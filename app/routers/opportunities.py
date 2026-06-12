"""
Xenia CRM – Suggested Actions Router
Exposes AI-discovered revenue opportunities as actionable "Suggested Actions"
to CRM users. The internal DB table remains 'opportunities' for data continuity.

Terminology:
  Internal: opportunity / opportunities (DB, models)
  External: suggested_action / suggested_actions (API responses, frontend)
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import logging
from uuid import UUID
from datetime import datetime

from app.database import get_db
from app.models.opportunity import Opportunity
from app.models.promotion import Promotion
from app.schemas.opportunities import OpportunityResponse
from app.services.xenia_ai import XeniaAIService

logger = logging.getLogger("xenia.suggested_actions_router")

# Keep URL prefix as /api/opportunities for backward compat (frontend already uses this)
# Tag and documentation use "Suggested Actions" terminology
router = APIRouter(prefix="/api/opportunities", tags=["Suggested Actions"])


def _enrich_response(op: Opportunity, db: Session) -> dict:
    """
    Serialise an Opportunity into a frontend-friendly Suggested Action dict.
    Adds: recommended promotion details, historical performance, and why it was generated.
    """
    # Resolve recommended promotion details
    recommended_promotion = None
    if op.recommended_promotion_id:
        promo = db.query(Promotion).filter(
            Promotion.promotion_id == op.recommended_promotion_id
        ).first()
        if promo:
            recommended_promotion = {
                "promotion_id": str(promo.promotion_id),
                "name": promo.name,
                "promo_code": promo.promo_code,
                "discount_type": promo.discount_type,
                "discount_value": float(promo.discount_value),
                "discount_percentage": float(promo.discount_percentage),
                "applicable_categories": promo.applicable_categories,
                "applicable_cities": promo.applicable_cities,
                "start_date": promo.start_date,
                "end_date": promo.end_date,
                "active": promo.active,
                # Historical performance
                "historical_performance": {
                    "times_used": promo.times_used,
                    "times_recommended": promo.times_recommended,
                    "purchases_attributed": promo.purchases_attributed,
                    "revenue_generated": float(promo.revenue_generated),
                    "roi_generated": float(promo.roi_generated or 0.0),
                }
            }

    # Build explainability context from stored fields + key_drivers
    key_drivers = op.key_drivers or []
    why_generated = op.ai_explanation or _build_why_generated(op, key_drivers)

    return {
        # Suggested Action identity (frontend uses "suggested_action" language)
        "suggested_action_id": str(op.opportunity_id),
        "suggested_action_type": _humanize_type(op.type),
        "internal_type": op.type,
        "description": op.description,

        # Audience signals
        "audience_size": op.audience_size,
        "potential_revenue": float(op.potential_revenue) if op.potential_revenue else None,
        "recommended_channel": op.recommended_channel,

        # Priority & confidence
        "priority": op.priority,
        "confidence_score": op.confidence_score,
        "key_drivers": key_drivers,

        # Explainability
        "why_generated": why_generated,
        "action_plan": op.ai_action_plan,

        # Recommended promotion (user-created, Xenia only recommends)
        "recommended_promotion": recommended_promotion,

        # Lifecycle
        "status": op.status,
        "created_at": op.created_at,
        "resolved_at": op.resolved_at,

        # Keep opportunity_id for backward compat with existing frontend references
        "opportunity_id": str(op.opportunity_id),
    }


def _humanize_type(type_key: str) -> str:
    """Convert internal type key to user-facing Suggested Action label."""
    mapping = {
        "win_back": "Bring Back VIP Shoppers",
        "winback": "Bring Back VIP Shoppers",
        "cross_sell": "Repeat Purchase Booster",
        "engaged_non_buyer": "Loyal Shopper Appreciation Offer",
        "revenue_risk": "Inactive Customer Recovery Program",
        "category_growth": "Beauty Category Growth Campaign",
        "reactivation": "High Value Customer Re-engagement",
        "upsell": "Premium Customer Retention Campaign",
        "channel_push": "WhatsApp Offer for Frequent Buyers",
        "fatigue_suppression": "Premium Customer Retention Campaign",
    }
    return mapping.get(type_key, type_key.replace("_", " ").title())



def _build_why_generated(op: Opportunity, key_drivers: list) -> str:
    """Build a plain-English explanation if AI explanation is not yet available."""
    parts = []
    if op.audience_size:
        parts.append(f"{op.audience_size} shoppers match this pattern.")
    if key_drivers:
        parts.append("Key signals: " + ", ".join(str(d) for d in key_drivers[:3]) + ".")
    if op.potential_revenue:
        parts.append(f"Estimated recovery potential: ₹{float(op.potential_revenue):,.0f}.")
    return " ".join(parts) if parts else "Discovered via nightly intelligence scan."


@router.get("", summary="List all Suggested Actions")
def list_suggested_actions(status: str = None, db: Session = Depends(get_db)):
    """
    GET /api/opportunities
    Returns all Suggested Actions (AI-discovered revenue opportunities).
    Each card includes: why it was generated, audience size, recommended promotion,
    confidence score, and recommended channel.
    """
    query = db.query(Opportunity)
    if status:
        query = query.filter(Opportunity.status == status)
    opportunities = query.order_by(Opportunity.potential_revenue.desc()).all()

    return [_enrich_response(op, db) for op in opportunities]


@router.get("/{opportunity_id}", summary="Get Suggested Action detail")
def get_suggested_action(opportunity_id: UUID, db: Session = Depends(get_db)):
    """
    GET /api/opportunities/{opportunity_id}
    Returns full Suggested Action detail. Auto-enriches with AI explanation
    if not yet generated.
    """
    op = db.query(Opportunity).filter(Opportunity.opportunity_id == opportunity_id).first()
    if not op:
        raise HTTPException(status_code=404, detail="Suggested Action not found")

    # Auto-enrich with AI explanation if missing
    if not op.ai_explanation:
        logger.info(f"Suggested Action {opportunity_id}: generating AI explanation on demand...")
        try:
            op = XeniaAIService.explain_opportunity(db, opportunity_id)
        except Exception as e:
            logger.error(f"Failed to enrich Suggested Action {opportunity_id}: {e}")

    return _enrich_response(op, db)


@router.post("/{opportunity_id}/explain", summary="Refresh AI explanation")
def refresh_explanation(opportunity_id: UUID, db: Session = Depends(get_db)):
    """
    POST /api/opportunities/{opportunity_id}/explain
    Forces Xenia AI to regenerate the explanation and confidence score
    for this Suggested Action.
    """
    op = db.query(Opportunity).filter(Opportunity.opportunity_id == opportunity_id).first()
    if not op:
        raise HTTPException(status_code=404, detail="Suggested Action not found")

    try:
        op = XeniaAIService.explain_opportunity(db, opportunity_id)
        return _enrich_response(op, db)
    except Exception as e:
        logger.error(f"Failed to refresh explanation for {opportunity_id}: {e}")
        raise HTTPException(status_code=500, detail=f"AI enrichment failed: {str(e)}")
