"""WhatsApp Cloud API connection settings for a business + the inbound message inbox."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
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
    # The inbound routing key: every webhook is matched to a business by phone_number_id, so
    # it must be uniquely indexed (one connection per WhatsApp number) and fast to look up.
    phone_number_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    display_phone_number: Mapped[str | None] = mapped_column(String(32))
    display_name: Mapped[str | None] = mapped_column(String(255))
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="configured", nullable=False)

    business: Mapped["Business"] = relationship(back_populates="whatsapp_connection")


class WhatsAppInbox(UUIDMixin, TimestampMixin, Base):
    """Durable record of every inbound WhatsApp message — the unit of work for the agent.

    Persisted *before* the webhook ACKs Meta, so a restart/crash can never lose a message
    (the sweeper re-drives anything left ``pending``). The unique ``message_id`` is the
    dedup guarantee: Meta's at-least-once retries hit the unique constraint and are dropped
    instead of answered twice — and this works across restarts and across instances, unlike
    the old in-memory set. ``thread_id`` (``business_id:wa_phone``) keys the per-conversation
    advisory lock so a customer's back-to-back messages are processed one at a time, in order.
    """

    __tablename__ = "whatsapp_inbox"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending','answered','done','failed','skipped')",
            name="whatsapp_inbox_status",
        ),
        # Drain query ("oldest pending rows for this conversation") + per-thread ordering.
        Index("ix_whatsapp_inbox_thread_status", "thread_id", "status", "created_at"),
        # Sweeper scan: only ever looks for active (unfinished) work — a partial index keeps
        # it tiny and selective as terminal (done/failed/skipped) rows pile up.
        Index(
            "ix_whatsapp_inbox_active",
            "thread_id",
            postgresql_where=text("status in ('pending','answered')"),
        ),
        # Match Meta delivery-status webhooks back to the row that sent the message.
        Index("ix_whatsapp_inbox_sent_ids", "sent_message_ids", postgresql_using="gin"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # Meta's wamid — globally unique; the dedup key.
    message_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    phone_number_id: Mapped[str] = mapped_column(String(64), nullable=False)
    wa_phone: Mapped[str] = mapped_column(String(32), nullable=False)
    thread_id: Mapped[str] = mapped_column(String(128), nullable=False)
    msg_type: Mapped[str] = mapped_column(String(32), nullable=False)
    reply_id: Mapped[str | None] = mapped_column(String(256))
    text: Mapped[str | None] = mapped_column(Text)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    profile_name: Mapped[str | None] = mapped_column(String(255))
    raw: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    # The rendered Graph API payloads, stored once the agent has answered but BEFORE the send
    # succeeds — so a send retry re-delivers the same reply without re-running the agent (which
    # would mutate the cart again). ``status='answered'`` means "reply ready, delivery pending".
    response: Mapped[list | None] = mapped_column(JSONB)
    # How many of ``response``'s payloads have already been delivered, so a retry after a
    # partial multi-message send resumes from the next one instead of re-sending (and thus
    # duplicating) the messages that already went out.
    sent_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # The Meta message ids (wamids) we got back for the delivered payloads — used to match
    # inbound delivery-status webhooks (notably ``failed``) back to this reply.
    sent_message_ids: Mapped[list | None] = mapped_column(JSONB)
    # Last delivery status Meta reported for this reply (e.g. 'failed'); None until a status
    # webhook arrives. Only failures are recorded (delivered/read are ignored to avoid churn).
    delivery_state: Mapped[str | None] = mapped_column(String(16))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
