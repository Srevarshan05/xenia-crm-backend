"""
Xenia CRM – Revenue Attribution Service
Implements a 7-day last-touch attribution model to trace customer orders
back to marketing communications and calculate campaign ROI metrics.
"""

import logging
from decimal import Decimal
from datetime import timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.campaign import Campaign, CampaignMetrics, Communication
from app.models.order import Order

logger = logging.getLogger("xenia.attribution")

class RevenueAttributionService:
    @classmethod
    def run_attribution_pipeline(cls, db: Session, campaign_id=None) -> None:
        """
        Runs the attribution engine:
        1. Identifies all orders placed within 7 days of a campaign communication sent to the same customer.
        2. Links orders to the most recent communication (last-touch attribution) by setting attributed_communication_id.
        3. Recomputes CampaignMetrics for all campaigns (or a specific campaign if provided).
        """
        logger.info("Starting revenue attribution pipeline...")
        
        # Optimize query: only scan orders placed in the last 7 days.
        # This prevents performance bottlenecks on the 139k+ historical seeded orders.
        from datetime import datetime, timezone
        window_limit = datetime.now(timezone.utc) - timedelta(days=7)
        orders = db.query(Order).filter(Order.order_date >= window_limit).all()
        
        attribution_count = 0
        for order in orders:
            # Find all communications to this customer sent BEFORE the order date, within a 7-day window
            window_start = order.order_date - timedelta(days=7)
            
            latest_comm = db.query(Communication).filter(
                Communication.customer_id == order.customer_id,
                Communication.created_at <= order.order_date,
                Communication.created_at >= window_start,
                Communication.status != "failed"
            ).order_by(Communication.created_at.desc()).first()
            
            if latest_comm:
                # Link order to this communication
                if order.attributed_communication_id != latest_comm.communication_id:
                    order.attributed_communication_id = latest_comm.communication_id
                    attribution_count += 1
                    
        db.commit()
        if attribution_count > 0:
            logger.info(f"Linked {attribution_count} orders to their source communications.")
            
        # Step 2: Recalculate CampaignMetrics
        campaign_query = db.query(Campaign)
        if campaign_id:
            campaign_query = campaign_query.filter(Campaign.campaign_id == campaign_id)
            
        campaigns = campaign_query.all()
        
        cost_per_send_map = {
            "whatsapp": Decimal("0.50"),
            "email": Decimal("0.05"),
            "sms": Decimal("0.15")
        }
        
        for campaign in campaigns:
            # Retrieve or create metrics record
            metrics = db.query(CampaignMetrics).filter(CampaignMetrics.campaign_id == campaign.campaign_id).first()
            if not metrics:
                metrics = CampaignMetrics(campaign_id=campaign.campaign_id)
                db.add(metrics)
                
            # Count communications status
            total_sent = db.query(Communication).filter(Communication.campaign_id == campaign.campaign_id).count()
            total_delivered = db.query(Communication).filter(Communication.campaign_id == campaign.campaign_id, Communication.status.in_(["delivered", "opened", "clicked", "promo_applied", "purchased"])).count()
            total_opened = db.query(Communication).filter(Communication.campaign_id == campaign.campaign_id, Communication.status.in_(["opened", "clicked", "promo_applied", "purchased"])).count()
            total_clicked = db.query(Communication).filter(Communication.campaign_id == campaign.campaign_id, Communication.status.in_(["clicked", "promo_applied", "purchased"])).count()
            total_promo_applied = db.query(Communication).filter(Communication.campaign_id == campaign.campaign_id, Communication.status.in_(["promo_applied", "purchased"])).count()
            total_failed = db.query(Communication).filter(Communication.campaign_id == campaign.campaign_id, Communication.status == "failed").count()
            
            # Attributed orders
            attributed_orders = db.query(Order).join(
                Communication, Order.attributed_communication_id == Communication.communication_id
            ).filter(Communication.campaign_id == campaign.campaign_id).all()
            
            total_purchased = len(attributed_orders)
            attributed_revenue = sum(o.total_amount for o in attributed_orders)
            
            # Cost & ROI
            channel_key = campaign.channel.lower()
            cost_per_send = cost_per_send_map.get(channel_key, Decimal("0.10"))
            estimated_cost = Decimal(total_sent) * cost_per_send
            
            roi = None
            if estimated_cost > 0:
                roi = float(((attributed_revenue - estimated_cost) / estimated_cost) * 100)
                
            conversion_rate = None
            if total_sent > 0:
                conversion_rate = float(total_purchased) / float(total_sent)
                
            # Update metrics record
            metrics.total_sent = total_sent
            metrics.total_delivered = total_delivered
            metrics.total_opened = total_opened
            metrics.total_clicked = total_clicked
            metrics.total_promo_applied = total_promo_applied
            metrics.total_purchased = total_purchased
            metrics.total_failed = total_failed
            metrics.attributed_revenue = attributed_revenue
            metrics.estimated_cost = estimated_cost
            metrics.roi = roi
            metrics.conversion_rate = conversion_rate
            
            logger.info(
                f"Updated metrics for Campaign '{campaign.name}': "
                f"Sent={total_sent}, Purchased={total_purchased}, Revenue={attributed_revenue:.2f}, ROI={roi or 0:.1f}%"
            )
            
        db.commit()
        logger.info("Revenue attribution pipeline completed successfully.")
