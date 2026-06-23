"""Render a validated ``AgentReply`` into WhatsApp Cloud API message payloads.

Pure mapping (no LangChain / no network) so it's unit-testable. Defensive
truncation is applied again here even though the schema already constrains lengths,
so a payload can never be rejected by Meta for an over-long field.
"""
from __future__ import annotations

from typing import Any

from app.agent.schemas import (
    AgentReply,
    ButtonsMessage,
    ImageMessage,
    ListMessage,
    OutboundMessage,
    TextMessage,
)


def _t(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def _envelope(to: str, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        **body,
    }


def _render_one(msg: OutboundMessage, to: str) -> dict[str, Any]:
    if isinstance(msg, TextMessage):
        return _envelope(to, {"type": "text", "text": {"body": _t(msg.body, 4096)}})

    if isinstance(msg, ImageMessage):
        image: dict[str, Any] = {"link": msg.image_url}
        if msg.caption:
            image["caption"] = _t(msg.caption, 1024)
        return _envelope(to, {"type": "image", "image": image})

    if isinstance(msg, ButtonsMessage):
        return _envelope(
            to,
            {
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": _t(msg.body, 1024)},
                    "action": {
                        "buttons": [
                            {
                                "type": "reply",
                                "reply": {"id": b.id[:256], "title": _t(b.title, 20)},
                            }
                            for b in msg.buttons[:3]
                        ]
                    },
                },
            },
        )

    if isinstance(msg, ListMessage):
        interactive: dict[str, Any] = {
            "type": "list",
            "body": {"text": _t(msg.body, 1024)},
            "action": {
                "button": _t(msg.button, 20),
                "sections": [
                    {
                        "title": _t(s.title, 24),
                        "rows": [
                            {
                                "id": r.id[:200],
                                "title": _t(r.title, 24),
                                **(
                                    {"description": _t(r.description, 72)}
                                    if r.description
                                    else {}
                                ),
                            }
                            for r in s.rows[:10]
                        ],
                    }
                    for s in msg.sections[:10]
                ],
            },
        }
        if msg.header:
            interactive["header"] = {"type": "text", "text": _t(msg.header, 60)}
        if msg.footer:
            interactive["footer"] = {"text": _t(msg.footer, 60)}
        return _envelope(to, {"type": "interactive", "interactive": interactive})

    raise TypeError(f"Unknown outbound message type: {type(msg)!r}")


def to_payloads(reply: AgentReply, to: str) -> list[dict[str, Any]]:
    """One Graph API payload per message in the reply, in order."""
    return [_render_one(m, to) for m in reply.messages]
