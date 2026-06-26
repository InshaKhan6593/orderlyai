"""Durable inbound processing for the WhatsApp agent.

The webhook persists every inbound message to ``whatsapp_inbox`` (durable + deduped) and
ACKs Meta immediately, then hands off to this module to actually run the agent and reply.

Why a durable inbox instead of running inline / in a BackgroundTask:
  * **No lost messages.** State that lived only in memory (the old in-process dedup set and
    the MemorySaver checkpointer) was wiped on every restart, so a Meta redelivery after a
    restart was re-answered as a brand-new conversation (the phantom "welcome" message). The
    inbox is written before the ACK; anything left ``pending`` is re-driven by the sweeper.
  * **Exactly-once-ish dedup.** Meta is at-least-once; the unique ``message_id`` drops retries
    at the DB, across restarts AND across instances.
  * **Back-to-back messages are safe.** A per-conversation Postgres advisory lock serializes a
    customer's messages so concurrent drains can't race the cart, and a burst of quick texts
    is coalesced into a single agent turn (one coherent reply, not a reply per fragment).
  * **Retries don't double-act.** Once the agent has produced a reply we store the rendered
    payloads and flip the row to ``answered``; a failed send is retried as a pure re-send, so
    the agent (and the cart) never runs twice for one message.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.schemas import BTN_CANCEL, BTN_CONFIRM, BTN_EDIT, ROW_PRODUCT_PREFIX
from app.agent.whatsapp_render import to_payloads
from app.core.config import settings
from app.core.crypto import decrypt_secret
from app.core.db import SessionLocal
from app.models.customer import Customer
from app.models.whatsapp import WhatsAppConnection, WhatsAppInbox
from app.services import whatsapp_service

logger = logging.getLogger(__name__)

_DRAIN_BATCH = 50
# Sent only if the agent itself errors out, so the customer isn't left hanging.
_FALLBACK_REPLY = "Sorry, I had trouble with that just now - please send that again."


def _now() -> datetime:
    return datetime.now(timezone.utc)


def thread_id_for(business_id: Any, wa_phone: str) -> str:
    """The checkpointer/lock key for one customer↔business conversation."""
    return f"{business_id}:{wa_phone}"


def _advisory_key(thread_id: str) -> int:
    """A stable signed 64-bit key for ``pg_advisory_lock`` derived from the thread id."""
    digest = hashlib.blake2b(thread_id.encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)


def agent_input(parsed: dict[str, Any]) -> tuple[str | None, bool]:
    """Map a parsed inbound message to ``(text_for_agent, confirmed)``.

    Button/list taps become a short instruction. The [Confirm] button is the ONLY thing that
    sets ``confirmed`` — the deterministic gate ``place_order`` checks (never inferred from
    free text). A shared location becomes an address line; unsupported media asks for text.
    Returns ``(None, False)`` when there's nothing actionable to send the agent.
    """
    reply_id = parsed.get("reply_id") or ""
    if reply_id == BTN_CONFIRM:
        return "Confirm the order.", True
    if reply_id == BTN_CANCEL:
        return "Cancel the order.", False
    if reply_id == BTN_EDIT:
        return "I'd like to edit my cart.", False
    if reply_id.startswith(ROW_PRODUCT_PREFIX):
        return parsed.get("text") or "Tell me about that item.", False

    mtype = parsed.get("type") or ""
    body = (parsed.get("text") or "").strip()
    if mtype == "location":
        if body:
            return f"My delivery address: {body}", False
        lat, lon = parsed.get("latitude"), parsed.get("longitude")
        if lat is not None and lon is not None:
            return (
                f"I shared a location pin ({lat}, {lon}); please use it as my delivery area.",
                False,
            )
        return "I shared my location.", False
    if body:
        return body, False
    if mtype and mtype not in ("text", "interactive", "button"):
        return (
            "[The customer sent a non-text message (e.g. an image or voice note) that I can't "
            "open. Ask them to describe what they'd like in text.]",
            False,
        )
    return None, False


async def _touch_customer(
    db: AsyncSession, business_id: Any, wa_phone: str, name: str | None
) -> None:
    """Record the inbound time (start of the 24h window) and backfill the name.

    Upserts so leads who message but never order are still captured for the dashboard.
    """
    stmt = pg_insert(Customer).values(
        business_id=business_id, wa_phone=wa_phone, name=name, last_inbound_at=_now()
    )
    stmt = stmt.on_conflict_do_update(
        constraint="customers_business_phone",
        set_={
            "last_inbound_at": stmt.excluded.last_inbound_at,
            "name": func.coalesce(Customer.name, stmt.excluded.name),
        },
    )
    await db.execute(stmt)


async def _rate_limited(db: AsyncSession, business_id: Any, wa_phone: str) -> bool:
    """True if this customer has exceeded the inbound rate limit in the last minute."""
    limit = settings.whatsapp_rate_limit_per_min
    if limit <= 0:
        return False
    since = _now() - timedelta(seconds=60)
    count = await db.scalar(
        select(func.count())
        .select_from(WhatsAppInbox)
        .where(
            WhatsAppInbox.business_id == business_id,
            WhatsAppInbox.wa_phone == wa_phone,
            WhatsAppInbox.created_at >= since,
        )
    )
    return (count or 0) >= limit


async def persist_inbound(db: AsyncSession, parsed: dict[str, Any]) -> str | None:
    """Durably record one inbound message; return its ``thread_id`` if it needs draining.

    Returns ``None`` for a duplicate (Meta retry), an unroutable message (no connection),
    a non-actionable message, or a rate-limited sender — none of which should run the agent.
    Commits on its own so the row survives even if the later drain crashes.
    """
    phone_number_id = parsed.get("phone_number_id") or ""
    wa_phone = parsed.get("from") or ""
    if not phone_number_id or not wa_phone:
        return None

    connection = (
        await db.execute(
            select(WhatsAppConnection).where(
                WhatsAppConnection.phone_number_id == phone_number_id
            )
        )
    ).scalars().first()
    if connection is None or not connection.access_token:
        logger.warning("No WhatsApp connection for phone_number_id=%s", phone_number_id)
        return None

    business_id = connection.business_id
    thread_id = thread_id_for(business_id, wa_phone)
    message_id = parsed.get("message_id") or f"noid:{phone_number_id}:{parsed.get('timestamp','')}"
    text_for_agent, confirmed = agent_input(parsed)

    # Decide the row's initial status: only genuinely actionable, non-throttled messages are
    # left `pending` for the agent. Everything else is recorded (dedup/audit) but not drained.
    if text_for_agent is None:
        status = "skipped"
    elif await _rate_limited(db, business_id, wa_phone):
        logger.warning("Rate limit hit for %s on business %s", wa_phone, business_id)
        status = "skipped"
    else:
        status = "pending"

    stmt = (
        pg_insert(WhatsAppInbox)
        .values(
            business_id=business_id,
            message_id=message_id,
            phone_number_id=phone_number_id,
            wa_phone=wa_phone,
            thread_id=thread_id,
            msg_type=parsed.get("type") or "",
            reply_id=parsed.get("reply_id") or None,
            text=text_for_agent,
            confirmed=confirmed,
            profile_name=parsed.get("name") or None,
            raw=parsed,
            status=status,
            attempts=0,
        )
        .on_conflict_do_nothing(index_elements=["message_id"])
        .returning(WhatsAppInbox.id)
    )
    inserted = (await db.execute(stmt)).scalar_one_or_none()
    if inserted is None:
        return None  # duplicate delivery / Meta retry — already recorded

    await _touch_customer(db, business_id, wa_phone, parsed.get("name"))
    await db.commit()
    return thread_id if status == "pending" else None


# --------------------------------------------------------------------------- #
# Draining (per-conversation, serialized, coalesced)
# --------------------------------------------------------------------------- #
def _discrete(row: WhatsAppInbox) -> bool:
    """A tap (button/list) or a confirm is processed on its own — never merged with text."""
    return bool(row.reply_id) or row.confirmed


def _next_unit(
    rows: list[WhatsAppInbox],
) -> tuple[WhatsAppInbox, list[WhatsAppInbox], str, bool]:
    """Take the next agent turn off the front of the queue.

    An ``answered`` row (agent already ran, send pending) is re-sent on its own. A tap/confirm
    is its own turn. Consecutive plain-text/location rows are coalesced into one turn so a
    burst of quick messages gets a single coherent reply. Returns
    ``(owner, consumed_siblings, combined_text, confirmed)``.
    """
    first = rows[0]
    if first.status == "answered" or _discrete(first):
        return first, [], (first.text or ""), first.confirmed

    unit = [first]
    for row in rows[1:]:
        if row.status == "pending" and not _discrete(row):
            unit.append(row)
        else:
            break
    combined = "\n".join(r.text for r in unit if r.text)
    return unit[0], unit[1:], combined, False


async def _mark(db: AsyncSession, rows: list[WhatsAppInbox], status: str, **extra: Any) -> None:
    for row in rows:
        row.status = status
        for key, value in extra.items():
            setattr(row, key, value)
    await db.commit()


async def _mark_read_safe(connection: WhatsAppConnection, token: str, row: WhatsAppInbox) -> None:
    if row.message_id.startswith("noid:"):
        return
    try:
        await whatsapp_service.mark_read(
            phone_number_id=connection.phone_number_id,
            access_token=token,
            message_id=row.message_id,
            typing=True,
        )
    except Exception:  # noqa: BLE001 — read receipts are best-effort UX, never block the reply
        pass


async def _process_unit(
    db: AsyncSession,
    connection: WhatsAppConnection,
    token: str,
    owner: WhatsAppInbox,
    siblings: list[WhatsAppInbox],
    combined_text: str,
    confirmed: bool,
) -> bool:
    """Run (or re-send) one turn. Returns True to keep draining, False to stop (retry later)."""
    wa_phone = owner.wa_phone

    if owner.status == "answered" and owner.response:
        payloads = owner.response  # send retry — do NOT re-run the agent
    else:
        from app.agent.runtime import get_whatsapp_agent, run_turn  # lazy: keep LangChain out of import

        try:
            reply = await run_turn(
                get_whatsapp_agent(),
                business_id=connection.business_id,
                customer_phone=wa_phone,
                thread_id=owner.thread_id,
                text=combined_text,
                confirmed=confirmed,
            )
        except Exception:  # noqa: BLE001 — an LLM/agent hiccup must not crash the worker
            logger.exception("Agent run failed for %s", wa_phone)
            return await _retry_after_agent_error(db, connection, token, owner, siblings)

        if reply is None:
            # Handed off to a human earlier in this thread → stay silent, consume the message.
            await _mark(db, [owner, *siblings], "done", processed_at=_now())
            return True

        payloads = to_payloads(reply, to=wa_phone)
        # Persist the reply + consume merged siblings BEFORE sending, so a send retry re-delivers
        # this exact reply instead of re-running the agent (which would mutate the cart again).
        owner.response = payloads
        owner.status = "answered"
        for sibling in siblings:
            sibling.status = "done"
            sibling.processed_at = _now()
        await db.commit()

    await _mark_read_safe(connection, token, owner)
    result = await whatsapp_service.send_payloads(
        phone_number_id=connection.phone_number_id,
        access_token=token,
        payloads=payloads,
    )
    if result:
        await _mark(db, [owner], "done", processed_at=_now())
        return True

    # Send failed. Hard errors (expired token, outside the 24h window, undeliverable) won't
    # succeed on retry — fail the row and flag the connection if the token died.
    error_code = getattr(result, "error_code", None)
    if not getattr(result, "retryable", True):
        await _mark(db, [owner], "failed", error=f"send failed (code={error_code})")
        if error_code == whatsapp_service.ERROR_TOKEN_EXPIRED:
            connection.status = "error"
            await db.commit()
        return False

    owner.attempts += 1
    if owner.attempts >= settings.whatsapp_inbox_max_attempts:
        await _mark(db, [owner], "failed", error=f"max send attempts (code={error_code})")
    else:
        await db.commit()  # stays 'answered' with the stored reply → sweeper re-sends
    return False


async def _retry_after_agent_error(
    db: AsyncSession,
    connection: WhatsAppConnection,
    token: str,
    owner: WhatsAppInbox,
    siblings: list[WhatsAppInbox],
) -> bool:
    """The agent itself errored (no reply produced). Retry a few times, then dead-letter with
    a brief fallback so the customer isn't left hanging."""
    owner.attempts += 1
    if owner.attempts < settings.whatsapp_inbox_max_attempts:
        await db.commit()  # leave pending; sweeper retries
        return False
    await _mark(db, [owner, *siblings], "failed", error="agent error (max attempts)")
    try:
        await whatsapp_service.send_text(
            phone_number_id=connection.phone_number_id,
            access_token=token,
            to=owner.wa_phone,
            body=_FALLBACK_REPLY,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Fallback send failed for %s", owner.wa_phone)
    return False


async def _drain_locked(db: AsyncSession, thread_id: str) -> None:
    """Process all queued turns for one conversation. Caller holds the advisory lock."""
    while True:
        rows = list(
            (
                await db.execute(
                    select(WhatsAppInbox)
                    .where(
                        WhatsAppInbox.thread_id == thread_id,
                        WhatsAppInbox.status.in_(("pending", "answered")),
                    )
                    .order_by(WhatsAppInbox.created_at)
                    .limit(_DRAIN_BATCH)
                )
            )
            .scalars()
            .all()
        )
        if not rows:
            return

        connection = (
            await db.execute(
                select(WhatsAppConnection).where(
                    WhatsAppConnection.phone_number_id == rows[0].phone_number_id
                )
            )
        ).scalars().first()
        if connection is None or not connection.access_token:
            await _mark(db, rows, "failed", error="no active WhatsApp connection")
            return
        token = decrypt_secret(connection.access_token)

        owner, siblings, combined_text, confirmed = _next_unit(rows)
        keep_going = await _process_unit(
            db, connection, token, owner, siblings, combined_text, confirmed
        )
        if not keep_going:
            return  # stop on failure; the sweeper will re-drive what's left


async def drain_conversation(thread_id: str) -> None:
    """Drain one conversation under a per-conversation advisory lock (no-op if busy).

    Non-blocking lock: if another worker/instance already holds this conversation, we return
    immediately — that holder's loop (or the sweeper) will pick up our freshly-queued rows.
    """
    if settings.whatsapp_coalesce_seconds > 0:
        # Brief debounce so a rapid burst is drained together as one coalesced turn.
        await asyncio.sleep(settings.whatsapp_coalesce_seconds)

    key = _advisory_key(thread_id)
    async with SessionLocal() as db:
        got = await db.scalar(text("SELECT pg_try_advisory_lock(:k)"), {"k": key})
        if not got:
            return
        try:
            await _drain_locked(db, thread_id)
        except Exception:  # noqa: BLE001 — never let a drain crash take down the caller
            logger.exception("Drain failed for thread %s", thread_id)
        finally:
            await db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
            await db.commit()


# --------------------------------------------------------------------------- #
# Sweeper (crash recovery + retry backstop)
# --------------------------------------------------------------------------- #
async def _pending_threads(db: AsyncSession, limit: int = 200) -> list[str]:
    rows = await db.execute(
        select(WhatsAppInbox.thread_id)
        .where(WhatsAppInbox.status.in_(("pending", "answered")))
        .group_by(WhatsAppInbox.thread_id)
        .limit(limit)
    )
    return [r[0] for r in rows.all()]


async def sweep_once() -> int:
    """Re-drive every conversation with unfinished work. Returns how many it touched.

    This is the safety net: it recovers messages left ``pending`` by a crash/restart and
    re-sends replies stuck ``answered`` by a transient send failure.
    """
    async with SessionLocal() as db:
        threads = await _pending_threads(db)
    for thread_id in threads:
        await drain_conversation(thread_id)
    return len(threads)


async def sweeper_loop() -> None:
    """Background task: periodically sweep unfinished conversations until cancelled."""
    interval = max(5, settings.whatsapp_inbox_sweep_seconds)
    logger.info("WhatsApp inbox sweeper started (every %ss)", interval)
    try:
        while True:
            try:
                await sweep_once()
            except Exception:  # noqa: BLE001
                logger.exception("Inbox sweep failed")
            await asyncio.sleep(interval)
    except asyncio.CancelledError:  # graceful shutdown
        logger.info("WhatsApp inbox sweeper stopped")
        raise
