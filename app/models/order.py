"""
Xenia CRM – Order & OrderItem Models
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Order(Base):
    __tablename__ = "orders"

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.customer_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), index=True
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # ── Attribution link (set after campaign analysis) ────────────────────────
    attributed_communication_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("communications.communication_id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    customer: Mapped["Customer"] = relationship("Customer", back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(
        "OrderItem", back_populates="order", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Order id={self.order_id} customer={self.customer_id} total={self.total_amount}>"


class OrderItem(Base):
    __tablename__ = "order_items"

    order_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.order_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.product_id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    # ── Relationships ─────────────────────────────────────────────────────────
    order: Mapped["Order"] = relationship("Order", back_populates="items")
    product: Mapped["Product"] = relationship("Product", back_populates="order_items")

    @property
    def subtotal(self) -> Decimal:
        return self.unit_price * self.quantity

    def __repr__(self) -> str:
        return f"<OrderItem order={self.order_id} product={self.product_id} qty={self.quantity}>"


# ── Circular import resolution ────────────────────────────────────────────────
from app.models.customer import Customer
from app.models.product import Product
from app.models.campaign import Communication
