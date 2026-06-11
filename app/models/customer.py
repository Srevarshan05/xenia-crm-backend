"""
Xenia CRM – Customer & Customer Metrics Models
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Index,
    Integer, String, Text, func
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING

from app.database import Base

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.campaign import Communication


class Customer(Base):
    __tablename__ = "customers"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(20))
    city: Mapped[str | None] = mapped_column(String(100), index=True)
    join_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    orders: Mapped[list["Order"]] = relationship(
        "Order", back_populates="customer", lazy="select"
    )
    metrics: Mapped["CustomerMetrics | None"] = relationship(
        "CustomerMetrics", back_populates="customer", uselist=False, lazy="select"
    )
    insights: Mapped["CustomerInsights | None"] = relationship(
        "CustomerInsights", back_populates="customer", uselist=False, lazy="select"
    )
    segments: Mapped[list["CustomerSegment"]] = relationship(
        "CustomerSegment", back_populates="customer", lazy="select"
    )
    communications: Mapped[list["Communication"]] = relationship(
        "Communication", back_populates="customer", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Customer id={self.customer_id} name={self.name!r}>"


class CustomerMetrics(Base):
    """
    Core intelligence table — computed nightly by the Intelligence Engine.
    Stores RFM scores, ML churn probability, engagement metrics, and
    category affinity JSON. This is the heart of Xenia's customer intelligence.
    """
    __tablename__ = "customer_metrics"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.customer_id", ondelete="CASCADE"),
        primary_key=True,
    )

    # ── RFM Scores (1–5 scale, percentile-based) ──────────────────────────────
    r_score: Mapped[int | None] = mapped_column(Integer)   # Recency
    f_score: Mapped[int | None] = mapped_column(Integer)   # Frequency
    m_score: Mapped[int | None] = mapped_column(Integer)   # Monetary

    # ── Composite Scores (0.0–100.0) ──────────────────────────────────────────
    value_score: Mapped[float | None] = mapped_column(Float)
    churn_score: Mapped[float | None] = mapped_column(Float)        # Rule-based (legacy)
    churn_probability: Mapped[float | None] = mapped_column(Float)  # ML-based (0.0–1.0)
    engagement_score: Mapped[float | None] = mapped_column(Float)   # 0–100

    # ── Channel & Category Intelligence ───────────────────────────────────────
    preferred_channel: Mapped[str | None] = mapped_column(String(50))  # WhatsApp/Email/SMS
    top_category: Mapped[str | None] = mapped_column(String(100))

    # Stored as: {"electronics": 60, "sports": 20, "beauty": 20}
    category_affinity_json: Mapped[dict | None] = mapped_column(JSONB)

    # ── Raw Metrics (for ML features) ─────────────────────────────────────────
    total_orders: Mapped[int | None] = mapped_column(Integer)
    total_spend: Mapped[float | None] = mapped_column(Float)
    avg_order_value: Mapped[float | None] = mapped_column(Float)
    days_since_last_order: Mapped[int | None] = mapped_column(Integer)
    orders_last_90d: Mapped[int | None] = mapped_column(Integer)
    orders_prev_90d: Mapped[int | None] = mapped_column(Integer)

    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    customer: Mapped["Customer"] = relationship(
        "Customer", back_populates="metrics"
    )

    __table_args__ = (
        Index("ix_customer_metrics_churn", "churn_probability"),
        Index("ix_customer_metrics_value", "value_score"),
    )


class CustomerSegment(Base):
    """Multi-label segment membership — a customer can belong to many segments."""
    __tablename__ = "customer_segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.customer_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    segment_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )

    customer: Mapped["Customer"] = relationship(
        "Customer", back_populates="segments"
    )

    __table_args__ = (
        Index("ix_customer_segment_unique", "customer_id", "segment_name", unique=True),
    )


class CustomerInsights(Base):
    """
    AI Memory Layer — stores Xenia AI-generated personas, summaries,
    risks, and recommendations. Updated each time Xenia AI analyzes a customer.
    """
    __tablename__ = "customer_insights"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.customer_id", ondelete="CASCADE"),
        primary_key=True,
    )

    # ── AI Persona ────────────────────────────────────────────────────────────
    ai_persona: Mapped[str | None] = mapped_column(String(100))           # "Tech Upgrader"
    persona_description: Mapped[str | None] = mapped_column(Text)         # 2–3 line AI profile

    # ── AI Summary ────────────────────────────────────────────────────────────
    summary: Mapped[str | None] = mapped_column(Text)                     # High-level insight

    # ── AI Recommendations ────────────────────────────────────────────────────
    # ["Send reactivation campaign", "Offer upgrade deal"]
    risks: Mapped[list | None] = mapped_column(JSONB)
    recommendations: Mapped[list | None] = mapped_column(JSONB)

    # ── Quality Metadata ──────────────────────────────────────────────────────
    confidence_score: Mapped[float | None] = mapped_column(Float)    # 0.0–1.0
    model_version: Mapped[str | None] = mapped_column(String(50))    # Gemini version

    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )

    customer: Mapped["Customer"] = relationship(
        "Customer", back_populates="insights"
    )

    def __repr__(self) -> str:
        return f"<CustomerInsights customer={self.customer_id} persona={self.ai_persona!r}>"



