import os
import sys
import logging
from sqlalchemy import text

# Add backend root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import db_session
from app.services.segmentation import SegmentationService

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("xenia.run_segmentation")

def run():
    logger.info("Initializing Segmentation Engine Run...")
    with db_session() as db:
        try:
            count = SegmentationService.run_segmentation(db)
            logger.info(f"Segmentation run successful! Assigned {count} segment links.")
            
            # Print segment distributions
            distribution_query = text("""
                SELECT segment_name, COUNT(*) as customer_count
                FROM customer_segments
                GROUP BY segment_name
                ORDER BY customer_count DESC
            """)
            dist = db.execute(distribution_query).fetchall()
            
            print("\n" + "=" * 40)
            print("  CUSTOMER SEGMENT DISTRIBUTIONS")
            print("=" * 40)
            for row in dist:
                print(f"  {row.segment_name:<25} : {row.customer_count} customers")
            print("=" * 40 + "\n")
            
        except Exception as e:
            logger.error(f"Error during customer segmentation: {e}", exc_info=True)

if __name__ == "__main__":
    run()
