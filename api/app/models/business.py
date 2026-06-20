"""Business (tenant root) and Membership (user ↔ business with role)."""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.menu import Category, Product
    from app.models.ops import BusinessHours, DeliveryZone
    from app.models.order import Order
    from app.models.user import User


class Business(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "businesses"
    __table_args__ = (
        CheckConstraint(
            "type in ('restaurant','cafe','bakery','home_kitchen','other')",
            name="business_type",
        ),
        CheckConstraint(
            "status in ('onboarding','active','paused','suspended')",
            name="business_status",
        ),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    logo_url: Mapped[str | None] = mapped_column(String(512))
    cover_url: Mapped[str | None] = mapped_column(String(512))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="PKR", nullable=False)
    languages: Mapped[list[str]] = mapped_column(
        ARRAY(String), default=lambda: ["en"], nullable=False
    )

    # Contact / info
    helpline_phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(Text)
    maps_url: Mapped[str | None] = mapped_column(String(512))

    # Fulfillment settings
    offers_delivery: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    offers_pickup: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    min_order_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    default_prep_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    packaging_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    accepting_orders: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Lifecycle + forward-compat billing
    status: Mapped[str] = mapped_column(String(16), default="onboarding", nullable=False)
    plan_code: Mapped[str] = mapped_column(String(32), default="free", nullable=False)
    next_order_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    memberships: Mapped[list["Membership"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    categories: Mapped[list["Category"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    products: Mapped[list["Product"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    hours: Mapped[list["BusinessHours"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    zones: Mapped[list["DeliveryZone"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    customers: Mapped[list["Customer"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    orders: Mapped[list["Order"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )


class Membership(TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (
        CheckConstraint("role in ('owner','manager','staff')", name="membership_role"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(16), default="owner", nullable=False)

    user: Mapped["User"] = relationship(back_populates="memberships")
    business: Mapped["Business"] = relationship(back_populates="memberships")
