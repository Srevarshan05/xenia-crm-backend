"""
Xenia CRM – Daily Nightly Sync Runner
Runs the entire daily sync pipeline in sequence:
1. Intelligence Engine (RFM, Churn probability, category affinity metrics)
2. Segmentation Engine (Rule-based shopper cohort assignments)
3. Opportunity Discovery Engine (AI-native and rules-based campaign discovery)
"""

import os
import sys
import logging

# Add backend root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import db_session
from app.services.intelligence import IntelligenceService
from app.services.segmentation import SegmentationService
from app.services.opportunity import OpportunityDiscoveryService

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("xenia.nightly_sync")


def run_pipeline():
    logger.info("=================================================================")
    logger.info("  STARTING XENIA CRM DAILY NIGHTLY SYNC PIPELINE")
    logger.info("=================================================================")
    
    with db_session() as db:
        try:
            # 1. Customer Metrics Sync (RFM, Churn, Affinities)
            logger.info("Step 1/3: Computing customer RFM metrics, Churn risk, and affinities...")
            metrics_count = IntelligenceService.calculate_rfm_metrics(db)
            logger.info(f"[SUCCESS] Calculated customer metrics for {metrics_count} customers.")
            
            # 2. Cohorts Segment Rule Engine Sync
            logger.info("Step 2/3: Evaluating shopper segment classification rule engine...")
            segment_count = SegmentationService.run_segmentation(db)
            logger.info(f"[SUCCESS] Assigned {segment_count} customer segment memberships.")
            
            # 3. Campaign Opportunities discovery
            logger.info("Step 3/3: Running marketing and suppression opportunity discovery...")
            opp_count = OpportunityDiscoveryService.discover_all_opportunities(db)
            logger.info(f"[SUCCESS] Populated {opp_count} campaign suggestions in the database.")
            
            logger.info("=================================================================")
            logger.info("  CRM NIGHTLY PIPELINE COMPLETED SUCCESSFULLY!")
            logger.info("=================================================================")
            
        except Exception as e:
            logger.error(f"[FATAL] Nightly sync failed during execution: {e}", exc_info=True)
            sys.exit(1)


if __name__ == "__main__":
    run_pipeline()
