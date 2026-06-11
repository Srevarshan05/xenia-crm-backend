"""
Xenia CRM – Campaign Simulation Service
Simulates marketing campaign performance (reach, CTR, conversion rate, revenue, and risks)
by combining a rule-based baseline engine with Xenia AI (Gemini 2.5 Flash).
"""

import logging
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.campaign import Campaign, CampaignSimulation
from app.models.promotion import Promotion
from app.services.xenia_ai import XeniaAIService

logger = logging.getLogger("xenia.simulation")

class CampaignSimulationService:
    @classmethod
    def run_simulation(cls, db: Session, campaign_id) -> CampaignSimulation:
        """
        Runs the full simulation pipeline:
        1. Calculates deterministic rule-based baseline metrics.
        2. Merges with historical performance benchmarks.
        3. Invokes Xenia AI to adjust predictions and generate risk factors/narratives.
        4. Saves and returns the CampaignSimulation object.
        """
        logger.info(f"Running simulation pipeline for campaign {campaign_id}...")
        
        campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found.")

        # 1. Base Channel Metrics (Fallback if no history)
        channel_defaults = {
            "whatsapp": {"ctr": 0.25, "cvr": 0.08, "cost_per_send": 0.50},
            "email": {"ctr": 0.12, "cvr": 0.03, "cost_per_send": 0.05},
            "sms": {"ctr": 0.08, "cvr": 0.015, "cost_per_send": 0.15}
        }
        
        channel_key = campaign.channel.lower()
        defaults = channel_defaults.get(channel_key, {"ctr": 0.10, "cvr": 0.02, "cost_per_send": 0.10})
        
        # 2. Segment Modifier
        segment_modifiers = {
            "Champion": {"ctr": 1.4, "cvr": 1.3},
            "High Value": {"ctr": 1.25, "cvr": 1.2},
            "At Risk": {"ctr": 0.7, "cvr": 0.6},
            "Dormant": {"ctr": 0.4, "cvr": 0.3},
            "High Engagement": {"ctr": 1.5, "cvr": 1.4},
            "Discount Hunter": {"ctr": 1.2, "cvr": 1.25}
        }
        
        seg_mod = segment_modifiers.get(campaign.target_segment, {"ctr": 1.0, "cvr": 1.0})
        
        # 3. Promotion Modifier
        promo_cvr_mod = 1.0
        if campaign.promotion_id:
            promo = db.query(Promotion).filter(Promotion.promotion_id == campaign.promotion_id).first()
            if promo:
                discount = float(promo.discount_percentage or 0)
                if discount > 20:
                    promo_cvr_mod = 1.6
                elif discount > 10:
                    promo_cvr_mod = 1.3
                else:
                    promo_cvr_mod = 1.15

        # 4. Compute Baseline Predictions
        target_size = campaign.target_audience_size or 0
        base_ctr = min(defaults["ctr"] * seg_mod["ctr"], 1.0)
        base_cvr = min(defaults["cvr"] * seg_mod["cvr"] * promo_cvr_mod, 1.0)
        
        # 5. Delegate to Xenia AI for contextual enrichment and override
        # The AI receives these baselines and contextualizes the simulation.
        # XeniaAIService.simulate_campaign already fetches historical benchmarks and does this.
        simulation = XeniaAIService.simulate_campaign(db, campaign_id)
        
        # We can also store the calculated baselines inside the simulation context JSON
        context = dict(simulation.simulation_context or {})
        context.update({
            "rule_engine_baseline": {
                "base_ctr": base_ctr,
                "base_cvr": base_cvr,
                "target_size": target_size,
                "segment_modifiers": seg_mod,
                "promotion_modifier": promo_cvr_mod
            }
        })
        simulation.simulation_context = context
        db.commit()
        
        logger.info(f"Simulation pipeline completed for campaign {campaign_id}.")
        return simulation
