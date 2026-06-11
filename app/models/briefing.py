"""
Xenia CRM – Daily Briefing & NL Query Audit Models
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Float, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DailyBriefing(Base):
    """
    AI-generated daily business briefing, produced nightly by the scheduler
    and displayed on the dashboard every morning.
    """
    __tablename__ = "daily_briefings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    briefing_date: Mapped[date] = mapped_column(Date, nullable=False, unique=True, index=True)

    # ── Summary Fields ────────────────────────────────────────────────────────
    headline: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    opportunities_count: Mapped[int] = mapped_column(Integer, default=0)
    at_risk_count: Mapped[int] = mapped_column(Integer, default=0)
    recoverable_revenue: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))

    # ── Full Structured Content ───────────────────────────────────────────────
    # Contains: opportunities[], risks[], recommended_actions[], market_pulse
    full_content: Mapped[dict | None] = mapped_column(JSONB)

    # ── Metadata ──────────────────────────────────────────────────────────────
    confidence_score: Mapped[float | None] = mapped_column(Float)
    model_version: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )

    def __repr__(self) -> str:
        return f"<DailyBriefing date={self.briefing_date} headline={self.headline!r:.40}>"


class NLQuery(Base):
    """
    Audit log for all Natural Language Analytics queries.
    Tracks every question asked, the context sent to Xenia AI, and the response.
    Useful for improving AI quality and auditing.
    """
    __tablename__ = "nl_queries"

    query_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(
        String(100), index=True
    )  # revenue_analysis|segment_lookup|category_trend|churn_lookup|channel_analysis
    context_json: Mapped[dict | None] = mapped_column(JSONB)  # structured data sent to AI
    response: Mapped[str | None] = mapped_column(Text)        # AI-generated answer
    data_points: Mapped[list | None] = mapped_column(JSONB)   # supporting data
    chart_suggestion: Mapped[str | None] = mapped_column(String(100))  # bar|line|pie
    confidence_score: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), index=True
    )

    def __repr__(self) -> str:
        return f"<NLQuery intent={self.intent!r} question={self.question!r:.40}>"
