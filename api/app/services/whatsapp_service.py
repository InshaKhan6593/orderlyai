"""WhatsApp Cloud API: inbound payload parsing + outbound message sending.

The webhook only ACKs Meta; this module is where inbound messages are interpreted
and replies are sent through the Graph API. The LangGraph + Claude agent will later
replace the placeholder reply with real menu/order handling.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

# Graph API version pinned so behaviour doesn't shift under us on Meta's rollout.
GRAPH_API_VERSION = "v22.0"
_GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

logger = logging.getLogger(__name__)


def parse_incoming_message(payload: dict[str, Any]) -> dict[str, str] | None:
    """Pull the first inbound message out of a webhook payload.

    Returns ``{phone_number_id, from, text, message_id, type}`` or ``None`` when the
    payload carries no user message (e.g. a delivery/read status notification).
    """
    try:
        value = payload["entry"][0]["changes"][0]["value"]
    except (KeyError, IndexError, TypeError):
        return None

    messages = value.get("messages")
    if not messages:
        return None  # status update (sent/delivered/read), not an inbound message

    msg = messages[0]
    text = ""
    if msg.get("type") == "text":
        text = (msg.get("text") or {}).get("body", "")
    return {
        "phone_number_id": (value.get("metadata") or {}).get("phone_number_id", ""),
        "from": msg.get("from", ""),
        "text": text,
        "message_id": msg.get("id", ""),
        "type": msg.get("type", ""),
    }


async def send_text(
    *, phone_number_id: str, access_token: str, to: str, body: str
) -> bool:
    """Send a plain-text WhatsApp message. Returns True on success (HTTP 2xx)."""
    url = f"{_GRAPH_BASE}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"body": body},
    }
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        logger.warning("WhatsApp send to %s failed: %s", to, exc)
        return False
    if resp.status_code >= 400:
        logger.warning(
            "WhatsApp send to %s failed (%s): %s", to, resp.status_code, resp.text
        )
        return False
    return True
