"""WhatsApp Cloud API: inbound payload parsing + outbound message sending.

The webhook only ACKs Meta; this module is where inbound messages are interpreted
and replies are sent through the Graph API.

Outbound sends are resilient: transient failures (network errors, 5xx, and Meta
rate-limit codes) are retried with exponential backoff, while hard errors (expired
token, outside the 24h window, undeliverable) are surfaced as a non-retryable
``SendResult`` so callers can react (dead-letter, re-auth, fall back to a template).
"""
from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import settings

# Graph API version pinned so behaviour doesn't shift under us on Meta's rollout.
GRAPH_API_VERSION = "v22.0"
_GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

logger = logging.getLogger(__name__)

# HTTP statuses worth retrying (transient): timeouts, rate limit, gateway/5xx.
_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
# Meta error codes that are transient (rate / throughput limits) — safe to retry.
_RETRYABLE_META_CODES = {4, 80007, 130429, 131048, 131056, 133016}
# Meta error codes the caller must handle specially (never retry):
#   131047 re-engagement (outside the 24h window → needs a template),
#   131026 message undeliverable, 190 access token expired/invalid (needs re-auth).
ERROR_REENGAGEMENT = 131047
ERROR_UNDELIVERABLE = 131026
ERROR_TOKEN_EXPIRED = 190


@dataclass
class SendResult:
    """Outcome of an outbound send. Truthy when the message was accepted (HTTP 2xx)."""

    ok: bool
    status_code: int | None = None
    error_code: int | None = None
    error_subcode: int | None = None
    error_message: str | None = None
    retryable: bool = False
    message_id: str | None = None
    # Batch bookkeeping, set by ``send_payloads``: how many payloads were delivered in this
    # call and their returned wamids — so the caller can resume a partial multi-message send
    # (without re-sending what already went out) and match delivery receipts to the reply.
    sent: int = 0
    sent_ids: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:  # `if result:` / `if not result:` reads naturally
        return self.ok


def _extract_one(
    msg: dict[str, Any], *, phone_number_id: str, name_by_waid: dict[str, str]
) -> dict[str, Any]:
    """Normalize a single inbound WhatsApp message into the worker's flat dict shape."""
    mtype = msg.get("type", "")
    text = ""
    reply_id = ""
    latitude: float | None = None
    longitude: float | None = None
    if mtype == "text":
        text = (msg.get("text") or {}).get("body", "")
    elif mtype == "interactive":
        interactive = msg.get("interactive") or {}
        chosen = interactive.get(interactive.get("type", ""), {}) or {}
        reply_id = chosen.get("id", "")
        text = chosen.get("title", "")
    elif mtype == "button":
        # Quick-reply from a template button arrives as a top-level "button".
        text = (msg.get("button") or {}).get("text", "")
    elif mtype == "location":
        loc = msg.get("location") or {}
        latitude = loc.get("latitude")
        longitude = loc.get("longitude")
        # Prefer a human address/name; fall back to coordinates the agent can echo back.
        text = loc.get("address") or loc.get("name") or ""
    sender = msg.get("from", "")
    return {
        "phone_number_id": phone_number_id,
        "from": sender,
        "name": name_by_waid.get(sender, ""),
        "text": text,
        "reply_id": reply_id,
        "message_id": msg.get("id", ""),
        "type": mtype,
        "timestamp": msg.get("timestamp", ""),
        "latitude": latitude,
        "longitude": longitude,
    }


def parse_incoming_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Pull **every** inbound message out of a webhook payload, in arrival order.

    Meta may batch multiple messages (and multiple entries/changes) in one webhook — a
    customer firing several messages back-to-back. Iterating only the first would silently
    drop the rest, so we walk them all. Status-only payloads (sent/delivered/read) yield [].
    Each item is ``{phone_number_id, from, name, text, reply_id, message_id, type,
    timestamp, latitude, longitude}``.
    """
    out: list[dict[str, Any]] = []
    entries = payload.get("entry")
    if not isinstance(entries, list):
        return out
    for entry in entries:
        for change in (entry or {}).get("changes") or []:
            value = (change or {}).get("value") or {}
            messages = value.get("messages")
            if not messages:
                continue  # status update, not an inbound message
            phone_number_id = (value.get("metadata") or {}).get("phone_number_id", "")
            name_by_waid = {
                c.get("wa_id", ""): ((c.get("profile") or {}).get("name") or "")
                for c in (value.get("contacts") or [])
            }
            for msg in messages:
                if not isinstance(msg, dict):
                    continue
                out.append(
                    _extract_one(
                        msg, phone_number_id=phone_number_id, name_by_waid=name_by_waid
                    )
                )
    return out


def parse_incoming_message(payload: dict[str, Any]) -> dict[str, Any] | None:
    """The first inbound message in a payload (or ``None``). See ``parse_incoming_messages``."""
    messages = parse_incoming_messages(payload)
    return messages[0] if messages else None


def parse_statuses(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Pull outbound delivery-status updates (sent/delivered/read/failed) from a webhook.

    The other half of an inbound webhook: ``messages`` are handled by
    ``parse_incoming_messages``; ``statuses`` are delivery receipts for messages WE sent,
    keyed by the wamid we got back at send time. Each item is ``{message_id, status,
    recipient, error_code, error_title}``.
    """
    out: list[dict[str, Any]] = []
    entries = payload.get("entry")
    if not isinstance(entries, list):
        return out
    for entry in entries:
        for change in (entry or {}).get("changes") or []:
            value = (change or {}).get("value") or {}
            for st in value.get("statuses") or []:
                if not isinstance(st, dict):
                    continue
                errors = st.get("errors") or []
                err = errors[0] if errors and isinstance(errors[0], dict) else {}
                out.append(
                    {
                        "message_id": st.get("id", ""),
                        "status": st.get("status", ""),
                        "recipient": st.get("recipient_id", ""),
                        "error_code": err.get("code"),
                        "error_title": err.get("title") or err.get("message"),
                    }
                )
    return out


