"""
Xenia CRM – Promotion Model
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, Numeric, String, Text, DateTime, Integer, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Promotion(Base):
    __tablename__ = "promotions"

    promotion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(100), index=True)  # target category (for backward compatibility)
    discount_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("0.00")) # backward compatibility
    min_order_value: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    promo_code: Mapped[str | None] = mapped_column(String(50), unique=True)

    # ── New Fields for Rule Enforcement & Tracking ────────────────────────────
    discount_type: Mapped[str] = mapped_column(String(50), nullable=False, default="Percentage") # Percentage, Fixed Amount, Free Shipping, etc.
    discount_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    applicable_categories: Mapped[str] = mapped_column(Text, nullable=False, default="ALL") # "ALL" or comma-separated list
    applicable_cities: Mapped[str] = mapped_column(Text, nullable=False, default="ALL") # "ALL" or comma-separated list
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    max_usage_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    
    # ── Performance Tracking Columns ───────────────────────────────────────────
    times_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    times_recommended: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    purchases_attributed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revenue_generated: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    roi_generated: Mapped[float | None] = mapped_column(Float, nullable=True, default=0.0)

    # ── Relationships ─────────────────────────────────────────────────────────
    campaigns: Mapped[list["Campaign"]] = relationship(
        "Campaign", back_populates="promotion", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Promotion name={self.name!r} code={self.promo_code!r} active={self.active}>"


# ── Circular import resolution ────────────────────────────────────────────────
from app.models.campaign import Campaign

