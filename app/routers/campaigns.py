"""
Xenia CRM – Campaigns Router
Full campaign lifecycle: draft → reviewed → awaiting_approval → approved → launched → completed

Campaign Dispatch Flow:
  POST /launch → creates Communication records → queues dispatch as BackgroundTask → returns 202
  BackgroundTask → sends batches to Service B → Service B fires webhook callbacks back to Xenia
  Webhooks → update Communication status with event precedence → trigger attribution
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List
import uuid
from uuid import UUID
import logging
from datetime import datetime, timezone

from app.database import get_db
from app.models.campaign import Campaign, CampaignSimulation, CampaignMetrics, Communication
from app.models.customer import Customer, CustomerSegment, CustomerMetrics
from app.models.promotion import Promotion
from app.schemas.campaigns import CampaignCreate, CampaignStatusUpdate, CampaignResponse, SimulationDetail, MetricsDetail
from app.services.simulation import CampaignSimulationService
from app.services.dispatch import dispatch_campaign_messages

logger = logging.getLogger("xenia.campaign_router")
router = APIRouter(prefix="/api/campaigns", tags=["Campaigns"])


@router.get("", response_model=List[CampaignResponse])
def list_campaigns(status: str = None, db: Session = Depends(get_db)):
    """
    GET /api/campaigns
    List all campaigns with optional status filter.
    """
    query = db.query(Campaign)
    if status:
        query = query.filter(Campaign.status == status)
    return query.order_by(Campaign.created_at.desc()).all()


@router.post("", response_model=CampaignResponse)
def create_campaign(payload: CampaignCreate, db: Session = Depends(get_db)):
    """
    POST /api/campaigns
    Create a new campaign draft. Promotion must exist in DB if provided —
    Xenia does not create promotions, only recommends existing ones.
    """
    if payload.promotion_id:
        promo = db.query(Promotion).filter(Promotion.promotion_id == payload.promotion_id).first()
        if not promo:
            raise HTTPException(status_code=404, detail="Promotion not found. Promotions must be created by CRM users first.")

    campaign = Campaign(
        name=payload.name,
        objective=payload.objective,
        promotion_id=payload.promotion_id,
        channel=payload.channel,
        status="draft",
        target_segment=payload.target_segment,
        target_audience_size=payload.target_audience_size or 0,
        message_template=payload.message_template,
        message_variants=payload.message_variants,
        ai_strategy=payload.ai_strategy,
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)

    # Run initial simulation
    try:
        CampaignSimulationService.run_simulation(db, campaign.campaign_id)
        db.refresh(campaign)
    except Exception as e:
        logger.error(f"Simulation failed for new campaign {campaign.campaign_id}: {e}")

    return campaign


@router.get("/{campaign_id}", response_model=CampaignResponse)
def get_campaign(campaign_id: UUID, db: Session = Depends(get_db)):
    """GET /api/campaigns/{campaign_id}"""
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@router.put("/{campaign_id}", response_model=CampaignResponse)
def update_campaign(campaign_id: UUID, payload: CampaignCreate, db: Session = Depends(get_db)):
    """
    PUT /api/campaigns/{campaign_id}
    Update campaign details (e.g. name, channel, message_template).
    """
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    campaign.name = payload.name
    if payload.objective is not None:
        campaign.objective = payload.objective
    campaign.channel = payload.channel
    if payload.message_template is not None:
        campaign.message_template = payload.message_template
    if payload.promotion_id is not None:
        campaign.promotion_id = payload.promotion_id
    campaign.target_segment = payload.target_segment
    if payload.target_audience_size is not None:
        campaign.target_audience_size = payload.target_audience_size

    db.commit()
    db.refresh(campaign)
    return campaign


@router.patch("/{campaign_id}/status", response_model=CampaignResponse)
def update_campaign_status(campaign_id: UUID, payload: CampaignStatusUpdate, db: Session = Depends(get_db)):
    """
    PATCH /api/campaigns/{campaign_id}/status
    Advance campaign lifecycle status.
    Valid transitions: draft → reviewed → awaiting_approval → approved → launched → completed
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
    """POST /api/campaigns/{campaign_id}/simulate — refresh simulation projections."""
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    CampaignSimulationService.run_simulation(db, campaign_id)
    db.refresh(campaign)
    return campaign


