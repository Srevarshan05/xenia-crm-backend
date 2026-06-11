import os
import sys
import logging

# Add backend root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import db_session
from app.services.intelligence import IntelligenceService

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("xenia.run_intelligence")

def run():
    logger.info("Initializing Intelligence Engine Run...")
    with db_session() as db:
        try:
            records_count = IntelligenceService.calculate_rfm_metrics(db)
            logger.info(f"Intelligence run successful! Processed {records_count} customers.")
            
            # Print a quick sample of the computed metrics
            from app.models.customer import CustomerMetrics
            sample = db.query(CustomerMetrics).limit(5).all()
            logger.info("Sample metrics from database:")
            for m in sample:
                logger.info(
                    f"CustID: {m.customer_id} | RFM: {m.r_score}{m.f_score}{m.m_score} | "
                    f"Value: {m.value_score} | Churn Score: {m.churn_score} | Top Cat: {m.top_category} | "
                    f"Pref Channel: {m.preferred_channel} | Spend: {m.total_spend}"
                )
        except Exception as e:
            logger.error(f"Error during intelligence metrics computation: {e}", exc_info=True)

if __name__ == "__main__":
    run()
