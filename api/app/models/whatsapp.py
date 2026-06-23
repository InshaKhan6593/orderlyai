"""WhatsApp Cloud API connection settings for a business."""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.business import Business


class WhatsAppConnection(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "whatsapp_connections"
    __table_args__ = (
        CheckConstraint("mode in ('test','live')", name="whatsapp_connection_mode"),
        CheckConstraint(
            "status in ('configured','verified','error')",
            name="whatsapp_connection_status",
        ),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    mode: Mapped[str] = mapped_column(String(16), default="test", nullable=False)
    waba_id: Mapped[str] = mapped_column(String(64), nullable=False)
    phone_number_id: Mapped[str] = mapped_column(String(64), nullable=False)
    display_phone_number: Mapped[str | None] = mapped_column(String(32))
    display_name: Mapped[str | None] = mapped_column(String(255))
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="configured", nullable=False)

    business: Mapped["Business"] = relationship(back_populates="whatsapp_connection")
