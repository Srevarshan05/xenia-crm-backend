"""
Xenia CRM – Customer Intelligence Engine
Calculates Recency, Frequency, and Monetary (RFM) scores, composite customer scores,
preferred channels, category affinity maps, and schedules intelligence updates.
"""

import logging
import json
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import pandas as pd
import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import db_session
from app.models.customer import Customer, CustomerMetrics
from app.models.order import Order
from app.models.campaign import Communication, CommunicationEvent

logger = logging.getLogger("xenia.intelligence")


def compute_quintiles(series: pd.Series, reverse: bool = False) -> pd.Series:
    """
    Split a pandas Series into 5 quintiles (values 1 to 5).
    If reverse=True, lower values get higher scores (useful for Recency).
    Handles duplicates gracefully.
    """
    if series.empty:
        return series
    
    # If all values are the same, return score 3 for all
    if series.nunique() == 1:
        return pd.Series(3, index=series.index)
        
    try:
        # qcut handles division into equal-frequency bins
        ranks = pd.qcut(series, 5, labels=False, duplicates='drop') + 1
        if reverse:
            max_rank = ranks.max()
            ranks = max_rank - ranks + 1
        return ranks.astype(int)
    except Exception as e:
        logger.warning(f"qcut failed, falling back to rank-based quintiles: {e}")
        # Fallback using rank-order mapping (guarantees equal sized bins even with duplicate values)
        ranks = series.rank(method='first')
        quintiles = pd.qcut(ranks, 5, labels=False) + 1
        if reverse:
            quintiles = 6 - quintiles
        return quintiles.astype(int)


