"""Structured WhatsApp output: schema constraints + Graph API rendering.

Pure unit tests — no DB, no LangChain, no network. Guards the contract that the
agent's reply can only ever serialize to a WhatsApp-valid payload.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent.schemas import (
    AgentReply,
    ButtonsMessage,
    ImageMessage,
    ListMessage,
    ListRow,
    ListSection,
    ReplyButton,
    TextMessage,
)
from app.agent.whatsapp_render import to_payloads


def test_button_title_limit_enforced():
    with pytest.raises(ValidationError):
        ReplyButton(id="confirm_order", title="x" * 21)  # max 20


def test_at_most_three_buttons():
    with pytest.raises(ValidationError):
        ButtonsMessage(
            body="Pick",
            buttons=[ReplyButton(id=f"b{i}", title=f"b{i}") for i in range(4)],
        )


def test_list_row_title_limit_enforced():
    with pytest.raises(ValidationError):
        ListRow(id="product:1", title="x" * 25)  # max 24


def test_discriminated_union_parses_from_dict():
    reply = AgentReply.model_validate(
        {"messages": [{"kind": "text", "body": "hello"}]}
    )
    assert isinstance(reply.messages[0], TextMessage)


def test_render_list_buttons_image_text_payloads():
    reply = AgentReply(
        messages=[
            ListMessage(
                body="Our menu",
                button="View",
                sections=[
                    ListSection(
                        title="Drinks",
                        rows=[ListRow(id="product:abc", title="Cola", description="100 PKR")],
                    )
                ],
            ),
            ButtonsMessage(
                body="Confirm your order?",
                buttons=[
                    ReplyButton(id="confirm_order", title="Confirm"),
                    ReplyButton(id="cancel_order", title="Cancel"),
                ],
            ),
            ImageMessage(image_url="https://x/y.jpg", caption="Cola — 100 PKR"),
            TextMessage(body="Anything else?"),
        ]
    )
    payloads = to_payloads(reply, to="923001234567")
    assert len(payloads) == 4

    lst, btns, img, txt = payloads
    assert all(p["messaging_product"] == "whatsapp" for p in payloads)
    assert all(p["to"] == "923001234567" for p in payloads)

    assert lst["type"] == "interactive" and lst["interactive"]["type"] == "list"
    assert lst["interactive"]["action"]["sections"][0]["rows"][0]["id"] == "product:abc"

    assert btns["interactive"]["type"] == "button"
    replies = [b["reply"]["id"] for b in btns["interactive"]["action"]["buttons"]]
    assert replies == ["confirm_order", "cancel_order"]

    assert img["type"] == "image" and img["image"]["link"] == "https://x/y.jpg"
    assert txt["type"] == "text" and txt["text"]["body"] == "Anything else?"


def test_render_truncates_long_text_defensively():
    reply = AgentReply(messages=[TextMessage(body="a" * 4096)])
    body = to_payloads(reply, to="1")[0]["text"]["body"]
    assert len(body) <= 4096
