"""WhatsApp Cloud API connection setup and webhook entrypoint.

The webhook does as little as possible synchronously: verify the signature, durably record
every inbound message to the inbox (``whatsapp_worker.persist_inbound``), ACK Meta, then
drain each affected conversation in the background. All the hard parts — dedup, ordering,
coalescing, retries, crash recovery — live in ``app.services.whatsapp_worker``.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select

from app.core.config import settings
from app.core.crypto import encrypt_secret
from app.core.db import SessionLocal
from app.core.deps import BusinessDep, DbSession
from app.core.errors import BadRequestError
from app.models.whatsapp import WhatsAppConnection
from app.schemas.whatsapp import WhatsAppConnectionIn, WhatsAppConnectionOut
from app.services import whatsapp_service, whatsapp_worker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/businesses/{business_id}/whatsapp-connection", tags=["whatsapp"])
webhook_router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def _clean_required(value: str, field: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        raise BadRequestError(f"{field} is required.")
    return trimmed


def _out(connection: WhatsAppConnection | None, business) -> WhatsAppConnectionOut:
    if connection is None:
        return WhatsAppConnectionOut(
            id=None,
            business_id=business.id,
            mode="test",
            waba_id="",
            phone_number_id="",
            display_phone_number=None,
            display_name=None,
            status="not_configured",
            has_access_token=False,
        )
    return WhatsAppConnectionOut(
        id=connection.id,
        business_id=connection.business_id,
        mode=connection.mode,  # type: ignore[arg-type]
        waba_id=connection.waba_id,
        phone_number_id=connection.phone_number_id,
        display_phone_number=connection.display_phone_number,
        display_name=connection.display_name,
        status=connection.status,  # type: ignore[arg-type]
        has_access_token=bool(connection.access_token),
    )


async def _get_connection(db: DbSession, business_id) -> WhatsAppConnection | None:
    row = await db.execute(
        select(WhatsAppConnection).where(WhatsAppConnection.business_id == business_id)
    )
    return row.scalar_one_or_none()


@router.get("", response_model=WhatsAppConnectionOut)
async def get_whatsapp_connection(
    business: BusinessDep, db: DbSession
) -> WhatsAppConnectionOut:
    return _out(await _get_connection(db, business.id), business)


@router.put("", response_model=WhatsAppConnectionOut)
async def save_whatsapp_connection(
    data: WhatsAppConnectionIn, business: BusinessDep, db: DbSession
) -> WhatsAppConnectionOut:
    connection = await _get_connection(db, business.id)
    access_token = _clean_optional(data.access_token)
    if connection is None and not access_token:
        raise BadRequestError("Access token is required for the first WhatsApp connection save.")

    # Encrypt at rest: the database only ever holds Fernet ciphertext, never the
    # raw Meta token. Decrypt at send time in the agent/worker phase.
    encrypted_token = encrypt_secret(access_token) if access_token else None

    values = {
        "mode": data.mode,
        "waba_id": _clean_required(data.waba_id, "WABA ID"),
        "phone_number_id": _clean_required(data.phone_number_id, "Phone number ID"),
        "display_phone_number": _clean_optional(data.display_phone_number),
        "display_name": _clean_optional(data.display_name),
        "status": "configured",
    }

    if connection is None:
        connection = WhatsAppConnection(
            business_id=business.id,
            access_token=encrypted_token or "",
            **values,
        )
        db.add(connection)
    else:
        for field, value in values.items():
            setattr(connection, field, value)
        if encrypted_token:
            connection.access_token = encrypted_token

    await db.commit()
    await db.refresh(connection)
    return _out(connection, business)


@webhook_router.get("/webhook", response_class=PlainTextResponse)
async def verify_whatsapp_webhook(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
) -> PlainTextResponse:
    verify_token = settings.whatsapp_verify_token
    if (
        verify_token
        and hub_mode == "subscribe"
        and hub_challenge is not None
        and hub_verify_token is not None
        # Constant-time compare avoids leaking the token via response timing.
        and hmac.compare_digest(hub_verify_token, verify_token)
    ):
        return PlainTextResponse(content=hub_challenge, status_code=200)
    raise HTTPException(status_code=403, detail="Invalid verify token")


def _valid_signature(secret: str, body: bytes, header: str) -> bool:
    """Verify Meta's ``X-Hub-Signature-256: sha256=<hex>`` over the raw request body."""
    prefix = "sha256="
    if not header.startswith(prefix):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[len(prefix) :])


# Re-exported so the parse→agent-input mapping has one home (the worker) but stays importable
# from here for tests and callers.
_agent_input = whatsapp_worker.agent_input


async def _persist_incoming(raw_body: bytes) -> list[str]:
    """Durably record every inbound message in the payload; return threads needing a drain.

    Runs INSIDE the request, before we ACK Meta — so a crash right after the 200 can never
    lose a message (Meta won't redeliver an ACKed webhook; our sweeper re-drives the inbox).
    Duplicates, status notifications, and non-actionable messages persist (or are ignored)
    without queueing agent work.
    """
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        return []

    messages = whatsapp_service.parse_incoming_messages(payload)
    if not messages:
        return []  # status update (sent/delivered/read) or empty payload

    threads: list[str] = []
    async with SessionLocal() as db:
        for parsed in messages:
            try:
                thread_id = await whatsapp_worker.persist_inbound(db, parsed)
            except Exception:  # noqa: BLE001 — one bad message must not drop the rest
                await db.rollback()
                logger.exception("Failed to persist inbound message %s", parsed.get("message_id"))
                continue
            if thread_id and thread_id not in threads:
                threads.append(thread_id)
    return threads


@webhook_router.post("/webhook")
async def receive_whatsapp_webhook(
    request: Request, background_tasks: BackgroundTasks
) -> dict[str, str]:
    secret = settings.whatsapp_app_secret
    if not secret:
        # Fail closed: a publicly reachable webhook whose payloads cannot be
        # authenticated must never accept them.
        raise HTTPException(status_code=503, detail="WhatsApp webhook is not configured")

    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not _valid_signature(secret, raw_body, signature):
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

    # Persist first (durability), then ACK, then drain each conversation in the background so
    # a slow agent turn never delays the 200. The per-conversation advisory lock in the worker
    # keeps a customer's back-to-back messages serialized and coalesced.
    threads = await _persist_incoming(raw_body)
    for thread_id in threads:
        background_tasks.add_task(whatsapp_worker.drain_conversation, thread_id)
    return {"status": "received"}
