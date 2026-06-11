from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import logging

from app.database import get_db
from app.services.xenia_ai import XeniaAIService
from app.schemas.analytics import NLQueryRequest, NLQueryResponse
from app.models.briefing import NLQuery

logger = logging.getLogger("xenia.analytics_router")
router = APIRouter(prefix="/api/analytics", tags=["NL Analytics"])

@router.post("/query", response_model=NLQueryResponse)
def execute_nl_query(payload: NLQueryRequest, db: Session = Depends(get_db)):
    """
    POST /api/analytics/query
    Accepts a natural language question, parses it to SQL using Xenia AI (Gemini),
    executes it safely, and returns the natural language response + data + chart suggestion.
    """
    try:
        new_query = XeniaAIService.execute_natural_language_query(db, payload.question)
        return new_query
    except Exception as e:
        logger.error(f"Failed to execute NL query: {e}")
        raise HTTPException(status_code=500, detail=f"AI query parsing failed: {str(e)}")

@router.get("/history", response_model=List[NLQueryResponse])
def get_query_history(limit: int = 20, db: Session = Depends(get_db)):
    """
    GET /api/analytics/history
    Retrieve audit log history of recently executed NL queries.
    """
    queries = db.query(NLQuery).order_by(NLQuery.created_at.desc()).limit(limit).all()
    return queries
