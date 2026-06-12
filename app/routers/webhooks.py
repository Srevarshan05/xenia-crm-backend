"""
Xenia CRM – Delivery Webhook Handler
Receives asynchronous event callbacks from the Channel Simulation Service (Service B).

Design Principles:
- Event precedence is strictly enforced — a lower-rank event can NEVER overwrite a higher-rank status
- Attribution runs in the background (non-blocking response)
- Purchases are NOT simulated here — they only occur via real order creation
- Every event is appended to communication_events for full audit trail
"""

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from uuid import UUID
import logging
from datetime import datetime, timezone
from typing import Optional

from app.database import get_db
from app.models.campaign import Campaign, Communication, CommunicationEvent
from app.services.attribution import RevenueAttributionService

logger = logging.getLogger("xenia.webhooks")
router = APIRouter(prefix="/api/webhook", tags=["Webhooks"])


# ── Event Precedence Map ──────────────────────────────────────────────────────
# A higher rank event can never be overwritten by a lower rank event.
EVENT_RANK: dict[str, int] = {
    "pending":       0,
    "sent":          1,
    "failed":        2,   # terminal on failure, but can still be superseded by delivered
    "delivered":     3,
    "opened":        4,
    "clicked":       5,
    "promo_applied": 6,
    "purchased":     7,
}

VALID_EVENTS = set(EVENT_RANK.keys())

# Timestamp field map — which column to set for each event
EVENT_TIMESTAMP_FIELD: dict[str, str] = {
    "sent":          "sent_at",
    "delivered":     "delivered_at",
    "opened":        "opened_at",
    "clicked":       "clicked_at",
    "promo_applied": "promo_applied_at",
}


class WebhookDeliveryPayload(BaseModel):
    communication_id: UUID
    event_type: str  # sent | delivered | opened | clicked | promo_applied | purchased | failed
    event_timestamp: Optional[datetime] = None
    metadata: Optional[dict] = None


def _run_attribution_bg(campaign_id: UUID):
    """Background task: runs attribution pipeline without blocking the webhook response."""
    from app.database import db_session
    try:
        with db_session() as db:
            RevenueAttributionService.run_attribution_pipeline(db, campaign_id=campaign_id)
    except Exception as e:
        logger.error(f"Background attribution failed for campaign {campaign_id}: {e}")


@router.post("/delivery")
def handle_delivery_webhook(
    payload: WebhookDeliveryPayload,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    POST /api/webhook/delivery
    Receives delivery lifecycle event callbacks from the Channel Simulation Service.

    Event precedence is enforced:
      pending(0) → sent(1) → delivered(3) → opened(4) → clicked(5) → promo_applied(6) → purchased(7)
    A lower-rank event will be logged but will NOT downgrade comm.status.
    """
    comm_id = payload.communication_id
    event_type = payload.event_type.lower().strip()
    event_ts = payload.event_timestamp or datetime.now(timezone.utc)

    # 1. Validate event type
    if event_type not in VALID_EVENTS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid event_type '{event_type}'. Valid events: {sorted(VALID_EVENTS)}."
        )

    logger.info(f"Webhook received: comm={comm_id} event={event_type}")

    # 2. Fetch communication
    comm = db.query(Communication).filter(Communication.communication_id == comm_id).first()
    if not comm:
        raise HTTPException(status_code=404, detail=f"Communication {comm_id} not found.")

    # 3. Simulate order creation for sandbox 'purchased' triggers
    if event_type == "purchased":
        from app.models.order import Order
        import random
        from decimal import Decimal
        
        # Check if already has an order linked to this communication
        existing_order = db.query(Order).filter(Order.attributed_communication_id == comm_id).first()
        if not existing_order:
            simulated_order = Order(
                customer_id=comm.customer_id,
                order_date=event_ts,
                total_amount=Decimal(random.randint(499, 2499)),
                attributed_communication_id=comm_id
            )
            db.add(simulated_order)
            db.flush() # Populate simulated_order.order_id

    # 4. Event precedence check — only advance, never downgrade
    current_rank = EVENT_RANK.get(comm.status, 0)
    incoming_rank = EVENT_RANK.get(event_type, 0)

    status_updated = False
    if incoming_rank > current_rank:
        comm.status = event_type
        status_updated = True

        # Set the specific timestamp field if applicable
        ts_field = EVENT_TIMESTAMP_FIELD.get(event_type)
        if ts_field:
            setattr(comm, ts_field, event_ts)

        logger.info(
            f"comm {comm_id}: status advanced {comm.status!r} → {event_type!r} "
            f"(rank {current_rank} → {incoming_rank})"
        )
    else:
        logger.info(
            f"comm {comm_id}: event '{event_type}' (rank {incoming_rank}) ignored — "
            f"current status '{comm.status}' (rank {current_rank}) is already higher"
        )

    # 5. Always append to audit trail regardless of precedence
    new_event = CommunicationEvent(
        communication_id=comm_id,
        event_type=event_type,
        event_timestamp=event_ts,
        metadata_json={
            "source": "channel-service",
            "status_updated": status_updated,
            "previous_status": comm.status if not status_updated else None,
            **(payload.metadata or {})
        }
    )
    db.add(new_event)
    db.commit()

    # 6. Trigger attribution in background — non-blocking
    # Attribution only runs for 'promo_applied', 'clicked', and 'purchased' events
    if event_type in ("promo_applied", "clicked", "purchased"):
        background_tasks.add_task(_run_attribution_bg, comm.campaign_id)

    return {
        "status": "accepted",
        "communication_id": str(comm_id),
        "event": event_type,
        "status_updated": status_updated,
        "current_status": comm.status
    }
