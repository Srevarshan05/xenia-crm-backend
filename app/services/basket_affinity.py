"""
Xenia CRM – Basket Affinity Analysis
Implements transaction association rule mining using FP-Growth and mlxtend.
Discovers product co-occurrences and exposes cross-sell recommendations.
"""

import os
import json
import logging
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session
from mlxtend.frequent_patterns import fpgrowth, association_rules

from app.config import settings

logger = logging.getLogger("xenia.basket_affinity")

RULES_CACHE_PATH = os.path.join("app", "ml", "basket_rules.json")


class BasketAffinityService:
    _cached_rules = None

    @classmethod
    def load_rules(cls) -> list:
        """Loads mined association rules from cache if available."""
        if cls._cached_rules is not None:
            return cls._cached_rules

        if os.path.exists(RULES_CACHE_PATH):
            try:
                with open(RULES_CACHE_PATH, "r") as f:
                    cls._cached_rules = json.load(f)
                logger.info(f"Loaded {len(cls._cached_rules)} basket affinity rules from cache.")
                return cls._cached_rules
            except Exception as e:
                logger.error(f"Failed to read basket rules cache: {e}")

        return []

    @classmethod
    def calculate_basket_affinities(cls, db: Session, min_support: float = 0.005, min_confidence: float = 0.1) -> int:
        """
        Extracts transaction baskets, computes association rules using FP-Growth,
        saves the resulting rules to a JSON file, and caches them in memory.
        """
        logger.info("Starting Basket Affinity analysis (FP-Growth)...")
        
        # 1. Fetch order items grouping by order and category
        query = text("""
            SELECT 
                oi.order_id,
                p.category as product_name
            FROM order_items oi
            JOIN products p ON oi.product_id = p.product_id
        """)
        records = db.execute(query).fetchall()
        
        if not records:
            logger.warning("No order items found. Cannot run basket affinity.")
            return 0

        # Convert to pandas DataFrame
        df = pd.DataFrame([{"order_id": str(r.order_id), "product_name": r.product_name} for r in records])
        
        # 2. Pivot to transaction one-hot encoded matrix
        logger.info("Building transaction matrix...")
        basket = (df.groupby(['order_id', 'product_name'])['product_name']
                  .count().unstack().reset_index().fillna(0)
                  .set_index('order_id'))
        
        # Convert counts to boolean (0 or 1)
        basket_sets = basket.map(lambda x: x > 0)
        
        logger.info(f"Transaction matrix shape: {basket_sets.shape}")

        # 3. Apply FP-Growth to find frequent itemsets
        logger.info(f"Running FP-Growth with min_support={min_support}...")
        frequent_itemsets = fpgrowth(basket_sets, min_support=min_support, use_colnames=True)
        
        if frequent_itemsets.empty:
            logger.warning("No frequent itemsets found. Adjust min_support.")
            cls._cached_rules = []
            return 0

        logger.info(f"Found {len(frequent_itemsets)} frequent itemsets. Generating association rules...")

        # 4. Generate association rules
        rules = association_rules(frequent_itemsets, metric="lift", min_threshold=1.0)
        
        if rules.empty:
            logger.warning("No association rules found matching lift threshold.")
            cls._cached_rules = []
            return 0

        # Filter rules by confidence
        rules = rules[rules["confidence"] >= min_confidence]
        
        # Sort by lift desc
        rules = rules.sort_values(by="lift", ascending=False)
        
        logger.info(f"Discovered {len(rules)} association rules. Formatting for serialization...")

        # 5. Format and save to JSON
        formatted_rules = []
        for idx, row in rules.iterrows():
            antecedents = list(row["antecedents"])
            consequents = list(row["consequents"])
            
            formatted_rules.append({
                "antecedents": antecedents,
                "consequents": consequents,
                "support": float(row["support"]),
                "confidence": float(row["confidence"]),
                "lift": float(row["lift"])
            })

        # Ensure directory exists
        os.makedirs(os.path.dirname(RULES_CACHE_PATH), exist_ok=True)
        
        with open(RULES_CACHE_PATH, "w") as f:
            json.dump(formatted_rules, f, indent=2)

        cls._cached_rules = formatted_rules
        logger.info(f"Saved {len(formatted_rules)} basket affinity rules to {RULES_CACHE_PATH}")
        return len(formatted_rules)

    @classmethod
    def get_cross_sell_recommendations(cls, product_name: str, limit: int = 3) -> list[dict]:
        """
        Gets list of recommended products to buy along with the specified product.
        Returns:
            list of dicts containing recommended product names and confidence/lift metrics
        """
        rules = cls.load_rules()
        recommendations = []
        
        for rule in rules:
            # Check if specified product is in antecedents and rule has 1 consequent
            if product_name in rule["antecedents"]:
                for item in rule["consequents"]:
                    if item != product_name:
                        recommendations.append({
                            "recommended_product": item,
                            "confidence": rule["confidence"],
                            "lift": rule["lift"],
                            "rule_trigger": ", ".join(rule["antecedents"])
                        })
        
        # Sort by lift then confidence
        recommendations = sorted(recommendations, key=lambda x: (x["lift"], x["confidence"]), reverse=True)
        
        # De-duplicate recommended products, keeping the highest lift rule
        seen = set()
        deduped = []
        for r in recommendations:
            if r["recommended_product"] not in seen:
                seen.add(r["recommended_product"])
                deduped.append(r)
                if len(deduped) >= limit:
                    break
                    
        return deduped
