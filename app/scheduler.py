"""
Xenia CRM – Background Job Scheduler
Configures and manages cron-style background jobs for metrics calculation,
opportunity discovery, ML retraining, and daily briefings.
"""

import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.database import db_session

logger = logging.getLogger("xenia.scheduler")

# Instantiate singleton background scheduler
scheduler = BackgroundScheduler()


def run_intelligence_metrics():
    """Trigger the customer metrics calculation engine."""
    from app.services.intelligence import IntelligenceService
    logger.info("Scheduler: Starting customer intelligence calculation job...")
    with db_session() as db:
        try:
            count = IntelligenceService.calculate_rfm_metrics(db)
            logger.info(f"Scheduler: Customer intelligence calculation completed. Updated {count} customers.")
        except Exception as e:
            logger.error(f"Scheduler: Error during customer metrics update: {e}", exc_info=True)


def run_ml_churn_retrain():
    """Retrain the ML churn prediction model."""
    from app.ml.train_churn import train_model
    logger.info("Scheduler: Starting weekly ML Churn Model retraining job...")
    with db_session() as db:
        try:
            model_path = train_model(db)
            logger.info(f"Scheduler: ML Churn model successfully retrained and saved to {model_path}.")
        except Exception as e:
            logger.error(f"Scheduler: Error during ML Churn retraining: {e}", exc_info=True)


def run_opportunity_discovery():
    """Trigger the opportunity discovery engine."""
    from app.services.opportunity import OpportunityDiscoveryService
    logger.info("Scheduler: Starting nightly opportunity discovery job...")
    with db_session() as db:
        try:
            count = OpportunityDiscoveryService.discover_all_opportunities(db)
            logger.info(f"Scheduler: Discovered {count} active opportunities.")
        except Exception as e:
            logger.error(f"Scheduler: Error during opportunity discovery: {e}", exc_info=True)


def run_daily_briefing():
    """Generate the daily AI-native briefing for the retail team."""
    from app.services.xenia_ai import XeniaAIService
    logger.info("Scheduler: Starting daily briefing generation job...")
    with db_session() as db:
        try:
            briefing = XeniaAIService.generate_daily_briefing(db)
            logger.info(f"Scheduler: Daily Briefing generated successfully: {briefing.headline}")
        except Exception as e:
            logger.error(f"Scheduler: Error generating daily briefing: {e}", exc_info=True)



def start_scheduler():
    """Initialise and start the background scheduler."""
    if not scheduler.running:
        # 1. Recalculate customer metrics (nightly at 02:00 IST by default)
        scheduler.add_job(
            run_intelligence_metrics,
            trigger=CronTrigger(hour=settings.intelligence_hour_ist, minute=0, timezone="Asia/Kolkata"),
            id="nightly_customer_intelligence",
            replace_existing=True,
        )

        # 2. Retrain ML Churn Model weekly (every Sunday at 03:00 IST by default)
        scheduler.add_job(
            run_ml_churn_retrain,
            trigger=CronTrigger(day_of_week="sun", hour=3, minute=0, timezone="Asia/Kolkata"),
            id="weekly_ml_churn_retrain",
            replace_existing=True,
        )

        # 3. Discover opportunities (nightly at 02:30 IST by default)
        scheduler.add_job(
            run_opportunity_discovery,
            trigger=CronTrigger(hour=settings.intelligence_hour_ist, minute=30, timezone="Asia/Kolkata"),
            id="nightly_opportunity_discovery",
            replace_existing=True,
        )

        # 4. Generate daily briefing (daily at 06:00 IST by default)
        scheduler.add_job(
            run_daily_briefing,
            trigger=CronTrigger(hour=settings.briefing_hour_ist, minute=0, timezone="Asia/Kolkata"),
            id="daily_ai_briefing",
            replace_existing=True,
        )

        scheduler.start()
        logger.info("Scheduler started successfully.")
    else:
        logger.warning("Scheduler is already running.")


def stop_scheduler():
    """Shut down the background scheduler."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler shut down successfully.")
    else:
        logger.warning("Scheduler is not running.")
