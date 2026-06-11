import os
import sys
import logging

# Add backend root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import db_session
from app.services.basket_affinity import BasketAffinityService

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("xenia.run_basket_affinity")

def run():
    logger.info("Initializing Basket Affinity Run...")
    with db_session() as db:
        try:
            # We use support 0.005 and confidence 0.1 for discovery
            rules_count = BasketAffinityService.calculate_basket_affinities(db, min_support=0.005, min_confidence=0.1)
            logger.info(f"Basket affinity run successful! Discovered {rules_count} association rules.")
            
            # Load and display top 10 rules
            rules = BasketAffinityService.load_rules()
            print("\n" + "=" * 60)
            print(f"  TOP 10 BASKET AFFINITY RULES (Total: {len(rules)})")
            print("=" * 60)
            for idx, r in enumerate(rules[:10]):
                antecedents = ", ".join(r["antecedents"])
                consequents = ", ".join(r["consequents"])
                print(f"  Rule #{idx+1:02d}: [{antecedents}] ---> [{consequents}]")
                print(f"           Support: {r['support']:.4f} | Confidence: {r['confidence']:.4f} | Lift: {r['lift']:.2f}\n")
            print("=" * 60 + "\n")
            
            # Test recommendations
            if rules:
                test_item = rules[0]["antecedents"][0]
                recs = BasketAffinityService.get_cross_sell_recommendations(test_item, limit=3)
                print(f"Cross-sell test for '{test_item}':")
                for r in recs:
                    print(f"  --> Recommend: {r['recommended_product']} (Confidence: {r['confidence']:.2%}, Lift: {r['lift']:.2f})")
                print()
                
        except Exception as e:
            logger.error(f"Error during basket affinity mining: {e}", exc_info=True)

if __name__ == "__main__":
    run()
