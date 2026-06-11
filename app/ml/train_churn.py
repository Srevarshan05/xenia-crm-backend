"""
Xenia CRM – Churn Model Training Pipeline
Trains a GradientBoostingClassifier to predict customer churn risk,
evaluates performance metrics, and saves the serialized pipeline (preprocessor + model).
"""

import os
import sys
import logging
import joblib
from sqlalchemy.orm import Session
from sklearn.model_selection import train_test_split
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.pipeline import Pipeline
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score

# Add backend root to path if running directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.config import settings
from app.database import db_session
from app.ml.feature_engineering import prepare_training_data, get_preprocessor

# Setup logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("xenia.ml.train_churn")


def train_model(db: Session) -> str:
    """
    Trains a Gradient Boosting model to predict churn, logs evaluations,
    and serializes the entire pipeline to settings.churn_model_path.
    """
    logger.info("Initializing churn model training process...")
    
    # 1. Prepare data
    X, y, _ = prepare_training_data(db)
    
    # Check class balance
    churn_rate = y.mean()
    logger.info(f"Loaded dataset: {len(X)} rows. Overall churn rate: {churn_rate:.2%}")

    # 2. Train-test split
    # Stratify by y to ensure balanced split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    logger.info(f"Split size: Train={len(X_train)} | Test={len(X_test)}")

    # 3. Build training pipeline
    preprocessor = get_preprocessor()
    model = GradientBoostingClassifier(
        n_estimators=100,
        learning_rate=0.1,
        max_depth=4,
        random_state=42
    )
    
    clf_pipeline = Pipeline(steps=[
        ('preprocessor', preprocessor),
        ('classifier', model)
    ])

    # 4. Train pipeline
    logger.info("Fitting GradientBoostingClassifier pipeline...")
    clf_pipeline.fit(X_train, y_train)

    # 5. Evaluate
    y_pred = clf_pipeline.predict(X_test)
    y_prob = clf_pipeline.predict_proba(X_test)[:, 1]

    accuracy = accuracy_score(y_test, y_pred)
    precision = precision_score(y_test, y_pred)
    recall = recall_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred)
    roc_auc = roc_auc_score(y_test, y_prob)

    logger.info("=" * 40)
    logger.info("  MODEL EVALUATION RESULTS")
    logger.info("=" * 40)
    logger.info(f"  Accuracy:  {accuracy:.4f}")
    logger.info(f"  Precision: {precision:.4f}")
    logger.info(f"  Recall:    {recall:.4f}")
    logger.info(f"  F1 Score:  {f1:.4f}")
    logger.info(f"  ROC AUC:   {roc_auc:.4f}")
    logger.info("=" * 40)

    # 6. Save model pipeline
    model_path = settings.churn_model_path
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    
    logger.info(f"Saving serialized pipeline model to {model_path}...")
    joblib.dump(clf_pipeline, model_path)
    logger.info("Model training and serialization complete.")
    
    return model_path


if __name__ == "__main__":
    with db_session() as db:
        train_model(db)
