"""
Xenia CRM – Product Model
"""

import uuid
from decimal import Decimal

from sqlalchemy import Enum, Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

import enum


class ProductCategory(str, enum.Enum):
    ELECTRONICS = "Electronics"
    GROCERIES = "Groceries"
    BEAUTY = "Beauty"
    FASHION = "Fashion"
    SPORTS = "Sports"
    HOME_KITCHEN = "Home & Kitchen"
    BABY_PRODUCTS = "Baby Products"
    BOOKS = "Books"
    HEALTH = "Health"
    PET_SUPPLIES = "Pet Supplies"


class Product(Base):
    __tablename__ = "products"

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(200))
    sku: Mapped[str | None] = mapped_column(String(100), unique=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    order_items: Mapped[list["OrderItem"]] = relationship(
        "OrderItem", back_populates="product", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Product id={self.product_id} name={self.name!r} category={self.category!r}>"


# ── Circular import resolution ────────────────────────────────────────────────
from app.models.order import OrderItem
