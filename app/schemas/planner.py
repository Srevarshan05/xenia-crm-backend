from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from decimal import Decimal
from datetime import datetime

class GoalPlannerRequest(BaseModel):
    goal: str

class SimulationPreview(BaseModel):
    predicted_reach: int
    predicted_ctr: float
    predicted_cvr: float
    predicted_revenue: Decimal
    confidence_score: float
    risk_factors: List[str]
    ai_narrative: str

class PromotionPreview(BaseModel):
    promotion_id: str
    name: str
    promo_code: str
    discount_percentage: float
    min_order_value: Optional[float] = None
    discount_type: Optional[str] = "Percentage"
    discount_value: Optional[float] = 0.0
    applicable_categories: Optional[str] = "ALL"
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

class CampaignStrategyExplanation(BaseModel):
    why_audience: str
    why_now: str
    why_channel: str
    why_promotion: str

class AudienceSummary(BaseModel):
    total_identified: int
    suppressed: int
    eligible: int
    avg_spend: float
    avg_inactivity_days: int
    city_distribution: Dict[str, int]
    channel_distribution: Dict[str, int]
    category_affinity_distribution: Dict[str, float]

class ShopperPreview(BaseModel):
    customer_id: str
    name: str
    city: str
    email: str
    phone: str
    lifetime_value: float
    last_purchase_days: int
    churn_probability: float
    preferred_channel: str

class PromotionRecommendation(BaseModel):
    promotion_id: str
    name: str
    promo_code: str
    discount_type: str
    discount_value: float
    applicable_categories: str
    applicable_cities: str
    min_order_value: Optional[float] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    rationale: List[str]

class PrepareContextResponse(BaseModel):
    audience_summary: AudienceSummary
    recommended_promotion: Optional[PromotionRecommendation] = None
    eligible_shoppers: List[ShopperPreview] = []

class GoalPlannerResponse(BaseModel):
    goal: str
    parsed_filters: Dict[str, Any]
    campaign_name: str
    target_segment: str
    channel: str
    message_template: str
    message_variants: List[str]
    recommended_promotion: Optional[PromotionPreview] = None
    simulation: SimulationPreview
    confidence_score: float
    ai_explanation: CampaignStrategyExplanation
    audience_summary: AudienceSummary
    eligible_shoppers: List[ShopperPreview] = []
    
    # Channel specific copy
    whatsapp_template: str
    whatsapp_variants: List[str]
    email_subject: str
    email_subject_variants: List[str]
    email_template: str
    email_variants: List[str]
    sms_template: str
    sms_variants: List[str]
