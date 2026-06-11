"""
Xenia CRM – ML Churn Feature Engineering
Extracts customer features from the database for ML training and prediction.
Avoids data leakage by excluding current recency (days_since_last_order) from predictors,
since churn is defined as a function of recency.
"""

import logging
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.pipeline import Pipeline

logger = logging.getLogger("xenia.ml.feature_engineering")

# Define features used in prediction to avoid data leakage
NUMERICAL_FEATURES = [
    "total_orders",
    "total_spend",
    "avg_order_value",
    "orders_prev_90d",
    "engagement_score"
]

CATEGORICAL_FEATURES = [
    "preferred_channel",
    "top_category",
    "city"
]


def extract_raw_features(db: Session) -> pd.DataFrame:
    """
    Query database to build a raw features dataframe.
    Combines Customer, CustomerMetrics, and campaign engagement stats.
    """
    logger.info("Extracting raw feature set from database...")
    query = text("""
        SELECT 
            c.customer_id,
            c.city,
            m.total_orders,
            m.total_spend,
            m.avg_order_value,
            m.orders_prev_90d,
            m.days_since_last_order,
            m.engagement_score,
            COALESCE(m.preferred_channel, 'WhatsApp') as preferred_channel,
            COALESCE(m.top_category, 'Groceries') as top_category
        FROM customers c
        JOIN customer_metrics m ON c.customer_id = m.customer_id
    """)
    records = db.execute(query).fetchall()
    
    df = pd.DataFrame([
        {
            "customer_id": str(r.customer_id),
            "city": r.city or "Unknown",
            "total_orders": r.total_orders or 0,
            "total_spend": float(r.total_spend or 0.0),
            "avg_order_value": float(r.avg_order_value or 0.0),
            "orders_prev_90d": r.orders_prev_90d or 0,
            "days_since_last_order": r.days_since_last_order or 0,
            "engagement_score": float(r.engagement_score or 0.0),
            "preferred_channel": r.preferred_channel,
            "top_category": r.top_category
        }
        for r in records
    ])
    
    logger.info(f"Extracted {len(df)} customer records for ML processing.")
    return df


def get_preprocessor() -> ColumnTransformer:
    """
    Creates a scikit-learn preprocessing pipeline.
    Scales numerical features and one-hot encodes categorical features.
    """
    numeric_transformer = Pipeline(steps=[
        ('scaler', StandardScaler())
    ])
    
    # handle_unknown='ignore' is critical so that new cities/categories in inference
    # do not break the deployed model.
    categorical_transformer = Pipeline(steps=[
        ('onehot', OneHotEncoder(handle_unknown='ignore', sparse_output=False))
    ])
    
    preprocessor = ColumnTransformer(
        transformers=[
            ('num', numeric_transformer, NUMERICAL_FEATURES),
            ('cat', categorical_transformer, CATEGORICAL_FEATURES)
        ]
    )
    return preprocessor


def prepare_training_data(db: Session, churn_threshold_days: int = 90) -> tuple[pd.DataFrame, pd.Series, list[str]]:
    """
    Prepares X (features) and y (target) for training.
    Target variable y is 1 if days_since_last_order > churn_threshold_days, else 0.
    Returns:
        X: pd.DataFrame of raw features
        y: pd.Series of binary targets
        customer_ids: list of customer_id strings
    """
    df = extract_raw_features(db)
    if df.empty:
        raise ValueError("Cannot prepare training data: customer metrics table is empty.")

    # Target: 1 if customer has churned (inactive for > churn_threshold_days), 0 otherwise
    y = (df["days_since_last_order"] > churn_threshold_days).astype(int)
    
    # Features (X) excludes customer_id, days_since_last_order (leakage), and other direct outcomes
    X = df[NUMERICAL_FEATURES + CATEGORICAL_FEATURES]
    customer_ids = df["customer_id"].tolist()
    
    return X, y, customer_ids
