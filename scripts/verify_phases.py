import os
import sys
import json
import logging
from sqlalchemy import text

# Add backend root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import db_session
from app.config import settings

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("xenia.verify")

def run_verification():
    logger.info("Starting Xenia CRM Phase 1-6 Verification...")
    errors = 0
    
    with db_session() as db:
        # Check 1: Churn Probabilities
        logger.info("Checking Churn Probabilities...")
        total_metrics = db.execute(text("SELECT COUNT(*) FROM customer_metrics")).scalar()
        null_churn_prob = db.execute(text("SELECT COUNT(*) FROM customer_metrics WHERE churn_probability IS NULL")).scalar()
        
        if total_metrics != 10000:
            logger.error(f"FAIL: Expected 10000 customer metrics rows, found {total_metrics}")
            errors += 1
        else:
            logger.info("PASS: 10000 customer metrics rows found.")
            
        if null_churn_prob > 0:
            logger.error(f"FAIL: Found {null_churn_prob} rows with NULL churn_probability")
            errors += 1
        else:
            logger.info("PASS: Churn probabilities populated for all customers.")
            
        # Check 2: Segment Assignments
        logger.info("Checking Segment Assignments...")
        segment_count = db.execute(text("SELECT COUNT(*) FROM customer_segments")).scalar()
        unique_customers_with_segments = db.execute(text("SELECT COUNT(DISTINCT customer_id) FROM customer_segments")).scalar()
        
        if segment_count == 0:
            logger.error("FAIL: No customer segments found.")
            errors += 1
        else:
            logger.info(f"PASS: {segment_count} segment associations synced for {unique_customers_with_segments} unique customers.")
            
        # Check 3: Basket Affinity Rules
        logger.info("Checking Basket Affinity Rules...")
        rules_path = os.path.join("app", "ml", "basket_rules.json")
        if not os.path.exists(rules_path):
            logger.error(f"FAIL: Basket rules file does not exist at {rules_path}")
            errors += 1
        else:
            try:
                with open(rules_path, "r") as f:
                    rules = json.load(f)
                if len(rules) == 0:
                    logger.error("FAIL: Basket rules file is empty.")
                    errors += 1
                else:
                    logger.info(f"PASS: Basket affinity rules successfully loaded ({len(rules)} rules found).")
            except Exception as e:
                logger.error(f"FAIL: Error loading basket rules: {e}")
                errors += 1
                
        # Check 4: Scheduler jobs dry-run imports
        logger.info("Verifying Scheduler Job definitions...")
        try:
            from app.scheduler import run_intelligence_metrics, start_scheduler, stop_scheduler
            logger.info("PASS: Scheduler module and jobs import successfully.")
        except Exception as e:
            logger.error(f"FAIL: Scheduler import/configuration error: {e}")
            errors += 1

        # Check 5: Database Indexes for Opportunities queries
        logger.info("Checking Opportunity Indexes...")
        index_query = text("""
            SELECT indexname 
            FROM pg_indexes 
            WHERE tablename = 'opportunities';
        """)
        idx_results = db.execute(index_query).fetchall()
        indexes = [r.indexname for r in idx_results]
        
        expected_indexes = ['ix_opportunities_priority', 'ix_opportunities_status', 'ix_opportunities_type']
        for exp_idx in expected_indexes:
            if exp_idx not in indexes:
                logger.error(f"FAIL: Expected index {exp_idx} was not found on table opportunities")
                errors += 1
            else:
                logger.info(f"PASS: Index {exp_idx} is active.")

    if errors == 0:
        print("\n" + "=" * 50)
        print("  [OK] ALL CHECKS PASSED SUCCESSFULLY!")
        print("  Ready to proceed to Phase 7: Opportunity Discovery.")
        print("=" * 50 + "\n")
    else:
        print("\n" + "=" * 50)
        print(f"  [FAIL] VERIFICATION FAILED WITH {errors} ERRORS.")
        print("=" * 50 + "\n")

if __name__ == "__main__":
    run_verification()
