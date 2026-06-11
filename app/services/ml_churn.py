"""
Xenia CRM – ML Churn Prediction Service
Loads the trained ML churn model and scores customers with their churn probabilities,
saving the predictions to the customer_metrics database table.
"""

import os
import logging
import joblib
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.ml.feature_engineering import extract_raw_features, NUMERICAL_FEATURES, CATEGORICAL_FEATURES
from app.models.customer import CustomerMetrics

logger = logging.getLogger("xenia.services.ml_churn")


class MLChurnService:
    _model_pipeline = None

    @classmethod
    def load_model(cls):
        """Loads and caches the model pipeline from disk."""
        if cls._model_pipeline is None:
            model_path = settings.churn_model_path
            if not os.path.exists(model_path):
                raise FileNotFoundError(
                    f"ML Churn model not found at {model_path}. "
                    f"Please run the model training script first: python app/ml/train_churn.py"
                )
            logger.info(f"Loading ML Churn model pipeline from {model_path}...")
            cls._model_pipeline = joblib.load(model_path)
        return cls._model_pipeline

    @classmethod
    def clear_cache(cls):
        """Clears the cached model pipeline (useful if model is retrained)."""
        cls._model_pipeline = None

    @classmethod
    def predict_all_customers_churn(cls, db: Session) -> int:
        """
        Extracts features for all customers, predicts churn probabilities using
        the serialized model, and updates the customer_metrics table in bulk.
        """
        logger.info("Starting batch churn probability prediction...")
        
        # 1. Load model pipeline
        try:
            model = cls.load_model()
        except FileNotFoundError as e:
            logger.error(str(e))
            logger.info("Model not trained yet. Retrying automatic training...")
            # Automatically train model if not present (self-healing architecture)
            from app.ml.train_churn import train_model
            train_model(db)
            model = cls.load_model()

        # 2. Extract features
        df = extract_raw_features(db)
        if df.empty:
            logger.warning("No customers found in database to score.")
            return 0

        X = df[NUMERICAL_FEATURES + CATEGORICAL_FEATURES]
        customer_ids = df["customer_id"].tolist()

        # 3. Predict churn probabilities
        logger.info("Running model inference...")
        probabilities = model.predict_proba(X)[:, 1]

        # 4. Bulk update customer_metrics with predicted churn probability
        logger.info("Updating churn probabilities in database...")
        update_query = text("""
            UPDATE customer_metrics
            SET churn_probability = :churn_prob
            WHERE customer_id = :customer_id
        """)

        # Build update payloads
        payload = [
            {"churn_prob": float(prob), "customer_id": cust_id}
            for cust_id, prob in zip(customer_ids, probabilities)
        ]

        # Execute updates in batches of 1000
        batch_size = 1000
        for i in range(0, len(payload), batch_size):
            db.execute(update_query, payload[i:i + batch_size])
        
        db.commit()
        logger.info(f"Successfully scored and updated churn probabilities for {len(payload)} customers.")
        return len(payload)
