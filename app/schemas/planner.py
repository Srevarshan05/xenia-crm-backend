"""
Xenia CRM – Planner Schemas
Campaign planning request/response models for the AI Goal Planner.
Includes audience summary, promotion recommendation with explainability,
simulation preview, channel-specific copy, and voice eligibility stub.
"""

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
    """
    Explainability block — every field explains a specific recommendation decision.
    Surfaced in the Campaign Review screen so users understand Xenia's reasoning.
    """
    why_audience: str   # Why this group of shoppers was selected
    why_now: str        # Why this is the right time to act
    why_channel: str    # Why this channel was recommended
    why_promotion: str  # Why this promotion was selected (includes historical performance)


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
    city: Optional[str] = None
    email: str
    phone: Optional[str] = None
    lifetime_value: float
    last_purchase_days: int
    churn_probability: float
    preferred_channel: str
    top_category: Optional[str] = None
    total_orders: Optional[int] = None


class PromotionRecommendation(BaseModel):
    """
    Promotion recommendation with full explainability.
    Xenia recommends from user-created promotions in DB — it never creates promotions.
    """
    promotion_id: str
    name: str
    promo_code: Optional[str] = None
    discount_type: str
    discount_value: float
    applicable_categories: str
    applicable_cities: str
    applicable_segments: Optional[str] = "ALL"
    min_order_value: Optional[float] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    # Why this promotion was selected
    rationale: List[str] = []

    # Historical performance data supporting the recommendation
    historical_performance: Optional[Dict[str, Any]] = None


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

    # Full explainability (why audience, channel, promotion)
    ai_explanation: CampaignStrategyExplanation
    audience_summary: AudienceSummary
    eligible_shoppers: List[ShopperPreview] = []

    # Channel-specific copy
    whatsapp_template: str = ""
    whatsapp_variants: List[str] = []
    email_subject: str = ""
    email_subject_variants: List[str] = []
    email_template: str = ""
    email_variants: List[str] = []
    sms_template: str = ""
    sms_variants: List[str] = []

    # Voice eligibility — future-ready stub (Phase 2 not implemented)
    # Returns True/False so frontend can optionally show "Voice campaign eligible" badge
    voice_eligible: bool = False
    voice_ineligible_reason: Optional[str] = None
