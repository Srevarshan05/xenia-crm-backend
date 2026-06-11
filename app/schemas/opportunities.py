from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime
from decimal import Decimal
from uuid import UUID

class OpportunityResponse(BaseModel):
    opportunity_id: UUID
    type: str
    description: Optional[str] = None
    audience_size: int
    potential_revenue: Decimal
    priority: str
    status: str
    recommended_channel: Optional[str] = None
    recommended_promotion_id: Optional[UUID] = None
    recommended_promotion_code: Optional[str] = None
    key_drivers: Optional[List[str]] = None
    customer_ids_sample: Optional[List[str]] = None
    ai_explanation: Optional[str] = None
    ai_action_plan: Optional[str] = None
    confidence_score: Optional[float] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
