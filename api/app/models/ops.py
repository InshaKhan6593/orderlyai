"""Operational settings: weekly business hours and delivery zones."""
from __future__ import annotations

import uuid
from datetime import time
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, Numeric, String, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.business import Business


class BusinessHours(UUIDMixin, Base):
    __tablename__ = "business_hours"
    __table_args__ = (
        CheckConstraint("day_of_week between 0 and 6", name="business_hours_dow"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)  # 0=Sun .. 6=Sat
    open_time: Mapped[time | None] = mapped_column(Time)
    close_time: Mapped[time | None] = mapped_column(Time)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    business: Mapped["Business"] = relationship(back_populates="hours")


class DeliveryZone(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "delivery_zones"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    min_order: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    eta_minutes: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    business: Mapped["Business"] = relationship(back_populates="zones")
