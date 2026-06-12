"""
Xenia CRM – Campaign, Communication, CommunicationEvent,
CampaignMetrics & CampaignSimulation Models
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime, Float, ForeignKey, Integer,
    Numeric, String, Text, func
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Campaign(Base):
    """
    A campaign represents a marketing initiative targeting a customer segment.
    Lifecycle: Draft → Review → Approved → Launched → Completed
    """
    __tablename__ = "campaigns"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    objective: Mapped[str | None] = mapped_column(Text)   # plain-text goal from user
    promotion_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("promotions.promotion_id", ondelete="SET NULL"),
        nullable=True,
    )
    channel: Mapped[str] = mapped_column(String(50), nullable=False)  # WhatsApp/Email/SMS
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="draft", index=True
    )  # draft|review|approved|launched|completed

    # ── AI-Generated Content ──────────────────────────────────────────────────
    ai_strategy: Mapped[dict | None] = mapped_column(JSONB)       # Full Xenia AI plan
    message_template: Mapped[str | None] = mapped_column(Text)    # Primary message
    message_variants: Mapped[list | None] = mapped_column(JSONB)  # A/B variants
    target_segment: Mapped[str | None] = mapped_column(String(200))
    target_audience_size: Mapped[int | None] = mapped_column(Integer)

    # ── Attribution ───────────────────────────────────────────────────────────
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("opportunities.opportunity_id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )
    launched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # ── Relationships ─────────────────────────────────────────────────────────
    promotion: Mapped["Promotion | None"] = relationship(
        "Promotion", back_populates="campaigns"
    )
    communications: Mapped[list["Communication"]] = relationship(
        "Communication", back_populates="campaign", lazy="select"
    )
    simulation: Mapped["CampaignSimulation | None"] = relationship(
        "CampaignSimulation", back_populates="campaign", uselist=False, lazy="select"
    )
    metrics: Mapped["CampaignMetrics | None"] = relationship(
        "CampaignMetrics", back_populates="campaign", uselist=False, lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Campaign name={self.name!r} status={self.status!r}>"


class Communication(Base):
    """
    Represents a single outbound message sent to one customer as part of a campaign.
    Status lifecycle: pending → sent → delivered → opened → clicked → promo_applied
    Purchases are NOT simulated here — they only occur via real order creation.
    """
    __tablename__ = "communications"

    communication_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campaigns.campaign_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.customer_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel: Mapped[str] = mapped_column(String(50))
    message_sent: Mapped[str | None] = mapped_column(Text)   # personalised message text

    # ── Status (event-precedence enforced in webhook handler) ─────────────────
    # pending | sent | delivered | opened | clicked | promo_applied | failed
    # NOTE: 'purchased' is NOT a communication status — it is tracked via Orders
    status: Mapped[str] = mapped_column(
        String(50), default="pending", index=True
    )

    # ── Delivery Timestamps (funnel timing analysis) ───────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    clicked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    promo_applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Dispatch Tracking ─────────────────────────────────────────────────────
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    external_message_id: Mapped[str | None] = mapped_column(String(200), nullable=True)  # carrier ref

    # ── Relationships ─────────────────────────────────────────────────────────
    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="communications")
    customer: Mapped["Customer"] = relationship("Customer", back_populates="communications")
    events: Mapped[list["CommunicationEvent"]] = relationship(
        "CommunicationEvent", back_populates="communication", lazy="select"
    )

    def __repr__(self) -> str:
        return (
            f"<Communication campaign={self.campaign_id} "
            f"customer={self.customer_id} status={self.status!r}>"
        )


class CommunicationEvent(Base):
    """
    Individual delivery lifecycle event for a communication.
    event_type: delivered | opened | clicked | purchased | failed
    """
    __tablename__ = "communication_events"

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    communication_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("communications.communication_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # delivered|opened|clicked|purchased|failed
    event_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)  # extra event context

    # ── Relationships ─────────────────────────────────────────────────────────
    communication: Mapped["Communication"] = relationship(
        "Communication", back_populates="events"
    )


class CampaignSimulation(Base):
    """
    Pre-launch simulation result generated by Xenia AI + rule engine.
    Predicts reach, CTR, CVR, and revenue impact with confidence score.
    Also stores explainability rationale and voice-eligibility stub (future phase).
    """
    __tablename__ = "campaign_simulations"

    simulation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campaigns.campaign_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    predicted_reach: Mapped[int | None] = mapped_column(Integer)
    predicted_ctr: Mapped[float | None] = mapped_column(Float)       # 0.0–1.0
    predicted_cvr: Mapped[float | None] = mapped_column(Float)       # 0.0–1.0
    predicted_revenue: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    confidence_score: Mapped[float | None] = mapped_column(Float)    # 0.0–1.0
    risk_factors: Mapped[list | None] = mapped_column(JSONB)
    simulation_context: Mapped[dict | None] = mapped_column(JSONB)   # inputs used
    ai_narrative: Mapped[str | None] = mapped_column(Text)           # Xenia AI explanation

    # ── Explainability (why this audience / promotion / channel) ──────────────
    why_audience: Mapped[str | None] = mapped_column(Text)
    why_promotion: Mapped[str | None] = mapped_column(Text)
    why_channel: Mapped[str | None] = mapped_column(Text)
    historical_performance_note: Mapped[str | None] = mapped_column(Text)

    # ── Voice Campaign — Future-Ready Placeholder ─────────────────────────────
    # Voice generation is NOT implemented in this phase.
    # This field reserves the architecture contract for Phase 2 voice integration.
    voice_eligible: Mapped[bool] = mapped_column(Integer, default=False)   # cast to bool in schema
    voice_ineligible_reason: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )

    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="simulation")


class CampaignMetrics(Base):
    """
    Post-launch actual performance metrics — updated by attribution engine.
    """
    __tablename__ = "campaign_metrics"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campaigns.campaign_id", ondelete="CASCADE"),
        primary_key=True,
    )
    total_sent: Mapped[int] = mapped_column(Integer, default=0)
    total_delivered: Mapped[int] = mapped_column(Integer, default=0)
    total_opened: Mapped[int] = mapped_column(Integer, default=0)
    total_clicked: Mapped[int] = mapped_column(Integer, default=0)
    total_purchased: Mapped[int] = mapped_column(Integer, default=0)
    total_failed: Mapped[int] = mapped_column(Integer, default=0)
    total_promo_applied: Mapped[int] = mapped_column(Integer, default=0)

    # ── Revenue Attribution ───────────────────────────────────────────────────
    attributed_revenue: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    estimated_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    roi: Mapped[float | None] = mapped_column(Float)       # percentage
    conversion_rate: Mapped[float | None] = mapped_column(Float)

    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )

    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="metrics")


# ── Circular import resolution ────────────────────────────────────────────────
from app.models.promotion import Promotion
from app.models.customer import Customer
from app.models.opportunity import Opportunity
