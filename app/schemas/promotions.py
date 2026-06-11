from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from decimal import Decimal
from uuid import UUID

class PromotionCreate(BaseModel):
    name: str
    description: Optional[str] = None
    promo_code: str
    discount_type: str = "Percentage" # Percentage, Fixed Amount, Free Shipping, etc.
    discount_value: Decimal = Decimal("0.00")
    applicable_categories: str = "ALL"
    applicable_cities: str = "ALL"
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    max_usage_limit: Optional[int] = None
    min_order_value: Optional[Decimal] = None
    active: bool = True

class PromotionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    promo_code: Optional[str] = None
    discount_type: Optional[str] = None
    discount_value: Optional[Decimal] = None
    applicable_categories: Optional[str] = None
    applicable_cities: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    max_usage_limit: Optional[int] = None
    min_order_value: Optional[Decimal] = None
    active: Optional[bool] = None

class PromotionResponse(BaseModel):
    promotion_id: UUID
    name: str
    description: Optional[str] = None
    promo_code: Optional[str] = None
    discount_type: str
    discount_value: Decimal
    applicable_categories: str
    applicable_cities: str
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    max_usage_limit: Optional[int] = None
    min_order_value: Optional[Decimal] = None
    active: bool
    
    # Performance metrics
    times_used: int
    times_recommended: int
    purchases_attributed: int
    revenue_generated: Decimal
    roi_generated: Optional[float] = 0.0

    class Config:
        from_attributes = True
