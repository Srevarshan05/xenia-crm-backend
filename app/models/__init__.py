"""
Xenia CRM – Models Package
Imports all models so SQLAlchemy metadata is populated
before Alembic runs migrations.
"""

from app.models.customer import Customer, CustomerMetrics, CustomerSegment, CustomerInsights
from app.models.product import Product
from app.models.order import Order, OrderItem
from app.models.promotion import Promotion
from app.models.campaign import Campaign, Communication, CommunicationEvent, CampaignSimulation, CampaignMetrics
from app.models.opportunity import Opportunity
from app.models.briefing import DailyBriefing, NLQuery

__all__ = [
    "Customer",
    "CustomerMetrics",
    "CustomerSegment",
    "CustomerInsights",
    "Product",
    "Order",
    "OrderItem",
    "Promotion",
    "Campaign",
    "Communication",
    "CommunicationEvent",
    "CampaignSimulation",
    "CampaignMetrics",
    "Opportunity",
    "DailyBriefing",
    "NLQuery",
]
