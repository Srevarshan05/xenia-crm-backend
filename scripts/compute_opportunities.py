import os
import sys
import logging
from sqlalchemy import text

# Add backend root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import db_session
from app.services.opportunity import OpportunityDiscoveryService

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("xenia.run_opportunities")

def run():
    logger.info("Initializing Opportunity Discovery Run...")
    with db_session() as db:
        try:
            count = OpportunityDiscoveryService.discover_all_opportunities(db)
            logger.info(f"Discovery successful! Populated {count} active opportunities.")
            
            # Print active opportunities
            opportunities_query = text("""
                SELECT type, priority, audience_size, potential_revenue, recommended_channel
                FROM opportunities
                WHERE status = 'open'
                ORDER BY potential_revenue DESC
            """)
            ops = db.execute(opportunities_query).fetchall()
            
            print("\n" + "=" * 80)
            print("  DISCOVERED REVENUE & RETENTION OPPORTUNITIES")
            print("=" * 80)
            for idx, row in enumerate(ops):
                print(f"  Op #{idx+1:02d}: Type: {row.type:<25} | Priority: {row.priority:<8}")
                print(f"           Audience Size: {row.audience_size:<6} shoppers")
                print(f"           Channel: {row.recommended_channel or 'None (FATIGUE SHIELD)':<15}")
                print(f"           Projected Impact: INR {float(row.potential_revenue):,.2f}")
                print("-" * 80)
            print("=" * 80 + "\n")
            
        except Exception as e:
            logger.error(f"Error during opportunity discovery: {e}", exc_info=True)

if __name__ == "__main__":
    run()
