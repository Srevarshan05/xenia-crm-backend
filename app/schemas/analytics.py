from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime, date
from decimal import Decimal
from uuid import UUID

class NLQueryRequest(BaseModel):
    question: str

class NLQueryResponse(BaseModel):
    query_id: UUID
    question: str
    intent: Optional[str] = None
    response: str
    data_points: Optional[List[Dict[str, Any]]] = None
    chart_suggestion: Optional[str] = None
    confidence_score: float
    created_at: datetime

class BriefingResponse(BaseModel):
    id: int
    briefing_date: date
    headline: str
    opportunities_count: int
    at_risk_count: int
    recoverable_revenue: Decimal
    full_content: Dict[str, Any]
    confidence_score: float
    created_at: datetime

    class Config:
        from_attributes = True
