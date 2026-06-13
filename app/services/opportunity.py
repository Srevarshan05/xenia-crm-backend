"""
Xenia CRM – Opportunity Discovery Engine
Scans database metrics and basket rules to identify retail opportunities
and safety fatigue cooling actions. Saves opportunities with projected revenues,
key drivers, recommended promotions, and audience filters.
"""

import os
import json
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import db_session
from app.models.promotion import Promotion
from app.models.opportunity import Opportunity
from app.services.basket_affinity import BasketAffinityService

logger = logging.getLogger("xenia.opportunity")


class OpportunityDiscoveryService:
    @staticmethod
    def discover_all_opportunities(db: Session) -> int:
        """
        Runs the discovery algorithms to identify campaign and safety opportunities.
        Clears existing 'open' opportunities and replaces them with fresh insights.
        """
        logger.info("Starting Opportunity Discovery Engine run...")
        now = datetime.now(timezone.utc)

        # Fetch promotions list to link appropriate coupon codes
        promotions = db.query(Promotion).filter(Promotion.active == True).all()
        promos_by_code = {p.promo_code: p for p in promotions}

        # Fetch baseline customer metrics aggregates for financial projections
        avg_aov_query = text("SELECT COALESCE(AVG(avg_order_value), 1500.0) FROM customer_metrics WHERE total_orders > 0")
        global_avg_aov = float(db.execute(avg_aov_query).scalar() or 1500.0)

        discovered_ops = []

        # ──────────────────────────────────────────────────────────────────────
        # OPPORTUNITY 1: Reactivate High-Value Churn Risk
        # ──────────────────────────────────────────────────────────────────────
        # Target: value_score >= 70 (or high value segment), churn_probability >= 0.70, not lost
        logger.info("Analyzing Opportunity: Reactivate High-Value Churn Risk...")
        reactivate_query = text("""
            SELECT m.customer_id, m.avg_order_value, m.preferred_channel
            FROM customer_metrics m
            WHERE m.value_score >= 65.0 
              AND m.churn_probability >= 0.65 
              AND m.days_since_last_order < 180
        """)
        reactivate_rows = db.execute(reactivate_query).fetchall()
        
        if reactivate_rows:
            reactivate_ids = [str(r.customer_id) for r in reactivate_rows]
            avg_aov = sum(float(r.avg_order_value or 0) for r in reactivate_rows) / len(reactivate_rows)
            avg_aov = avg_aov if avg_aov > 0 else global_avg_aov
            
            # Projected Revenue: assume 12% reactivation rate on WINBACK25 coupon code
            conversion_rate = 0.12
            potential_rev = len(reactivate_ids) * avg_aov * conversion_rate
            
            # Find win-back promo
            promo = promos_by_code.get("WINBACK25")
            promo_id = promo.promotion_id if promo else None

            discovered_ops.append({
                "type": "reactivation",
                "description": "Re-engage premium shoppers who haven't made a purchase recently.",
                "audience_size": len(reactivate_ids),
                "segment_filter": {
                    "min_value_score": 65.0,
                    "min_churn_probability": 0.65,
                    "max_days_inactive": 180
                },
                "customer_ids_sample": reactivate_ids[:10],
                "potential_revenue": Decimal(str(round(potential_rev, 2))),
                "priority": "high",
                "ai_explanation": (
                    f"This group of {len(reactivate_ids)} shoppers was chosen based on a purchase Recency (R) "
                    "inactivity window of up to 180 days, high lifetime spend (Monetary value M), "
                    "and elevated Churn Probability (exceeding 65%). Active customers with low churn risk "
                    "were excluded. The WINBACK25 promotion code was chosen over standard codes because "
                    "its 25% discount is optimal to reactivate premium lapsing customers without diluting margins "
                    "on active shoppers."
                ),
                "ai_action_plan": (
                    "1. Launch a high-incentive campaign using WhatsApp.\n"
                    "2. Attach the exclusive promo code WINBACK25 (25% off).\n"
                    "3. Personalize the message copy with their top purchased category."
                ),
                "ai_context": {
                    "segment": "High Value Churn Risk",
                    "churn_threshold": 0.65,
                    "suggested_channel": "WhatsApp",
                    "assumed_conversion_rate": conversion_rate,
                    "average_aov": avg_aov
                },
                "confidence_score": 0.90,
                "key_drivers": ["High lifetime spend", "Recent drop in purchase frequency", "Lapsing VIP status"],
                "recommended_promotion_id": promo_id,
                "recommended_channel": "WhatsApp",
                "status": "open",
                "created_at": now
            })

        # ──────────────────────────────────────────────────────────────────────
        # OPPORTUNITY 2: Cross-sell High-Affinity Category
        # ──────────────────────────────────────────────────────────────────────
        # Look at mined category rules from Phase 6. Let's inspect rules like Health -> Sports
        logger.info("Analyzing Opportunity: Cross-sell High-Affinity Category...")
        rules = BasketAffinityService.load_rules()
        
        # We find a rule with high lift (e.g. lift > 1.3)
        target_rule = None
        for r in rules:
            if len(r["antecedents"]) == 1 and len(r["consequents"]) == 1:
                target_rule = r
                break # Take the highest lift single-item rule

        if target_rule:
            source_cat = target_rule["antecedents"][0]
            target_cat = target_rule["consequents"][0]
            
            # Find customers who buy source category (spend affinity >= 30%)
            # but have 0 affinity (no purchases) in the target category, and are active
            cross_sell_query = text("""
                SELECT customer_id, avg_order_value, preferred_channel
                FROM customer_metrics
                WHERE days_since_last_order < 90
                  AND COALESCE((category_affinity_json->>:source_cat)::float, 0.0) >= 30.0
                  AND COALESCE((category_affinity_json->>:target_cat)::float, 0.0) = 0.0
            """)
            cross_sell_rows = db.execute(cross_sell_query, {"source_cat": source_cat, "target_cat": target_cat}).fetchall()
            
            if cross_sell_rows:
                cross_sell_ids = [str(r.customer_id) for r in cross_sell_rows]
                avg_aov = sum(float(r.avg_order_value or 0) for r in cross_sell_rows) / len(cross_sell_rows)
                avg_aov = avg_aov if avg_aov > 0 else global_avg_aov
                
                # Projected Revenue: assume 8% cross-sell conversion rate
                conversion_rate = 0.08
                potential_rev = len(cross_sell_ids) * avg_aov * conversion_rate
                
                # Check for category specific promo
                # e.g., if target_cat is 'Sports', look for 'FITNESS12' or matching category promotion
                promo_id = None
                for p in promotions:
                    if p.category == target_cat:
                        promo_id = p.promotion_id
                        break
                
                # Fallback to Welcome promo
                if not promo_id:
                    promo = promos_by_code.get("WELCOME15")
                    promo_id = promo.promotion_id if promo else None

                discovered_ops.append({
                    "type": "cross_sell",
                    "description": f"Introduce relevant {target_cat} items to {source_cat} buyers based on their previous basket preferences.",
                    "audience_size": len(cross_sell_ids),
                    "segment_filter": {
                        "source_category": source_cat,
                        "min_source_affinity": 30.0,
                        "target_category": target_cat,
                        "max_target_affinity": 0.0,
                        "max_days_inactive": 90
                    },
                    "customer_ids_sample": cross_sell_ids[:10],
                    "potential_revenue": Decimal(str(round(potential_rev, 2))),
                    "priority": "medium",
                    "ai_explanation": (
                        f"This cohort of {len(cross_sell_ids)} shoppers was chosen because they possess a strong Shopper Affinity "
                        f"(at least 30% spend share) for {source_cat} products but zero history (0% affinity) in {target_cat}, "
                        f"coupled with active purchase Recency (R) of less than 90 days. Other customers without this category "
                        f"preference were excluded. The recommended coupon code was selected specifically to reduce "
                        f"the trial barrier for {target_cat} items, rather than using a general site-wide promotion."
                    ),
                    "ai_action_plan": (
                        f"1. Target {source_cat} shoppers with a cross-sell campaign displaying top-rated {target_cat} products.\n"
                        f"2. Provide a category-specific discount coupon to lower the trial barrier.\n"
                        f"3. Trigger communication on their preferred engagement channel."
                    ),
                    "ai_context": {
                        "source_category": source_cat,
                        "target_category": target_cat,
                        "association_lift": target_rule["lift"],
                        "suggested_channel": "Email",
                        "assumed_conversion_rate": conversion_rate,
                        "average_aov": avg_aov
                    },
                    "confidence_score": 0.82,
                    "key_drivers": ["Active purchase behavior", "Category interest matching", "Product category gap"],
                    "recommended_promotion_id": promo_id,
                    "recommended_channel": "Email",
                    "status": "open",
                    "created_at": now
                })

        # ──────────────────────────────────────────────────────────────────────
        # OPPORTUNITY 3: Win Back Lost Champions
        # ──────────────────────────────────────────────────────────────────────
        # Target: Champion or High Value in the past (spend >= 40000), but now days_inactive >= 180 (Lost segment)
        logger.info("Analyzing Opportunity: Win Back Lost Champions...")
        winback_query = text("""
            SELECT m.customer_id, m.total_spend, m.preferred_channel
            FROM customer_metrics m
            WHERE m.total_spend >= 40000.0
              AND m.days_since_last_order >= 180
        """)
        winback_rows = db.execute(winback_query).fetchall()
        
        if winback_rows:
            winback_ids = [str(r.customer_id) for r in winback_rows]
            avg_spend = sum(float(r.total_spend or 0) for r in winback_rows) / len(winback_rows)
            
            # Projected Revenue: assume 15% winback rate with a high discount WINBACK25
            conversion_rate = 0.15
            potential_rev = len(winback_ids) * (avg_spend * 0.15) * conversion_rate  # estimated portion of previous value recovered
            potential_rev = potential_rev if potential_rev > 0 else (len(winback_ids) * global_avg_aov * conversion_rate)

            promo = promos_by_code.get("WINBACK25")
            promo_id = promo.promotion_id if promo else None

            discovered_ops.append({
                "type": "winback",
                "description": "Bring back former VIP shoppers who haven't placed an order in over 6 months.",
                "audience_size": len(winback_ids),
                "segment_filter": {
                    "min_lifetime_spend": 40000.0,
                    "min_days_inactive": 180
                },
                "customer_ids_sample": winback_ids[:10],
                "potential_revenue": Decimal(str(round(potential_rev, 2))),
                "priority": "high",
                "ai_explanation": (
                    f"This cohort of {len(winback_ids)} shoppers was selected due to an extreme purchase Recency (R) "
                    "inactivity of 180+ days, combined with very high historical Monetary value (M) exceeding "
                    "₹40,000 in spend. Shoppers with lower spend tiers or active purchase history were excluded. "
                    "The WINBACK25 promotion code was selected from available offers because a deep 25% incentive "
                    "is required to overcome long-term dormancy, whereas a lower 10-15% discount would be ineffective."
                ),
                "ai_action_plan": (
                    "1. Dispatch a highly personalized WhatsApp campaign offering our deepest discount: WINBACK25 (25% off).\n"
                    "2. Inject conversational check-in copy ('We miss you, VIP customer!').\n"
                    "3. Assign a dedicated customer experience representative if response is received."
                ),
                "ai_context": {
                    "segment": "Lost Champions",
                    "suggested_channel": "WhatsApp",
                    "assumed_conversion_rate": conversion_rate,
                    "average_historical_spend": avg_spend
                },
                "confidence_score": 0.88,
                "key_drivers": ["High historical spend", "Extended inactivity period", "VIP customer status"],
                "recommended_promotion_id": promo_id,
                "recommended_channel": "WhatsApp",
                "status": "open",
                "created_at": now
            })

        # ──────────────────────────────────────────────────────────────────────
        # OPPORTUNITY 4: Preferred Channel Flash Sale
        # ──────────────────────────────────────────────────────────────────────
        # Target: Active customers (days_inactive < 30) who prefer WhatsApp and haven't ordered in last 14 days
        logger.info("Analyzing Opportunity: Preferred Channel WhatsApp Flash Sale...")
        channel_query = text("""
            SELECT m.customer_id, m.avg_order_value
            FROM customer_metrics m
            WHERE m.preferred_channel = 'WhatsApp'
              AND m.days_since_last_order BETWEEN 14 AND 45
              AND m.churn_probability < 0.40
        """)
        channel_rows = db.execute(channel_query).fetchall()
        
        if channel_rows:
            channel_ids = [str(r.customer_id) for r in channel_rows]
            avg_aov = sum(float(r.avg_order_value or 0) for r in channel_rows) / len(channel_rows)
            avg_aov = avg_aov if avg_aov > 0 else global_avg_aov
            
            # Projected Revenue: assume 20% conversion rate on short flash sale
            conversion_rate = 0.20
            potential_rev = len(channel_ids) * avg_aov * conversion_rate
            
            promo = promos_by_code.get("DIWALI20")  # electronics/general flash coupon
            if not promo:
                promo = promos_by_code.get("WELCOME15")
            promo_id = promo.promotion_id if promo else None

            discovered_ops.append({
                "type": "channel_push",
                "description": "WhatsApp promotion targeting frequent shoppers who prefer conversational engagement.",
                "audience_size": len(channel_ids),
                "segment_filter": {
                    "preferred_channel": "WhatsApp",
                    "days_inactive_range": [14, 45],
                    "max_churn_probability": 0.40
                },
                "customer_ids_sample": channel_ids[:10],
                "potential_revenue": Decimal(str(round(potential_rev, 2))),
                "priority": "medium",
                "ai_explanation": (
                    f"This cohort of {len(channel_ids)} shoppers was selected because they have a low Churn Probability "
                    "under 40%, a moderate purchase Recency (R) between 14 and 45 days, and preferred channel metrics "
                    "heavily favoring WhatsApp. Shoppers with high churn risk or other channel preferences were excluded. "
                    "The DIWALI20/WELCOME15 promotion was selected to drive instant conversational conversions, "
                    "matching their high-affinity mobile touchpoints."
                ),
                "ai_action_plan": (
                    "1. Schedule an instant WhatsApp blast with a 24-hour expiration notice.\n"
                    "2. Offer a clean 15-20% discount code.\n"
                    "3. Direct them straight to their top purchased category landing page."
                ),
                "ai_context": {
                    "preferred_channel": "WhatsApp",
                    "assumed_conversion_rate": conversion_rate,
                    "average_aov": avg_aov
                },
                "confidence_score": 0.85,
                "key_drivers": ["Preferred channel alignment", "High responsiveness probability", "Active shopper status"],
                "recommended_promotion_id": promo_id,
                "recommended_channel": "WhatsApp",
                "status": "open",
                "created_at": now
            })

        # ──────────────────────────────────────────────────────────────────────
        # [CONTRARIAN] OPPORTUNITY 5: Campaign Fatigue Suppression (Guardian AI)
        # ──────────────────────────────────────────────────────────────────────
        # Target: Spam Risk segment. Customers who are over-contacted or ignoring campaigns.
        # Action: Suppress from all active campaigns, apply cooling off.
        logger.info("Analyzing Opportunity: Campaign Fatigue Suppression (Guardian AI)...")
        suppression_query = text("""
            SELECT s.customer_id
            FROM customer_segments s
            WHERE s.segment_name = 'Spam Risk'
        """)
        suppression_rows = db.execute(suppression_query).fetchall()
        
        if suppression_rows:
            suppression_ids = [str(r.customer_id) for r in suppression_rows]
            
            # Projected Revenue: This is about stopping churn, i.e. saving customer lifetime value!
            # Let's project 'Saved Lifetime Value' (e.g. 10% of their historical spend saved from complete churn)
            value_saved_query = text("""
                SELECT COALESCE(SUM(total_spend), 0.0)
                FROM customer_metrics
                WHERE customer_id IN (
                    SELECT customer_id FROM customer_segments WHERE segment_name = 'Spam Risk'
                )
            """)
            total_fatigue_spend = float(db.execute(value_saved_query).scalar() or 0.0)
            saved_ltv = total_fatigue_spend * 0.10  # assume we prevent 10% churn loss by going silent
            
            discovered_ops.append({
                "type": "fatigue_suppression",
                "description": "Apply a 14-day marketing cooling-off period to over-contacted VIP customers to protect engagement.",
                "audience_size": len(suppression_ids),
                "segment_filter": {
                    "segment_name": "Spam Risk"
                },
                "customer_ids_sample": suppression_ids[:10],
                "potential_revenue": Decimal(str(round(saved_ltv, 2))),  # Revenue saved through retention
                "priority": "high",
                "ai_explanation": (
                    f"This cohort of {len(suppression_ids)} shoppers was selected because their communication Frequency (F) "
                    "is unsustainably high (3+ messages in the last 7 days) or they have ignored 4+ consecutive campaigns, "
                    "creating a high unsubscribe/spam risk. Active, engaged shoppers were excluded from suppression. "
                    "No promotion is recommended for this cohort, as the system mandates a strict cooling-off period "
                    "to preserve long-term brand relationship."
                ),
                "ai_action_plan": (
                    "1. Exclude these customer IDs from all ongoing and upcoming marketing blasts.\n"
                    "2. Apply a strict 14-day messaging cooling-off window.\n"
                    "3. Clear their spam flag only when the cooling-off period expires and positive organic behavior occurs."
                ),
                "ai_context": {
                    "safety_action": "Exclude / Suppress",
                    "cooling_period_days": 14,
                    "reasons": ["Ignored streak >= 4", "Sent count last 7d >= 3"],
                    "total_risk_revenue": total_fatigue_spend
                },
                "confidence_score": 0.95,
                "key_drivers": ["Multiple ignored communications", "High message frequency", "Channel oversaturation"],
                "recommended_promotion_id": None,
                "recommended_channel": None,  # No channel (Do not contact!)
                "status": "open",
                "created_at": now
            })

        # 6. Clear existing 'open' opportunities and insert the newly discovered ones
        logger.info("Clearing existing open opportunities...")
        db.execute(text("DELETE FROM opportunities WHERE status = 'open'"))
        db.commit()

        logger.info(f"Saving {len(discovered_ops)} discovered opportunities...")
        for op in discovered_ops:
            new_op = Opportunity(
                type=op["type"],
                description=op["description"],
                audience_size=op["audience_size"],
                segment_filter=op["segment_filter"],
                customer_ids_sample=op["customer_ids_sample"],
                potential_revenue=op["potential_revenue"],
                priority=op["priority"],
                ai_explanation=op["ai_explanation"],
                ai_action_plan=op["ai_action_plan"],
                ai_context=op["ai_context"],
                confidence_score=op["confidence_score"],
                key_drivers=op["key_drivers"],
                recommended_promotion_id=op["recommended_promotion_id"],
                recommended_channel=op["recommended_channel"],
                status=op["status"],
                created_at=op["created_at"]
            )
            db.add(new_op)
        
        db.commit()
        logger.info(f"Discovery complete! Populated {len(discovered_ops)} active opportunity types in the database.")
        return len(discovered_ops)
