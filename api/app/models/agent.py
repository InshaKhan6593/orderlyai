"""AI assistant configuration for a business."""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.business import Business


class AgentConfig(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "agent_configs"
    __table_args__ = (
        CheckConstraint("language = 'en'", name="agent_config_language_en_only"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    greeting_message: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(8), default="en", nullable=False)
    upsell_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    human_handoff_phone: Mapped[str | None] = mapped_column(String(32))
    extra_instructions: Mapped[str | None] = mapped_column(Text)

    business: Mapped["Business"] = relationship(back_populates="agent_config")
