"""
Xenia CRM – Segmentation Engine
Computes multi-label segment assignments for all customers based on RFM scores,
category affinities, campaign attributions, and communication fatigue (Spam Risk).
"""

import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import db_session
from app.models.customer import CustomerSegment

logger = logging.getLogger("xenia.segmentation")


class SegmentationService:
    @staticmethod
    def run_segmentation(db: Session) -> int:
        """
        Calculates and updates customer segment memberships in the database.
        Clears old segments and bulk inserts new ones.
        """
        logger.info("Starting segmentation engine run...")
        now = datetime.now(timezone.utc)

        # 1. Query all necessary metrics and attributes from customer_metrics and customers
        metrics_query = text("""
            SELECT 
                m.customer_id,
                m.r_score,
                m.f_score,
                m.m_score,
                m.value_score,
                m.churn_score,
                m.churn_probability,
                m.days_since_last_order,
                m.total_orders,
                m.category_affinity_json,
                m.engagement_score
            FROM customer_metrics m
        """)
        metrics = db.execute(metrics_query).fetchall()

        if not metrics:
            logger.warning("No customer metrics found. Cannot run segmentation.")
            return 0

        # 2. Query campaign-driven purchases (ratio of attributed orders)
        attribution_query = text("""
            SELECT 
                customer_id,
                COUNT(order_id) as total_orders,
                COUNT(attributed_communication_id) as attributed_orders
            FROM orders
            GROUP BY customer_id
        """)
        attribution_records = db.execute(attribution_query).fetchall()
        attr_ratio = {
            r.customer_id: (r.attributed_orders / r.total_orders) if r.total_orders > 0 else 0.0
            for r in attribution_records
        }

        # 3. Query communication frequency in the last 7 days (for Spam Risk detection)
        # Also query consecutive ignored communications
        recent_comm_query = text("""
            SELECT 
                customer_id,
                COUNT(communication_id) as comms_last_7d
            FROM communications
            WHERE created_at >= :date_7d
            GROUP BY customer_id
        """)
        date_7d = now - timedelta(days=7)
        recent_comms = db.execute(recent_comm_query, {"date_7d": date_7d}).fetchall()
        comms_7d = {r.customer_id: r.comms_last_7d for r in recent_comms}

        # Query ignored count: consecutive communications with no opens or clicks
        # We fetch the last 5 communications for each customer and count how many were not opened
        ignored_query = text("""
            SELECT 
                c.customer_id,
                c.communication_id,
                c.created_at,
                (SELECT COUNT(*) FROM communication_events e WHERE e.communication_id = c.communication_id AND e.event_type IN ('opened', 'clicked')) as engagement_count
            FROM communications c
            ORDER BY c.customer_id, c.created_at DESC
        """)
        comm_events = db.execute(ignored_query).fetchall()
        
        ignored_streaks = {}
        for r in comm_events:
            c_id = r.customer_id
            ignored_streaks.setdefault(c_id, [])
            if len(ignored_streaks[c_id]) < 5:  # Inspect last 5
                # If engagement_count is 0, it means it was ignored
                ignored_streaks[c_id].append(r.engagement_count == 0)

        consecutive_ignored = {
            c_id: sum(1 for is_ignored in streak if is_ignored)
            for c_id, streak in ignored_streaks.items()
        }

        # 4. Compute segments
        segment_entries = []
        
        for m in metrics:
            c_id = m.customer_id
            
            # Extract RFM and scores
            r, f, env_m = m.r_score, m.f_score, m.m_score
            val_score = m.value_score or 0.0
            churn_prob = m.churn_probability or 0.0
            days_inactive = m.days_since_last_order or 0
            total_orders = m.total_orders or 0
            affinities = m.category_affinity_json or {}
            
            # Get pre-computed indicators
            c_attr_ratio = attr_ratio.get(c_id, 0.0)
            c_comms_7d = comms_7d.get(c_id, 0)
            c_ignored_count = consecutive_ignored.get(c_id, 0)

            customer_segments = []

            # ── Value-Based Segments ──────────────────────────────────────────
            if r >= 4 and f >= 4 and env_m >= 4:
                customer_segments.append("Champion")
            elif val_score >= 70.0:
                customer_segments.append("High Value")
            
            # ── Churn/Retention-Based Segments ────────────────────────────────
            if churn_prob >= 0.70 and total_orders >= 3:
                customer_segments.append("At Risk")
            elif churn_prob >= 0.85 or days_inactive >= 180:
                customer_segments.append("Lost")
            
            # ── Category Affinity Segments ────────────────────────────────────
            if affinities.get("Groceries", 0.0) >= 50.0 and total_orders >= 4:
                customer_segments.append("Grocery Loyalist")
            if affinities.get("Electronics", 0.0) >= 40.0 and total_orders >= 2:
                customer_segments.append("Electronics Enthusiast")
            if (affinities.get("Sports", 0.0) >= 35.0 or affinities.get("Health", 0.0) >= 35.0) and total_orders >= 3:
                customer_segments.append("Fitness Shopper")
            if (affinities.get("Baby Products", 0.0) >= 30.0 or affinities.get("Books", 0.0) >= 30.0) and total_orders >= 3:
                customer_segments.append("Young Family")

            # ── Marketing Behavior Segments ───────────────────────────────────
            # Discount Hunter: high attribution from communication pushes
            if c_attr_ratio >= 0.35 and total_orders >= 3:
                customer_segments.append("Discount Hunter")

            # ── [CONTRARIAN] Spam Risk / Fatigue Segment ──────────────────────
            # Mark customer as Spam Risk if they are heavily contacted recently OR ignoring messages
            if c_comms_7d >= 3 or c_ignored_count >= 4:
                customer_segments.append("Spam Risk")

            # Build database rows
            for seg_name in customer_segments:
                segment_entries.append({
                    "customer_id": c_id,
                    "segment_name": seg_name,
                    "assigned_at": now
                })

        # 5. Clear old segments and bulk insert new ones
        logger.info("Clearing old segment memberships...")
        db.execute(text("TRUNCATE TABLE customer_segments;"))
        db.commit()

        logger.info(f"Bulk inserting {len(segment_entries)} segment memberships...")
        insert_query = text("""
            INSERT INTO customer_segments (customer_id, segment_name, assigned_at)
            VALUES (:customer_id, :segment_name, :assigned_at)
            ON CONFLICT (customer_id, segment_name) DO NOTHING;
        """)

        # Execute inserts in batches of 2000
        batch_size = 2000
        for i in range(0, len(segment_entries), batch_size):
            db.execute(insert_query, segment_entries[i:i + batch_size])
        
        db.commit()
        logger.info(f"Segmentation complete! Assigned {len(segment_entries)} segments across the customer base.")
        return len(segment_entries)
