from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from uuid import UUID
import logging
from datetime import datetime, timezone
import random

from app.database import get_db
from app.models.campaign import Campaign, Communication, CommunicationEvent
from app.models.order import Order, OrderItem
from app.models.product import Product
from app.models.customer import CustomerMetrics
from app.services.attribution import RevenueAttributionService

logger = logging.getLogger("xenia.webhooks")
router = APIRouter(prefix="/api/webhook", tags=["Webhooks"])

class WebhookDeliveryPayload(BaseModel):
    communication_id: UUID
    event_type: str  # delivered | opened | clicked | purchased | failed

@router.post("/delivery")
def handle_delivery_webhook(payload: WebhookDeliveryPayload, db: Session = Depends(get_db)):
    """
    POST /api/webhook/delivery
    Callback endpoint triggered by the channel-service messaging stub.
    Tracks communication delivery lifecycle events and updates campaigns.
    """
    comm_id = payload.communication_id
    event_type = payload.event_type.lower()
    
    logger.info(f"Received webhook callback for communication {comm_id} - event: {event_type}")
    
    # 1. Fetch communication
    comm = db.query(Communication).filter(Communication.communication_id == comm_id).first()
    if not comm:
        raise HTTPException(status_code=404, detail=f"Communication {comm_id} not found.")
        
    # 2. Save communication event
    new_event = CommunicationEvent(
        communication_id=comm_id,
        event_type=event_type,
        event_timestamp=datetime.now(timezone.utc),
        metadata_json={"source": "channel-service"}
    )
    db.add(new_event)
    
    # 3. Update communication status
    comm.status = event_type
    db.commit()
    
    # 4. Special logic for purchased: simulate a PostgreSQL order event
    if event_type == "purchased":
        logger.info(f"Simulating retail purchase order for customer {comm.customer_id}")
        
        # Get customer's top category to pick a relevant product
        cust_metric = db.query(CustomerMetrics).filter(CustomerMetrics.customer_id == comm.customer_id).first()
        top_cat = cust_metric.top_category if cust_metric else None
        
        # Pick a product
        product_query = db.query(Product)
        if top_cat:
            product_query = product_query.filter(Product.category == top_cat)
        product = product_query.order_by(func.random()).first()
        
        if not product:
            product = db.query(Product).first()
            
        if product:
            # Create Order
            quantity = random.randint(1, 2)
            total_amount = product.price * quantity
            
            new_order = Order(
                customer_id=comm.customer_id,
                order_date=datetime.now(timezone.utc),
                total_amount=total_amount,
                attributed_communication_id=comm_id
            )
            db.add(new_order)
            db.commit()
            db.refresh(new_order)
            
            # Create OrderItem
            new_order_item = OrderItem(
                order_id=new_order.order_id,
                product_id=product.product_id,
                quantity=quantity,
                unit_price=product.price
            )
            db.add(new_order_item)
            db.commit()
            logger.info(f"Successfully simulated order {new_order.order_id} with revenue {total_amount:.2f}")
            
    # 5. Run attribution to update CampaignMetrics in real-time
    RevenueAttributionService.run_attribution_pipeline(db, campaign_id=comm.campaign_id)
    
    return {"status": "success", "communication_id": comm_id, "event": event_type}
