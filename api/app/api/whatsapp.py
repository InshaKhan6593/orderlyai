"""WhatsApp Cloud API connection setup and webhook entrypoint."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select

from app.core.config import settings
from app.core.crypto import decrypt_secret, encrypt_secret
from app.core.deps import BusinessDep, DbSession
from app.core.errors import BadRequestError
from app.models.whatsapp import WhatsAppConnection
from app.schemas.whatsapp import WhatsAppConnectionIn, WhatsAppConnectionOut
from app.services import whatsapp_service

logger = logging.getLogger(__name__)

# Placeholder auto-reply until the LangGraph + Claude ordering agent is built.
_PLACEHOLDER_REPLY = (
    "Thanks for your message! Our ordering assistant isn't live just yet — "
    "we've received what you sent and someone will follow up soon."
)

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


async def _reply_to_incoming(db: DbSession, raw_body: bytes) -> None:
    """Parse an inbound message and send the placeholder reply for its tenant.

    Routes by ``metadata.phone_number_id`` so the correct business's (decrypted)
    token is used. Status notifications and non-message payloads are ignored.
    """
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        return

    parsed = whatsapp_service.parse_incoming_message(payload)
    if not parsed or not parsed["from"] or not parsed["phone_number_id"]:
        return

    row = await db.execute(
        select(WhatsAppConnection).where(
            WhatsAppConnection.phone_number_id == parsed["phone_number_id"]
        )
    )
    connection = row.scalars().first()
    if connection is None or not connection.access_token:
        logger.warning(
            "No WhatsApp connection for phone_number_id=%s", parsed["phone_number_id"]
        )
        return

    await whatsapp_service.send_text(
        phone_number_id=parsed["phone_number_id"],
        access_token=decrypt_secret(connection.access_token),
        to=parsed["from"],
        body=_PLACEHOLDER_REPLY,
    )


@webhook_router.post("/webhook")
async def receive_whatsapp_webhook(request: Request, db: DbSession) -> dict[str, str]:
    secret = settings.whatsapp_app_secret
    if not secret:
        # Fail closed: a publicly reachable webhook whose payloads cannot be
        # authenticated must never accept them.
        raise HTTPException(status_code=503, detail="WhatsApp webhook is not configured")

    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not _valid_signature(secret, raw_body, signature):
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

    # Always ACK 200 to Meta; downstream failures must not trigger retries.
    try:
        await _reply_to_incoming(db, raw_body)
    except Exception:  # noqa: BLE001 — never let processing break the ACK
        logger.exception("WhatsApp webhook processing failed")

    return {"status": "received"}