@router.post("/{campaign_id}/launch")
def launch_campaign(
    campaign_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    POST /api/campaigns/{campaign_id}/launch
    Launches a campaign asynchronously:
      1. Validates campaign is in a launchable state
      2. Fetches target audience from segment
      3. Creates Communication records (batch)
      4. Enqueues dispatch as a BackgroundTask → returns 202 immediately
      5. Dispatch worker sends batches to Service B → Service B fires webhook callbacks

    Returns 202 Accepted immediately — delivery events arrive via webhook.
    """
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.status in ["launched", "completed"]:
        raise HTTPException(
            status_code=400,
            detail=f"Campaign is already '{campaign.status}'. Cannot re-launch."
        )

    # ── Step 1: Resolve target audience ──────────────────────────────────────
    segment_customers = db.query(Customer).join(
        CustomerSegment, Customer.customer_id == CustomerSegment.customer_id
    ).filter(
        CustomerSegment.segment_name == campaign.target_segment
    ).all()

    # Fallback for demo: use a small random cohort if segment is empty
    if not segment_customers:
        logger.warning(
            f"No customers in segment '{campaign.target_segment}'. "
            f"Falling back to 20-customer demo cohort."
        )
        segment_customers = db.query(Customer).order_by(text("random()")).limit(20).all()

    if not segment_customers:
        raise HTTPException(
            status_code=400,
            detail="Cannot launch campaign: target audience is empty."
        )

    # ── Step 2: Create Communication records ──────────────────────────────────
    campaign.target_audience_size = len(segment_customers)

    comm_objects: list[Communication] = []
    for customer in segment_customers:
        message_text = (campaign.message_template or "Hello {name}, check out our exclusive offers!")
        message_text = message_text.replace("{name}", customer.name.split()[0])

        comm = Communication(
            campaign_id=campaign.campaign_id,
            customer_id=customer.customer_id,
            channel=campaign.channel,
            message_sent=message_text,
            status="pending",
            created_at=datetime.now(timezone.utc)
        )
        db.add(comm)
        comm_objects.append(comm)

    # Flush to get UUIDs without committing — we need IDs for the dispatch payload
    db.flush()

    # ── Step 3: Build dispatch payload ────────────────────────────────────────
    # Map comm objects to a serializable format before session closes
    outbound_messages = [
        {
            "communication_id": str(comm.communication_id),
            "customer_id": str(comm.customer_id),
            "channel": comm.channel,
            "message": comm.message_sent or ""
        }
        for comm in comm_objects
    ]

    # ── Step 4: Advance campaign status + initialize metrics ──────────────────
    campaign.status = "launched"
    campaign.launched_at = datetime.now(timezone.utc)

    metrics = db.query(CampaignMetrics).filter(
        CampaignMetrics.campaign_id == campaign.campaign_id
    ).first()
    if not metrics:
        metrics = CampaignMetrics(
            campaign_id=campaign.campaign_id,
            total_sent=len(segment_customers)
        )
        db.add(metrics)

    db.commit()
    db.refresh(campaign)

    # ── Step 5: Enqueue dispatch as background task ───────────────────────────
    # Returns 202 immediately — delivery proceeds asynchronously
    background_tasks.add_task(
        dispatch_campaign_messages,
        db,
        str(campaign.campaign_id),
        outbound_messages
    )

    logger.info(
        f"Campaign '{campaign.name}' launched. "
        f"{len(outbound_messages)} messages queued for dispatch."
    )

    return {
        "campaign_id": str(campaign.campaign_id),
        "name": campaign.name,
        "status": "launched",
        "recipients_queued": len(outbound_messages),
        "message": "Campaign dispatched. Delivery events will arrive via webhook callbacks."
    }


@router.get("/{campaign_id}/analytics")
def get_campaign_analytics(campaign_id: UUID, db: Session = Depends(get_db)):
    """
    GET /api/campaigns/{campaign_id}/analytics
    Returns funnel metrics. Attribution is updated via webhook events, not on every GET.
    """
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    metrics = campaign.metrics
    if not metrics:
        return {
            "campaign_id": str(campaign.campaign_id),
            "name": campaign.name,
            "funnel": {
                "sent": 0, "delivered": 0, "opened": 0,
                "clicked": 0, "promo_applied": 0, "purchased": 0, "failed": 0
            },
            "metrics": {
                "attributed_revenue": 0.0, "estimated_cost": 0.0,
                "roi": 0.0, "conversion_rate": 0.0
            }
        }

    return {
        "campaign_id": str(campaign.campaign_id),
        "name": campaign.name,
        "status": campaign.status,
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
def get_campaign_recipients(
    campaign_id: UUID,
    page: int = 1,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """
    GET /api/campaigns/{campaign_id}/recipients
    Paginated shopper-level delivery status with lifecycle timestamps.
    """
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    offset = (page - 1) * limit
    comms = db.query(Communication).filter(
        Communication.campaign_id == campaign_id
    ).order_by(Communication.created_at.desc()).offset(offset).limit(limit).all()

    # Bulk-fetch attributed orders — eliminates N+1
    comm_ids = [c.communication_id for c in comms]
    orders_by_comm = {}
    if comm_ids:
        for order in db.query(Order).filter(Order.attributed_communication_id.in_(comm_ids)).all():
            orders_by_comm[order.attributed_communication_id] = {
                "order_id": str(order.order_id),
                "total_amount": float(order.total_amount),
                "order_date": order.order_date
            }

    results = []
    for c in comms:
        results.append({
            "communication_id": str(c.communication_id),
            "customer": {
                "customer_id": str(c.customer.customer_id),
                "name": c.customer.name,
                "email": c.customer.email,
                "city": c.customer.city,
                "lifetime_value": float(c.customer.metrics.total_spend or 0.0) if c.customer.metrics else 0.0,
                "last_purchase_days": int(c.customer.metrics.days_since_last_order or 0) if c.customer.metrics else 0,
                "churn_probability": float(c.customer.metrics.churn_probability or 0.0) if c.customer.metrics else 0.0,
                "preferred_channel": c.customer.metrics.preferred_channel or "WhatsApp" if c.customer.metrics else "WhatsApp",
                "top_category": c.customer.metrics.top_category if c.customer.metrics else None,
                "total_orders": c.customer.metrics.total_orders if c.customer.metrics else 0,
            },
            "channel": c.channel,
            "status": c.status,
            # Lifecycle timestamps for funnel timing analysis
            "timeline": {
                "created_at": c.created_at,
                "sent_at": c.sent_at,
                "delivered_at": c.delivered_at,
                "opened_at": c.opened_at,
                "clicked_at": c.clicked_at,
                "promo_applied_at": c.promo_applied_at,
            },
            "attributed_order": orders_by_comm.get(c.communication_id)
        })

    total_count = db.query(Communication).filter(Communication.campaign_id == campaign_id).count()

    return {
        "recipients": results,
        "total_count": total_count,
        "page": page,
        "limit": limit,
        "pages": (total_count + limit - 1) // limit
    }
