import os
import sys
import logging

# Add backend root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import db_session
from app.ml.train_churn import train_model
from app.services.ml_churn import MLChurnService

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("xenia.run_churn")

def main():
    logger.info("Initializing ML Churn Pipeline...")
    with db_session() as db:
        try:
            # 1. Train the model
            logger.info("Step 1: Training the Gradient Boosting Classifier...")
            model_path = train_model(db)
            logger.info(f"Model successfully saved to: {model_path}")
            
            # 2. Score all customers
            logger.info("Step 2: Scoring all customers in database...")
            scored_count = MLChurnService.predict_all_customers_churn(db)
            logger.info(f"Successfully scored {scored_count} customers!")
            
            # 3. Print sample of predictions
            from app.models.customer import CustomerMetrics
            sample = db.query(CustomerMetrics).filter(CustomerMetrics.churn_probability.isnot(None)).limit(5).all()
            logger.info("Sample churn predictions from database:")
            for m in sample:
                logger.info(
                    f"CustID: {m.customer_id} | "
                    f"RFM Value: {m.value_score} | "
                    f"Days since last order: {m.days_since_last_order} | "
                    f"ML Churn Probability: {m.churn_probability:.2%}"
                )
        except Exception as e:
            logger.error(f"Error during churn training/prediction: {e}", exc_info=True)

if __name__ == "__main__":
    main()
