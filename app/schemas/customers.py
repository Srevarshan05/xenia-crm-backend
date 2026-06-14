from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime
from uuid import UUID

class CustomerResponse(BaseModel):
    customer_id: UUID
    name: str
    email: str
    phone: Optional[str] = None
    city: Optional[str] = None
    join_date: datetime
    total_spend: Optional[float] = None
    churn_probability: Optional[float] = None

    class Config:
        from_attributes = True

class CustomerMetricsResponse(BaseModel):
    customer_id: UUID
    r_score: Optional[int] = None
    f_score: Optional[int] = None
    m_score: Optional[int] = None
    value_score: Optional[float] = None
    churn_probability: Optional[float] = None
    engagement_score: Optional[float] = None
    preferred_channel: Optional[str] = None
    top_category: Optional[str] = None
    category_affinity_json: Optional[Dict[str, float]] = None
    total_orders: Optional[int] = None
    total_spend: Optional[float] = None
    avg_order_value: Optional[float] = None
    days_since_last_order: Optional[int] = None
    orders_last_90d: Optional[int] = None
    orders_prev_90d: Optional[int] = None
    last_updated: datetime

    class Config:
        from_attributes = True

class CustomerInsightsResponse(BaseModel):
    customer_id: UUID
    ai_persona: Optional[str] = None
    persona_description: Optional[str] = None
    summary: Optional[str] = None
    risks: Optional[List[str]] = None
    recommendations: Optional[List[str]] = None
    confidence_score: Optional[float] = None
    model_version: Optional[str] = None
    last_updated: datetime

    class Config:
        from_attributes = True

class CustomerSegmentResponse(BaseModel):
    segment_name: str
    assigned_at: datetime

    class Config:
        from_attributes = True
