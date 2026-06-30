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


def test_button_title_is_sanitized_to_whatsapp_limit():
    button = ReplyButton(id="confirm_order", title="Confirm Order Please")

    assert len(button.title) <= 20
    assert button.title.startswith("Confirm Order")


def test_at_most_three_buttons():
    with pytest.raises(ValidationError):
        ButtonsMessage(
            kind="buttons",
            body="Pick",
            buttons=[ReplyButton(id=f"b{i}", title=f"b{i}") for i in range(4)],
        )


def test_list_row_title_is_sanitized_to_whatsapp_limit():
    row = ListRow(id="product:1", title="All American Cheese Burger")

    assert len(row.title) <= 24
    assert row.title.startswith("All American Cheese")


def test_list_short_fields_collapse_whitespace_before_validation():
    msg = ListMessage(
        kind="list",
        header="Burgers\nMenu",
        body="Choose one",
        button="Pick\tItem",
        sections=[
            ListSection(
                title="Burger\nOptions",
                rows=[ListRow(id="product:1", title="Big\nSmoky\tBurger")],
            )
        ],
    )

    assert msg.header == "Burgers Menu"
    assert msg.button == "Pick Item"
    assert msg.sections[0].title == "Burger Options"
    assert msg.sections[0].rows[0].title == "Big Smoky Burger"


def test_discriminated_union_parses_from_dict():
    reply = AgentReply.model_validate(
        {"messages": [{"kind": "text", "body": "hello"}]}
    )
    assert isinstance(reply.messages[0], TextMessage)


def test_message_without_kind_is_rejected():
    # Regression: every message must carry its `kind` discriminator. A list-shaped message
    # missing `kind` (sections + button, no `kind`) is exactly what produced union_tag_not_found.
    with pytest.raises(ValidationError):
        AgentReply.model_validate(
            {"messages": [{"body": "x", "button": "Add", "sections": []}]}
        )


def test_render_list_buttons_image_text_payloads():
    reply = AgentReply(
        messages=[
            ListMessage(
                kind="list",
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
                kind="buttons",
                body="Confirm your order?",
                buttons=[
                    ReplyButton(id="confirm_order", title="Confirm"),
                    ReplyButton(id="cancel_order", title="Cancel"),
                ],
            ),
            ImageMessage(kind="image", image_url="https://x/y.jpg", caption="Cola - 100 PKR"),
            TextMessage(kind="text", body="Anything else?"),
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


def test_image_message_accepts_body_as_caption_alias():
    # Regression: the model often emits `body` (like text/list/buttons) for an image instead of
    # `caption`; it must map to the caption, not be silently dropped (which sent a bare photo).
    reply = AgentReply.model_validate(
        {
            "messages": [
                {
                    "kind": "image",
                    "image_url": "https://x/y.jpg",
                    "body": "*Double Cheese Burger* - 1895 PKR. Add to cart?",
                }
            ]
        }
    )
    img = to_payloads(reply, to="1")[0]
    assert img["type"] == "image"
    assert img["image"]["link"] == "https://x/y.jpg"
    assert "Double Cheese Burger" in img["image"]["caption"]


def test_render_truncates_long_text_defensively():
    reply = AgentReply(messages=[TextMessage(kind="text", body="a" * 4096)])
    body = to_payloads(reply, to="1")[0]["text"]["body"]
    assert len(body) <= 4096


def test_list_rejects_more_than_10_rows_total():
    # WhatsApp hard limit: at most 10 rows across all sections.
    s1 = ListSection(title="A", rows=[ListRow(id=f"product:a{i}", title=f"A{i}") for i in range(6)])
    s2 = ListSection(title="B", rows=[ListRow(id=f"product:b{i}", title=f"B{i}") for i in range(6)])
    with pytest.raises(ValidationError):
        ListMessage(kind="list", body="Menu", button="View", sections=[s1, s2])  # 12 rows


def test_list_rejects_duplicate_row_ids():
    with pytest.raises(ValidationError):
        ListMessage(
            kind="list",
            body="Menu",
            button="View",
            sections=[
                ListSection(
                    title="A",
                    rows=[
                        ListRow(id="product:x", title="One"),
                        ListRow(id="product:x", title="Two"),  # duplicate id
                    ],
                )
            ],
        )


def test_render_converts_markdown_bold_to_whatsapp():
    # LLMs emit **bold**; WhatsApp wants *bold*. The renderer normalizes it.
    reply = AgentReply(messages=[TextMessage(kind="text", body="Try **Guns N Smoke**!")])
    body = to_payloads(reply, to="1")[0]["text"]["body"]
    assert body == "Try *Guns N Smoke*!"
    assert "**" not in body


def test_render_strips_newlines_in_list_titles():
    # WhatsApp rejects newlines/tabs in interactive titles; the renderer flattens them.
    reply = AgentReply(
        messages=[
            ListMessage(
                kind="list",
                body="Menu",
                button="View",
                sections=[
                    ListSection(
                        title="Burgers",
                        rows=[ListRow(id="product:1", title="Big\nSmoky\tBurger")],
                    )
                ],
            )
        ]
    )
    row = to_payloads(reply, to="1")[0]["interactive"]["action"]["sections"][0]["rows"][0]
    assert row["title"] == "Big Smoky Burger"
