from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import logging
from uuid import UUID

from app.database import get_db
from app.models.opportunity import Opportunity
from app.models.promotion import Promotion
from app.schemas.opportunities import OpportunityResponse
from app.services.xenia_ai import XeniaAIService

logger = logging.getLogger("xenia.opportunities_router")
router = APIRouter(prefix="/api/opportunities", tags=["Opportunities"])

@router.get("", response_model=List[OpportunityResponse])
def list_opportunities(status: str = None, db: Session = Depends(get_db)):
    """
    GET /api/opportunities
    List all opportunities with optional status filter.
    """
    query = db.query(Opportunity)
    if status:
        query = query.filter(Opportunity.status == status)
    opportunities = query.order_by(Opportunity.potential_revenue.desc()).all()
    
    # Resolve recommended promotion codes
    promos = {p.promotion_id: p.promo_code for p in db.query(Promotion).all()}
    for op in opportunities:
        if op.recommended_promotion_id:
            op.recommended_promotion_code = promos.get(op.recommended_promotion_id)
        else:
            op.recommended_promotion_code = None
            
    return opportunities

@router.get("/{opportunity_id}", response_model=OpportunityResponse)
def get_opportunity(opportunity_id: UUID, db: Session = Depends(get_db)):
    """
    GET /api/opportunities/{opportunity_id}
    Retrieve opportunity details. Automatically triggers AI explanation enrichment
    if it hasn't been generated yet.
    """
    op = db.query(Opportunity).filter(Opportunity.opportunity_id == opportunity_id).first()
    if not op:
        raise HTTPException(status_code=404, detail="Opportunity not found")
        
    if not op.ai_explanation:
        logger.info(f"Opportunity {opportunity_id} has no AI explanation. Enriching on-the-fly...")
        try:
            op = XeniaAIService.explain_opportunity(db, opportunity_id)
        except Exception as e:
            logger.error(f"Failed to dynamically enrich opportunity: {e}")
            
    if op.recommended_promotion_id:
        promo = db.query(Promotion).filter(Promotion.promotion_id == op.recommended_promotion_id).first()
        op.recommended_promotion_code = promo.promo_code if promo else None
    else:
        op.recommended_promotion_code = None
        
    return op

@router.post("/{opportunity_id}/explain", response_model=OpportunityResponse)
def enrich_opportunity(opportunity_id: UUID, db: Session = Depends(get_db)):
    """
    POST /api/opportunities/{opportunity_id}/explain
    Forces Xenia AI to generate/regenerate the explanation, action plan, and confidence score.
    """
    op = db.query(Opportunity).filter(Opportunity.opportunity_id == opportunity_id).first()
    if not op:
        raise HTTPException(status_code=404, detail="Opportunity not found")
        
    try:
        op = XeniaAIService.explain_opportunity(db, opportunity_id)
        return op
    except Exception as e:
        logger.error(f"Failed to explain opportunity: {e}")
        raise HTTPException(status_code=500, detail="Gemini enrichment failed.")
