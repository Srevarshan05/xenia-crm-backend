"""
Xenia CRM – Opportunity Model
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Float, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Opportunity(Base):
    """
    Revenue and engagement opportunity discovered by the Opportunity Discovery Engine.
    Enriched with Xenia AI explanation, action plan, and confidence score.
    """
    __tablename__ = "opportunities"

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # ── Opportunity Classification ────────────────────────────────────────────
    type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # win_back | cross_sell | engaged_non_buyer | revenue_risk | category_growth
    description: Mapped[str | None] = mapped_column(Text)

    # ── Audience ──────────────────────────────────────────────────────────────
    audience_size: Mapped[int | None] = mapped_column(Integer)
    segment_filter: Mapped[dict | None] = mapped_column(JSONB)  # query params used
    customer_ids_sample: Mapped[list | None] = mapped_column(JSONB)  # first 10 IDs

    # ── Financial Impact ──────────────────────────────────────────────────────
    potential_revenue: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))

    # ── Prioritisation ────────────────────────────────────────────────────────
    priority: Mapped[str] = mapped_column(
        String(20), default="medium", index=True
    )  # high | medium | low

    # ── Xenia AI Enrichment ───────────────────────────────────────────────────
    ai_explanation: Mapped[str | None] = mapped_column(Text)
    ai_action_plan: Mapped[str | None] = mapped_column(Text)
    ai_context: Mapped[dict | None] = mapped_column(JSONB)       # structured context sent to AI
    confidence_score: Mapped[float | None] = mapped_column(Float)  # 0.0–1.0
    key_drivers: Mapped[list | None] = mapped_column(JSONB)      # ["churn spike", "high aov"]
    recommended_promotion_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("promotions.promotion_id", ondelete="SET NULL"),
        nullable=True,
    )
    recommended_channel: Mapped[str | None] = mapped_column(String(50))

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        String(50), default="open", index=True
    )  # open | in_progress | resolved | dismissed
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # ── Relationships ─────────────────────────────────────────────────────────
    campaigns: Mapped[list["Campaign"]] = relationship(
        "Campaign",
        foreign_keys="Campaign.opportunity_id",
        back_populates=None,
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"<Opportunity type={self.type!r} priority={self.priority!r} "
            f"audience={self.audience_size}>"
        )


# ── Circular import resolution ────────────────────────────────────────────────
from app.models.campaign import Campaign
