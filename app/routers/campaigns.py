"""
Xenia CRM – Campaigns Router
Full campaign lifecycle: draft → reviewed → awaiting_approval → approved → launched → completed

Campaign Dispatch Flow:
  POST /launch → creates Communication records → queues dispatch as BackgroundTask → returns 202
  BackgroundTask → sends batches to Service B → Service B fires webhook callbacks back to Xenia
  Webhooks → update Communication status with event precedence → trigger attribution
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List
import uuid
from uuid import UUID
import logging
from datetime import datetime, timezone
import io
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors

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
    query = db.query(Campaign).filter(~Campaign.channel.in_(["Voice", "Voice Call"]))
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


def generate_executive_summary(campaign, metrics):
    if not metrics:
        return "This campaign has not been launched yet. No performance metrics are available to summarize the outcome."
    
    purchases = metrics.total_purchased or 0
    revenue = float(metrics.attributed_revenue or 0)
    cost = float(metrics.estimated_cost or 0)
    roi = float(metrics.roi or 0)
    conv_rate = float(metrics.conversion_rate or 0) * 100
    sent = metrics.total_sent or 1
    opened = metrics.total_opened or 0
    clicked = metrics.total_clicked or 0
    
    promo_code = campaign.promotion.promo_code if campaign.promotion else "None"
    channel = campaign.channel
    segment = campaign.target_segment or "selected segment"
    
    summary = (
        f"The campaign '{campaign.name}' was launched targeting {sent} customers in the '{segment}' segment via {channel}. "
        f"The campaign featured the '{promo_code}' promotion. "
    )
    
    if purchases > 0:
        summary += (
            f"The initiative successfully generated a total of INR {revenue:,.2f} in attributed revenue from {purchases} completed purchases. "
            f"With a campaign dispatch cost of INR {cost:,.2f}, the campaign achieved a conversion rate of {conv_rate:.1f}% and a return on investment (ROI) of {roi:.1f}%. "
        )
    else:
        summary += (
            f"No purchases have been attributed to this campaign yet. "
        )
        
    if sent > 0:
        delivered_pct = (metrics.total_delivered or 0) / sent * 100
        opened_pct = opened / sent * 100
        clicked_pct = clicked / sent * 100
        summary += (
            f"In terms of engagement, the campaign recorded a delivery rate of {delivered_pct:.1f}%, an open rate of {opened_pct:.1f}%, and a click-through rate of {clicked_pct:.1f}%."
        )
        
    return summary


def build_pdf_report(campaign, metrics, filename_or_stream):
    c = canvas.Canvas(filename_or_stream, pagesize=letter)
    width, height = letter # 612 x 792
    
    # Colors
    primary_color = colors.HexColor("#0f172a") # Navy Dark Slate
    accent_color = colors.HexColor("#7c3aed") # Purple
    text_color = colors.HexColor("#334155") # Gray
    light_bg = colors.HexColor("#f8fafc") # Slate Light
    border_color = colors.HexColor("#e2e8f0") # Border gray
    
    # Draw header banner
    c.setFillColor(primary_color)
    c.rect(0, 720, 612, 72, fill=True, stroke=False)
    
    # Header Title
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(36, 750, "XENIA CRM — CAMPAIGN PERFORMANCE REPORT")
    c.setFont("Helvetica", 9)
    c.drawString(36, 735, "PREMIUM ANALYTICS LOG & BUSINESS OUTCOME SUMMARY")
    
    # Date generated
    c.drawRightString(576, 745, f"Date: {datetime.now().strftime('%b %d, %Y')}")
    
    # Section 1: Campaign Metadata
    c.setFillColor(primary_color)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(36, 685, "CAMPAIGN INFORMATION")
    c.setStrokeColor(border_color)
    c.setLineWidth(1)
    c.line(36, 678, 576, 678)
    
    # Left Column
    c.setFillColor(text_color)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(36, 655, "Campaign Name:")
    c.drawString(36, 635, "Objective:")
    c.drawString(36, 600, "Target Segment:")
    c.drawString(36, 580, "Outreach Channel:")
    
    c.setFont("Helvetica", 9)
    c.drawString(140, 655, campaign.name or "N/A")
    obj_text = campaign.objective or "N/A"
    if len(obj_text) > 80:
        c.drawString(140, 635, obj_text[:80] + "...")
    else:
        c.drawString(140, 635, obj_text)
    c.drawString(140, 600, campaign.target_segment or "General")
    c.drawString(140, 580, campaign.channel or "N/A")
    
    # Right Column
    c.setFont("Helvetica-Bold", 9)
    c.drawString(340, 655, "Campaign ID:")
    c.drawString(340, 635, "Launch Date:")
    c.drawString(340, 600, "Audience Size:")
    c.drawString(340, 580, "Campaign Status:")
    
    c.setFont("Helvetica", 9)
    c.drawString(440, 655, str(campaign.campaign_id)[:18] + "...")
    launch_str = campaign.launched_at.strftime('%Y-%m-%d %H:%M') if campaign.launched_at else "N/A"
    c.drawString(440, 635, launch_str)
    c.drawString(440, 600, str(campaign.target_audience_size or 0))
    status_str = (campaign.status or "N/A").upper()
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(accent_color if campaign.status in ["launched", "completed"] else text_color)
    c.drawString(440, 580, status_str)
    
    # Section 2: Performance metrics
    c.setFillColor(primary_color)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(36, 545, "PERFORMANCE SUMMARY")
    c.line(36, 538, 576, 538)
    
    # Draw simple metrics table
    c.setFillColor(light_bg)
    c.rect(36, 435, 540, 90, fill=True, stroke=True)
    c.setStrokeColor(border_color)
    
    # Draw vertical grid lines
    c.line(126, 435, 126, 525)
    c.line(216, 435, 216, 525)
    c.line(306, 435, 306, 525)
    c.line(396, 435, 396, 525)
    c.line(486, 435, 486, 525)
    
    # Header row
    c.setFillColor(primary_color)
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(81, 510, "SENT")
    c.drawCentredString(171, 510, "DELIVERED")
    c.drawCentredString(261, 510, "OPENED")
    c.drawCentredString(351, 510, "CLICKED")
    c.drawCentredString(441, 510, "PROMO APPL.")
    c.drawCentredString(531, 510, "PURCHASED")
    
    # Values row
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(text_color)
    sent_val = metrics.total_sent if metrics else 0
    deliv_val = metrics.total_delivered if metrics else 0
    open_val = metrics.total_opened if metrics else 0
    click_val = metrics.total_clicked if metrics else 0
    promo_val = metrics.total_promo_applied if metrics else 0
    purch_val = metrics.total_purchased if metrics else 0
    
    c.drawCentredString(81, 470, str(sent_val))
    c.drawCentredString(171, 470, str(deliv_val))
    c.drawCentredString(261, 470, str(open_val))
    c.drawCentredString(351, 470, str(click_val))
    c.drawCentredString(441, 470, str(promo_val))
    c.drawCentredString(531, 470, str(purch_val))
    
    # Percentages row
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#64748b"))
    c.drawCentredString(81, 450, "100.0%")
    c.drawCentredString(171, 450, f"{(deliv_val/max(1, sent_val)*100):.1f}%")
    c.drawCentredString(261, 450, f"{(open_val/max(1, sent_val)*100):.1f}%")
    c.drawCentredString(351, 450, f"{(click_val/max(1, sent_val)*100):.1f}%")
    c.drawCentredString(441, 450, f"{(promo_val/max(1, sent_val)*100):.1f}%")
    c.drawCentredString(531, 450, f"{(purch_val/max(1, sent_val)*100):.1f}%")
    
    # Section 3: Revenue Metrics & ROI
    c.setFillColor(primary_color)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(36, 400, "REVENUE METRICS")
    c.line(36, 393, 576, 393)
    
    revenue_val = float(metrics.attributed_revenue or 0) if metrics else 0.0
    cost_val = float(metrics.estimated_cost or 0) if metrics else 0.0
    conversion_rate = float(metrics.conversion_rate or 0) * 100 if metrics else 0.0
    roi = float(metrics.roi or 0) if metrics else 0.0
    
    c.setFillColor(text_color)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(36, 370, "Revenue Generated:")
    c.drawString(36, 350, "Campaign Dispatch Cost:")
    c.drawString(36, 330, "Conversion Rate:")
    c.drawString(36, 310, "Estimated Return on Investment (ROI):")
    
    c.setFont("Helvetica-Bold", 9)
    c.drawString(240, 370, f"INR {revenue_val:,.2f}")
    c.drawString(240, 350, f"INR {cost_val:,.2f}")
    c.drawString(240, 330, f"{conversion_rate:.2f}%")
    c.setFillColor(colors.HexColor("#16a34a") if roi >= 0 else colors.HexColor("#dc2626"))
    c.drawString(240, 310, f"{roi:.2f}%")
    
    # Section 4: Promotion Information
    c.setFillColor(primary_color)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(36, 275, "PROMOTION INFORMATION")
    c.line(36, 268, 576, 268)
    
    promo_name = "None"
    promo_code = "None"
    promo_usage = 0
    if campaign.promotion:
        promo_name = campaign.promotion.name
        promo_code = campaign.promotion.promo_code
        promo_usage = promo_val
        
    c.setFillColor(text_color)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(36, 245, "Promotion Used:")
    c.drawString(36, 225, "Promo Code:")
    c.drawString(36, 205, "Promo Usage / Claim Count:")
    
    c.setFont("Helvetica", 9)
    c.drawString(200, 245, promo_name)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(200, 225, promo_code)
    c.setFont("Helvetica", 9)
    c.drawString(200, 205, str(promo_usage))
    
    # Section 5: Executive Summary
    c.setFillColor(primary_color)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(36, 170, "EXECUTIVE SUMMARY")
    c.line(36, 163, 576, 163)
    
    summary_text = generate_executive_summary(campaign, metrics)
    c.setFillColor(light_bg)
    c.rect(36, 60, 540, 85, fill=True, stroke=True)
    
    c.setFillColor(text_color)
    c.setFont("Helvetica", 9)
    # Wrap text inside the box
    lines = []
    words = summary_text.split(" ")
    curr_line = ""
    for w in words:
        if len(curr_line + " " + w) > 95:
            lines.append(curr_line)
            curr_line = w
        else:
            curr_line = (curr_line + " " + w).strip()
    if curr_line:
        lines.append(curr_line)
        
    y_pos = 130
    for line in lines[:5]:
        c.drawString(46, y_pos, line)
        y_pos -= 14
        
    # Footer
    c.setStrokeColor(border_color)
    c.line(36, 40, 576, 40)
    c.setFillColor(colors.HexColor("#94a3b8"))
    c.setFont("Helvetica", 8)
    c.drawString(36, 26, "Xenia CRM Platform © 2026. Generated Automatically.")
    c.drawRightString(576, 26, "Page 1 of 1")
    
    c.showPage()
    c.save()


@router.get("/{campaign_id}/report")
def export_campaign_report(campaign_id: UUID, db: Session = Depends(get_db)):
    """
    GET /api/campaigns/{campaign_id}/report
    Generates and downloads a premium PDF performance report for a campaign.
    """
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
        
    metrics = campaign.metrics
    
    buffer = io.BytesIO()
    build_pdf_report(campaign, metrics, buffer)
    buffer.seek(0)
    
    sanitized_name = "".join(x for x in campaign.name if x.isalnum() or x in " -_").strip()
    filename = f"campaign_report_{sanitized_name or 'export'}.pdf"
    
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