def _parse_error(resp: httpx.Response) -> tuple[int | None, int | None, str | None]:
    """Pull (code, subcode, message) out of a Graph API error body."""
    try:
        err = (resp.json() or {}).get("error") or {}
    except ValueError:
        return None, None, resp.text[:300]
    return err.get("code"), err.get("error_subcode"), err.get("message")


def _sent_message_id(resp: httpx.Response) -> str | None:
    try:
        messages = (resp.json() or {}).get("messages") or []
    except ValueError:
        return None
    return (messages[0] or {}).get("id") if messages else None


async def _post_message(
    *,
    phone_number_id: str,
    access_token: str,
    payload: dict[str, Any],
    client: httpx.AsyncClient | None = None,
) -> SendResult:
    """POST one fully-formed message payload, retrying transient failures with backoff.

    Returns a :class:`SendResult`; on a hard (non-retryable) Meta error the result carries
    the error code so the caller can re-auth, switch to a template, or dead-letter.
    """
    url = f"{_GRAPH_BASE}/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {access_token}"}
    to = payload.get("to", "?")
    attempts = max(1, settings.whatsapp_send_max_retries)
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=15)
    try:
        last: SendResult | None = None
        for attempt in range(attempts):
            try:
                resp = await client.post(url, json=payload, headers=headers)
            except httpx.HTTPError as exc:
                logger.warning("WhatsApp send to %s network error: %s", to, exc)
                last = SendResult(ok=False, error_message=str(exc), retryable=True)
            else:
                if resp.status_code < 400:
                    return SendResult(
                        ok=True,
                        status_code=resp.status_code,
                        message_id=_sent_message_id(resp),
                    )
                code, subcode, message = _parse_error(resp)
                retryable = (
                    resp.status_code in _RETRYABLE_STATUS or code in _RETRYABLE_META_CODES
                )
                logger.warning(
                    "WhatsApp send to %s failed (http=%s code=%s subcode=%s retryable=%s): %s",
                    to, resp.status_code, code, subcode, retryable, message,
                )
                last = SendResult(
                    ok=False,
                    status_code=resp.status_code,
                    error_code=code,
                    error_subcode=subcode,
                    error_message=message,
                    retryable=retryable,
                )
                if not retryable:
                    return last
            if attempt < attempts - 1 and (last is None or last.retryable):
                # Exponential backoff with jitter; small because this runs inline-ish.
                await asyncio.sleep(min(8.0, 0.5 * (2**attempt)) + random.uniform(0, 0.3))
        return last or SendResult(ok=False, retryable=True)
    finally:
        if owns_client:
            await client.aclose()


async def send_text(
    *, phone_number_id: str, access_token: str, to: str, body: str
) -> SendResult:
    """Send a plain-text WhatsApp message (free-form; only valid inside the 24h window)."""
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"body": body},
    }
    return await _post_message(
        phone_number_id=phone_number_id, access_token=access_token, payload=payload
    )


async def send_payloads(
    *, phone_number_id: str, access_token: str, payloads: list[dict[str, Any]]
) -> SendResult:
    """Send pre-rendered Graph API payloads (e.g. from ``agent.whatsapp_render``) in order.

    Sends sequentially (WhatsApp preserves order this way), reusing one HTTP client. Stops on
    the first failure so a half-reply isn't sent, and returns that failure's result. The
    result's ``sent``/``sent_ids`` report how many payloads went out (and their wamids) so a
    retry can resume from the next one instead of re-sending — and thus duplicating — messages
    that already arrived.
    """
    async with httpx.AsyncClient(timeout=15) as client:
        sent = 0
        sent_ids: list[str] = []
        result = SendResult(ok=True)
        for payload in payloads:
            result = await _post_message(
                phone_number_id=phone_number_id,
                access_token=access_token,
                payload=payload,
                client=client,
            )
            if not result:
                break
            sent += 1
            if result.message_id:
                sent_ids.append(result.message_id)
        result.sent = sent
        result.sent_ids = sent_ids
        return result


async def send_template(
    *,
    phone_number_id: str,
    access_token: str,
    to: str,
    template_name: str,
    language: str | None = None,
    components: list[dict[str, Any]] | None = None,
) -> SendResult:
    """Send a pre-approved template message — the ONLY message kind Meta allows outside the
    24h customer-service window (e.g. a proactive order-status update hours later)."""
    template: dict[str, Any] = {
        "name": template_name,
        "language": {"code": language or settings.whatsapp_template_lang},
    }
    if components:
        template["components"] = components
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "template",
        "template": template,
    }
    return await _post_message(
        phone_number_id=phone_number_id, access_token=access_token, payload=payload
    )


async def mark_read(
    *, phone_number_id: str, access_token: str, message_id: str, typing: bool = False
) -> bool:
    """Mark an inbound message read (blue ticks), optionally showing a typing indicator.

    Best-effort UX only — failures are swallowed and never block the reply.
    """
    payload: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }
    if typing:
        payload["typing_indicator"] = {"type": "text"}
    url = f"{_GRAPH_BASE}/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload, headers=headers)
        return resp.status_code < 400
    except httpx.HTTPError:
        return False
