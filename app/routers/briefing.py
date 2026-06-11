from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from typing import List
import logging

from app.database import get_db
from app.services.xenia_ai import XeniaAIService
from app.schemas.analytics import BriefingResponse
from app.models.briefing import DailyBriefing

logger = logging.getLogger("xenia.briefing_router")
router = APIRouter(prefix="/api/briefing", tags=["Daily Briefing"])


def _generate_briefing_bg(db: Session):
    """Background task: generate today's briefing without blocking the request."""
    try:
        XeniaAIService.generate_daily_briefing(db)
        logger.info("Background briefing generation completed.")
    except Exception as e:
        logger.error(f"Background briefing generation failed: {e}")


@router.get("/latest", response_model=BriefingResponse)
def get_latest_briefing(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    GET /api/briefing/latest
    Returns the latest daily executive briefing INSTANTLY from cache.
    If today's briefing is missing, returns the most recent one and
    schedules a background generation — does NOT block the response.
    """
    today_date = datetime.now(timezone.utc).date()

    # First: try to return today's briefing (instant DB read)
    briefing = db.query(DailyBriefing).filter(DailyBriefing.briefing_date == today_date).first()

    if briefing:
        return briefing

    # No briefing for today — return most recent cached one immediately
    latest = db.query(DailyBriefing).order_by(DailyBriefing.briefing_date.desc()).first()

    if latest:
        # Schedule background generation for today's briefing (non-blocking)
        background_tasks.add_task(_generate_briefing_bg, db)
        logger.info(f"No briefing for {today_date}. Returning cached ({latest.briefing_date}). Generating in background.")
        return latest

    # Truly no briefing exists at all — generate synchronously (first-time setup only)
    logger.info("No briefing found at all. Generating first briefing synchronously...")
    try:
        briefing = XeniaAIService.generate_daily_briefing(db)
        return briefing
    except Exception as e:
        logger.error(f"Failed to generate first briefing: {e}")
        raise HTTPException(status_code=503, detail="Briefing service temporarily unavailable. Please try again shortly.")


@router.get("/history", response_model=List[BriefingResponse])
def get_briefing_history(limit: int = 14, db: Session = Depends(get_db)):
    """
    GET /api/briefing/history
    Retrieve the historical record of daily briefings.
    """
    briefings = db.query(DailyBriefing).order_by(DailyBriefing.briefing_date.desc()).limit(limit).all()
    return briefings
