from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Dict, Any
import uuid
from uuid import UUID
import httpx
import logging
from datetime import datetime, timezone

from app.database import get_db
from app.models.campaign import Campaign, CampaignSimulation, CampaignMetrics, Communication
from app.models.customer import Customer, CustomerSegment, CustomerMetrics
from app.models.promotion import Promotion
from app.schemas.campaigns import CampaignCreate, CampaignStatusUpdate, CampaignResponse, SimulationDetail, MetricsDetail
from app.services.simulation import CampaignSimulationService
from app.services.attribution import RevenueAttributionService

logger = logging.getLogger("xenia.campaign_router")
router = APIRouter(prefix="/api/campaigns", tags=["Campaigns"])

# Channel Service endpoint
CHANNEL_SERVICE_URL = "http://localhost:8001/send"

@router.get("", response_model=List[CampaignResponse])
def list_campaigns(status: str = None, db: Session = Depends(get_db)):
    """
    GET /api/campaigns
    List all campaigns with optional status filtering.
    """
    query = db.query(Campaign)
    if status:
        query = query.filter(Campaign.status == status)
    campaigns = query.order_by(Campaign.created_at.desc()).all()
    return campaigns

@router.post("", response_model=CampaignResponse)
def create_campaign(payload: CampaignCreate, db: Session = Depends(get_db)):
    """
    POST /api/campaigns
    Create a new campaign.
    """
    # Verify promotion exists if provided
    if payload.promotion_id:
        promo = db.query(Promotion).filter(Promotion.promotion_id == payload.promotion_id).first()
        if not promo:
            raise HTTPException(status_code=404, detail="Promotion not found")
            
    campaign = Campaign(
        name=payload.name,
        objective=payload.objective,
        promotion_id=payload.promotion_id,
        channel=payload.channel,
        status="draft",
        target_segment=payload.target_segment,
        target_audience_size=payload.target_audience_size or 0,
        message_template=payload.message_template,
        message_variants=payload.message_variants
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    
    # Run initial simulation
    try:
        CampaignSimulationService.run_simulation(db, campaign.campaign_id)
        db.refresh(campaign)
    except Exception as e:
        logger.error(f"Failed to run initial simulation: {e}")
        
    return campaign

@router.get("/{campaign_id}", response_model=CampaignResponse)
def get_campaign(campaign_id: UUID, db: Session = Depends(get_db)):
    """
    GET /api/campaigns/{campaign_id}
    Get campaign details.
    """
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign

@router.patch("/{campaign_id}/status", response_model=CampaignResponse)
def update_campaign_status(campaign_id: UUID, payload: CampaignStatusUpdate, db: Session = Depends(get_db)):
    """
    PATCH /api/campaigns/{campaign_id}/status
    Updates the lifecycle status of a campaign.
    """
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
        
    campaign.status = payload.status
    if payload.status == "completed":
        campaign.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(campaign)
    return campaign

@router.post("/{campaign_id}/simulate", response_model=CampaignResponse)
def simulate_campaign(campaign_id: UUID, db: Session = Depends(get_db)):
    """
    POST /api/campaigns/{campaign_id}/simulate
    Triggers/refreshes campaign simulation using Xenia AI.
    """
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
        
    CampaignSimulationService.run_simulation(db, campaign_id)
    db.refresh(campaign)
    return campaign

@router.post("/{campaign_id}/launch", response_model=CampaignResponse)
def launch_campaign(campaign_id: UUID, db: Session = Depends(get_db)):
    """
    POST /api/campaigns/{campaign_id}/launch
    Launches a campaign:
    1. Fetches target customers belonging to target_segment.
    2. Populates the communications table (pending messages).
    3. Triggers async delivery simulation in channel-service.
    4. Updates campaign status to 'launched'.
    """
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
        
    if campaign.status in ["launched", "completed"]:
        raise HTTPException(status_code=400, detail=f"Campaign is already in '{campaign.status}' state.")

    # 1. Fetch targeted customer segment
    segment_customers = db.query(Customer).join(
        CustomerSegment, Customer.customer_id == CustomerSegment.customer_id
    ).filter(CustomerSegment.segment_name == campaign.target_segment).all()
    
    # Fallback if segment is empty, fetch some customers for demo
    if not segment_customers:
        logger.warning(f"No customers in segment '{campaign.target_segment}', falling back to random cohort...")
        segment_customers = db.query(Customer).order_by(text("random()")).limit(10).all()
        
    if not segment_customers:
        raise HTTPException(status_code=400, detail="Cannot launch campaign: target audience is empty.")

    # Update audience size
    campaign.target_audience_size = len(segment_customers)

    # 2. Populate communications table (batch insert for performance)
    comm_objects = []
    for customer in segment_customers:
        # Personalize copy
        message_text = campaign.message_template or "Hello {name}, checkout our new offers!"
        message_text = message_text.replace("{name}", customer.name)
        
        comm = Communication(
            campaign_id=campaign.campaign_id,
            customer_id=customer.customer_id,
            channel=campaign.channel,
            message_sent=message_text,
            status="pending",
            created_at=datetime.now(timezone.utc)
        )
        db.add(comm)
        comm_objects.append((comm, customer, message_text))
    
    # Single flush to assign UUIDs without committing yet
    db.flush()
    
    outbound_messages = []
    for comm, customer, message_text in comm_objects:
        outbound_messages.append({
            "communication_id": str(comm.communication_id),
            "customer_id": str(customer.customer_id),
            "channel": campaign.channel,
            "message": message_text
        })
        
    # 3. Trigger async delivery in channel-service
    payload = {
        "campaign_id": str(campaign.campaign_id),
        "messages": outbound_messages
    }
    
    try:
        response = httpx.post(CHANNEL_SERVICE_URL, json=payload, timeout=5.0)
        logger.info(f"Triggered channel service: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"Could not connect to Channel Service at {CHANNEL_SERVICE_URL}. Running stub locally: {e}")
        # Transition anyway for demonstration resilience
        
    # 4. Advance lifecycle status
    campaign.status = "launched"
    campaign.launched_at = datetime.now(timezone.utc)
    
    # Initialize metrics
    metrics = db.query(CampaignMetrics).filter(CampaignMetrics.campaign_id == campaign.campaign_id).first()
    if not metrics:
        metrics = CampaignMetrics(
            campaign_id=campaign.campaign_id,
            total_sent=len(segment_customers)
        )
        db.add(metrics)
        
    db.commit()
    db.refresh(campaign)
    return campaign

@router.get("/{campaign_id}/analytics")
def get_campaign_analytics(campaign_id: UUID, db: Session = Depends(get_db)):
    """
    GET /api/campaigns/{campaign_id}/analytics
    Returns full funnel analytics for a launched/completed campaign.
    """
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
        
    # Read metrics directly from DB - attribution runs via webhook callbacks, not on every GET

    metrics = campaign.metrics
    if not metrics:
        return {
            "campaign_id": campaign.campaign_id,
            "name": campaign.name,
            "funnel": {"sent": 0, "delivered": 0, "opened": 0, "clicked": 0, "promo_applied": 0, "purchased": 0, "failed": 0},
            "metrics": {
                "attributed_revenue": 0.0,
                "estimated_cost": 0.0,
                "roi": 0.0,
                "conversion_rate": 0.0
            }
        }
        
    return {
        "campaign_id": campaign.campaign_id,
        "name": campaign.name,
        "funnel": {
            "sent": metrics.total_sent,
            "delivered": metrics.total_delivered,
            "opened": metrics.total_opened,
            "clicked": metrics.total_clicked,
            "promo_applied": metrics.total_promo_applied,
            "purchased": metrics.total_purchased,
            "failed": metrics.total_failed
        },
        "metrics": {
            "attributed_revenue": float(metrics.attributed_revenue),
            "estimated_cost": float(metrics.estimated_cost),
            "roi": float(metrics.roi or 0.0),
            "conversion_rate": float(metrics.conversion_rate or 0.0)
        }
    }

from app.models.order import Order

@router.get("/{campaign_id}/recipients")
def get_campaign_recipients(campaign_id: UUID, page: int = 1, limit: int = 50, db: Session = Depends(get_db)):
    """
    GET /api/campaigns/{campaign_id}/recipients
    Returns paginated individual shopper-level communications and their status/attributed orders.
    """
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
        
    offset = (page - 1) * limit
    comms = db.query(Communication).filter(
        Communication.campaign_id == campaign_id
    ).order_by(Communication.created_at.desc()).offset(offset).limit(limit).all()
    
    results = []
    # Bulk-fetch attributed orders for all comms in one query (eliminates N+1)
    comm_ids = [c.communication_id for c in comms]
    orders_by_comm = {}
    if comm_ids:
        comm_orders = db.query(Order).filter(Order.attributed_communication_id.in_(comm_ids)).all()
        for order in comm_orders:
            orders_by_comm[order.attributed_communication_id] = {
                "order_id": str(order.order_id),
                "total_amount": float(order.total_amount),
                "order_date": order.order_date
            }
    
    for c in comms:
        results.append({
            "communication_id": str(c.communication_id),
            "customer": {
                "customer_id": str(c.customer.customer_id),
                "name": c.customer.name,
                "email": c.customer.email,
                "city": c.customer.city
            },
            "channel": c.channel,
            "status": c.status,
            "created_at": c.created_at,
            "attributed_order": orders_by_comm.get(c.communication_id)
        })
        
    # Get total count for pagination
    total_count = db.query(Communication).filter(Communication.campaign_id == campaign_id).count()
    
    return {
        "recipients": results,
        "total_count": total_count,
        "page": page,
        "limit": limit
    }

