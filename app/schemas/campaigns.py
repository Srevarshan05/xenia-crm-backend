from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime
from decimal import Decimal
from uuid import UUID

class CampaignCreate(BaseModel):
    name: str
    objective: Optional[str] = None
    promotion_id: Optional[UUID] = None
    channel: str
    target_segment: str
    message_template: Optional[str] = None
    message_variants: Optional[List[str]] = None
    target_audience_size: Optional[int] = None

class CampaignStatusUpdate(BaseModel):
    status: str  # draft | review | approved | launched | completed

class PromotionDetail(BaseModel):
    promotion_id: UUID
    name: str
    promo_code: str
    discount_percentage: float
    min_order_value: Optional[float] = None

class SimulationDetail(BaseModel):
    simulation_id: UUID
    predicted_reach: int
    predicted_ctr: float
    predicted_cvr: float
    predicted_revenue: Decimal
    confidence_score: float
    risk_factors: List[str]
    ai_narrative: str
    created_at: datetime

class MetricsDetail(BaseModel):
    total_sent: int
    total_delivered: int
    total_opened: int
    total_clicked: int
    total_purchased: int
    total_failed: int
    total_promo_applied: int
    attributed_revenue: Decimal
    estimated_cost: Decimal
    roi: Optional[float] = None
    conversion_rate: Optional[float] = None
    last_updated: datetime

class CampaignResponse(BaseModel):
    campaign_id: UUID
    name: str
    objective: Optional[str] = None
    promotion_id: Optional[UUID] = None
    channel: str
    status: str
    ai_strategy: Optional[Dict[str, Any]] = None
    message_template: Optional[str] = None
    message_variants: Optional[List[str]] = None
    target_segment: Optional[str] = None
    target_audience_size: Optional[int] = None
    opportunity_id: Optional[UUID] = None
    created_at: datetime
    launched_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    promotion: Optional[PromotionDetail] = None
    simulation: Optional[SimulationDetail] = None
    metrics: Optional[MetricsDetail] = None

    class Config:
        from_attributes = True