class IntelligenceService:
    @staticmethod
    def calculate_rfm_metrics(db: Session) -> int:
        """
        Computes RFM profiles, engagement scores, category affinities, and preferred channels
        for ALL customers in the database. Upserts results into the customer_metrics table.
        """
        logger.info("Starting RFM metrics calculation...")
        now = datetime.now(timezone.utc)

        # 1. Fetch aggregate order metrics per customer
        # We perform a single optimized query to calculate totals, averages, and date ranges
        order_query = text("""
            SELECT 
                c.customer_id,
                COUNT(o.order_id) as total_orders,
                COALESCE(SUM(o.total_amount), 0.0) as total_spend,
                MAX(o.order_date) as last_order_date,
                COUNT(CASE WHEN o.order_date >= :date_90d THEN o.order_id END) as orders_last_90d,
                COUNT(CASE WHEN o.order_date >= :date_180d AND o.order_date < :date_90d THEN o.order_id END) as orders_prev_90d
            FROM customers c
            LEFT JOIN orders o ON c.customer_id = o.customer_id
            GROUP BY c.customer_id
        """)

        date_90d = now - timedelta(days=90)
        date_180d = now - timedelta(days=180)

        order_records = db.execute(order_query, {"date_90d": date_90d, "date_180d": date_180d}).fetchall()
        
        if not order_records:
            logger.info("No customers found to compute metrics for.")
            return 0

        # Convert to Pandas DataFrame for vectorised calculations
        df = pd.DataFrame([
            {
                "customer_id": r.customer_id,
                "total_orders": r.total_orders,
                "total_spend": float(r.total_spend),
                "last_order_date": r.last_order_date,
                "orders_last_90d": r.orders_last_90d,
                "orders_prev_90d": r.orders_prev_90d
            }
            for r in order_records
        ])

        # Calculate recency (days since last order)
        # If the customer has never ordered, set to 730 days (2 years) as a default penalty
        def get_days_since(d):
            if pd.isna(d):
                return 730
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            return (now - d).days

        df["days_since_last_order"] = df["last_order_date"].apply(get_days_since)
        df["avg_order_value"] = df.apply(
            lambda r: round(r["total_spend"] / r["total_orders"], 2) if r["total_orders"] > 0 else 0.0, 
            axis=1
        )

        # 2. Compute RFM Scores
        # Scores are only computed for active purchasers. Customers with 0 orders get RFM=1.
        has_purchased = df["total_orders"] > 0
        df["r_score"] = 1
        df["f_score"] = 1
        df["m_score"] = 1

        if has_purchased.any():
            df.loc[has_purchased, "r_score"] = compute_quintiles(df.loc[has_purchased, "days_since_last_order"], reverse=True)
            df.loc[has_purchased, "f_score"] = compute_quintiles(df.loc[has_purchased, "total_orders"])
            df.loc[has_purchased, "m_score"] = compute_quintiles(df.loc[has_purchased, "total_spend"])

        # 3. Calculate Composite Scores
        # Value Score (0.0 to 100.0) -> Weighted RFM: R=20%, F=40%, M=40%
        df["value_score"] = df.apply(
            lambda r: round(((r["r_score"] * 0.2 + r["f_score"] * 0.4 + r["m_score"] * 0.4) / 5.0) * 100.0, 2),
            axis=1
        )

        # Rule-based Legacy Churn Score (0.0 to 100.0)
        # If no orders: churn_score is 100.0. Otherwise, linear risk based on recency.
        # Max recency target for churn is 180 days (6 months)
        df["churn_score"] = df.apply(
            lambda r: 100.0 if r["total_orders"] == 0 else min(100.0, round(max(0.0, (r["days_since_last_order"] - 30) / 150.0) * 100.0, 2)),
            axis=1
        )

        # 4. Fetch Category Affinities
        # We query the order item category distribution per customer
        category_query = text("""
            SELECT 
                o.customer_id, 
                p.category, 
                SUM(oi.quantity * oi.unit_price) as category_spend
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.order_id
            JOIN products p ON oi.product_id = p.product_id
            GROUP BY o.customer_id, p.category
        """)
        cat_records = db.execute(category_query).fetchall()
        
        customer_categories = {}
        for r in cat_records:
            customer_categories.setdefault(r.customer_id, []).append({
                "category": r.category,
                "spend": float(r.category_spend)
            })

        # Calculate affinities and top categories
        affinities = {}
        top_categories = {}
        for cust_id, cats in customer_categories.items():
            total = sum(c["spend"] for c in cats)
            if total > 0:
                # Store percentage breakdown: {"Electronics": 60.0, "Fashion": 40.0}
                affinities[cust_id] = {c["category"]: round((c["spend"] / total) * 100, 2) for c in cats}
                # Find category with highest spend
                top_categories[cust_id] = max(cats, key=lambda x: x["spend"])["category"]

        # 5. Fetch Campaign Engagement & Communications History
        # We fetch sending, delivery, open, click, and purchase counts per customer and channel
        engagement_query = text("""
            SELECT 
                c.customer_id,
                c.channel,
                COUNT(c.communication_id) as sent,
                SUM(CASE WHEN e.event_type = 'opened' THEN 1 ELSE 0 END) as opened,
                SUM(CASE WHEN e.event_type = 'clicked' THEN 1 ELSE 0 END) as clicked,
                SUM(CASE WHEN e.event_type = 'purchased' THEN 1 ELSE 0 END) as purchased
            FROM communications c
            LEFT JOIN communication_events e ON c.communication_id = e.communication_id
            GROUP BY c.customer_id, c.channel
        """)
        eng_records = db.execute(engagement_query).fetchall()

        customer_engagement = {}
        for r in eng_records:
            customer_engagement.setdefault(r.customer_id, []).append({
                "channel": r.channel,
                "sent": r.sent,
                "opened": r.opened,
                "clicked": r.clicked,
                "purchased": r.purchased
            })

        # Calculate composite engagement score and preferred channel
        engagement_scores = {}
        preferred_channels = {}
        
        for cust_id, channels in customer_engagement.items():
            total_sent = sum(ch["sent"] for ch in channels)
            total_opened = sum(ch["opened"] for ch in channels)
            total_clicked = sum(ch["clicked"] for ch in channels)
            total_purchased = sum(ch["purchased"] for ch in channels)

            # Engagement Score (0.0 to 100.0)
            # Weighted formula: Open=10, Click=30, Purchase=60
            if total_sent > 0:
                score = ((total_opened * 10 + total_clicked * 30 + total_purchased * 60) / (total_sent * 60)) * 100.0
                engagement_scores[cust_id] = min(100.0, round(score, 2))
            else:
                engagement_scores[cust_id] = 0.0

            # Preferred Channel Selection
            # Selection priority: channel with most clicks -> most opens -> most sent -> fallback 'WhatsApp'
            sorted_channels = sorted(
                channels,
                key=lambda x: (x["clicked"], x["opened"], x["sent"]),
                reverse=True
            )
            preferred_channels[cust_id] = sorted_channels[0]["channel"] if sorted_channels else "WhatsApp"

        # 6. Build final payload and bulk upsert
        metrics_to_upsert = []
        for idx, row in df.iterrows():
            c_id = row["customer_id"]
            
            # Map calculated affinities, engagement, and preferences
            cust_affinity = affinities.get(c_id, {})
            cust_top_cat = top_categories.get(c_id, None)
            cust_eng_score = engagement_scores.get(c_id, 0.0)
            cust_pref_channel = preferred_channels.get(c_id, "WhatsApp")

            metrics_to_upsert.append({
                "customer_id": c_id,
                "r_score": int(row["r_score"]),
                "f_score": int(row["f_score"]),
                "m_score": int(row["m_score"]),
                "value_score": float(row["value_score"]),
                "churn_score": float(row["churn_score"]),
                "engagement_score": float(cust_eng_score),
                "preferred_channel": cust_pref_channel,
                "top_category": cust_top_cat,
                "category_affinity_json": json.dumps(cust_affinity),
                "total_orders": int(row["total_orders"]),
                "total_spend": float(row["total_spend"]),
                "avg_order_value": float(row["avg_order_value"]),
                "days_since_last_order": int(row["days_since_last_order"]),
                "orders_last_90d": int(row["orders_last_90d"]),
                "orders_prev_90d": int(row["orders_prev_90d"]),
                "last_updated": now
            })

        # Bulk upsert using SQL query to update on conflict
        # Using native postgres EXCLUDED updates
        upsert_query = text("""
            INSERT INTO customer_metrics (
                customer_id, r_score, f_score, m_score, value_score, churn_score,
                engagement_score, preferred_channel, top_category, category_affinity_json,
                total_orders, total_spend, avg_order_value, days_since_last_order,
                orders_last_90d, orders_prev_90d, last_updated
            ) VALUES (
                :customer_id, :r_score, :f_score, :m_score, :value_score, :churn_score,
                :engagement_score, :preferred_channel, :top_category, :category_affinity_json,
                :total_orders, :total_spend, :avg_order_value, :days_since_last_order,
                :orders_last_90d, :orders_prev_90d, :last_updated
            )
            ON CONFLICT (customer_id) DO UPDATE SET
                r_score = EXCLUDED.r_score,
                f_score = EXCLUDED.f_score,
                m_score = EXCLUDED.m_score,
                value_score = EXCLUDED.value_score,
                churn_score = EXCLUDED.churn_score,
                engagement_score = EXCLUDED.engagement_score,
                preferred_channel = EXCLUDED.preferred_channel,
                top_category = EXCLUDED.top_category,
                category_affinity_json = EXCLUDED.category_affinity_json,
                total_orders = EXCLUDED.total_orders,
                total_spend = EXCLUDED.total_spend,
                avg_order_value = EXCLUDED.avg_order_value,
                days_since_last_order = EXCLUDED.days_since_last_order,
                orders_last_90d = EXCLUDED.orders_last_90d,
                orders_prev_90d = EXCLUDED.orders_prev_90d,
                last_updated = EXCLUDED.last_updated;
        """)

        # Execute upserts in batches of 1000 to avoid locking database too long
        batch_size = 1000
        for i in range(0, len(metrics_to_upsert), batch_size):
            batch = metrics_to_upsert[i:i + batch_size]
            # Convert JSON dict fields to strings for correct psycopg2 binding
            # though sqlalchemy JSONB type handles it, bound queries sometimes need raw dict or cast
            db.execute(upsert_query, batch)
        
        db.commit()
        logger.info(f"Successfully computed and updated customer metrics for {len(metrics_to_upsert)} customers.")
        return len(metrics_to_upsert)
