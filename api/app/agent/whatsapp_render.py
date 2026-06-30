"""Render a validated ``AgentReply`` into WhatsApp Cloud API message payloads.

Pure mapping (no LangChain / no network) so it's unit-testable. The schema already
constrains lengths and the 10-row list limit; this layer applies the same limits
*defensively* — plus newline stripping on short fields and markdown -> WhatsApp bold
normalization — so a payload can never be rejected by Meta or render wrong, even if an
upstream check is bypassed.
"""
from __future__ import annotations

import re
from typing import Any

from app.agent.schemas import (
    AgentReply,
    ButtonsMessage,
    ImageMessage,
    ListMessage,
    OutboundMessage,
    TextMessage,
)

_ELLIPSIS = "…"
# WhatsApp bold is a SINGLE asterisk; LLMs often emit markdown **bold**. Collapse runs of
# 2+ asterisks to one so it renders as bold instead of showing literal asterisks.
_MD_BOLD = re.compile(r"\*\*+")


def _t(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    return value if len(value) <= limit else value[: limit - 1].rstrip() + _ELLIPSIS


def _body(value: str | None, limit: int) -> str | None:
    """Free-text body/caption: normalize markdown bold to WhatsApp's single-asterisk style."""
    if value is None:
        return None
    return _t(_MD_BOLD.sub("*", value), limit)


def _line(value: str | None, limit: int) -> str | None:
    """Short single-line field (titles, button, header, footer). WhatsApp rejects newlines/tabs,
    so collapse all whitespace, then truncate."""
    if value is None:
        return None
    return _t(" ".join(value.split()), limit)


def _id(value: str, limit: int) -> str:
    return value.strip()[:limit]


def _envelope(to: str, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        **body,
    }


def _list_sections(msg: ListMessage) -> list[dict[str, Any]]:
    """Sections + rows, capped at 10 rows TOTAL across sections (WhatsApp's hard limit)."""
    sections: list[dict[str, Any]] = []
    remaining = 10
    for s in msg.sections[:10]:
        if remaining <= 0:
            break
        rows: list[dict[str, Any]] = []
        for r in s.rows[:remaining]:
            row: dict[str, Any] = {"id": _id(r.id, 200), "title": _line(r.title, 24)}
            if r.description:
                row["description"] = _line(r.description, 72)
            rows.append(row)
        remaining -= len(rows)
        if rows:
            sections.append({"title": _line(s.title, 24), "rows": rows})
    return sections


def _render_one(msg: OutboundMessage, to: str) -> dict[str, Any]:
    if isinstance(msg, TextMessage):
        return _envelope(to, {"type": "text", "text": {"body": _body(msg.body, 4096)}})

    if isinstance(msg, ImageMessage):
        image: dict[str, Any] = {"link": msg.image_url}
        if msg.caption:
            image["caption"] = _body(msg.caption, 1024)
        return _envelope(to, {"type": "image", "image": image})

    if isinstance(msg, ButtonsMessage):
        return _envelope(
            to,
            {
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": _body(msg.body, 1024)},
                    "action": {
                        "buttons": [
                            {
                                "type": "reply",
                                "reply": {"id": _id(b.id, 256), "title": _line(b.title, 20)},
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
            "body": {"text": _body(msg.body, 1024)},
            "action": {"button": _line(msg.button, 20), "sections": _list_sections(msg)},
        }
        if msg.header:
            interactive["header"] = {"type": "text", "text": _line(msg.header, 60)}
        if msg.footer:
            interactive["footer"] = {"text": _line(msg.footer, 60)}
        return _envelope(to, {"type": "interactive", "interactive": interactive})

    raise TypeError(f"Unknown outbound message type: {type(msg)!r}")


def to_payloads(reply: AgentReply, to: str) -> list[dict[str, Any]]:
    """One Graph API payload per message in the reply, in order."""
    return [_render_one(m, to) for m in reply.messages]
