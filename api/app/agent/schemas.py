"""Structured WhatsApp output — the agent's reply is a validated Pydantic object.

The agent never emits free-form WhatsApp JSON. `create_agent(response_format=...)`
forces the final turn into `AgentReply`, and the renderer (`whatsapp_render.py`)
maps it 1:1 to Graph API payloads. WhatsApp's hard limits are encoded as field
constraints here (verified against the Cloud API docs), so an invalid interactive
message can't even be constructed:

  text body        <= 4096        list: <= 10 sections, <= 10 rows TOTAL
  list row title   <= 24          list row description <= 72
  reply buttons    <= 3           button title <= 20
  header/footer    <= 60          image caption <= 1024

No LangChain import here on purpose — keep this unit-testable standalone.
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class TextMessage(BaseModel):
    kind: Literal["text"] = "text"
    body: str = Field(max_length=4096)


class ListRow(BaseModel):
    # Self-describing ids let the worker interpret a tap deterministically:
    # "product:<uuid>", "confirm_order", "edit_cart", "cancel_order".
    id: str = Field(max_length=200)
    title: str = Field(max_length=24)
    description: str | None = Field(default=None, max_length=72)


class ListSection(BaseModel):
    title: str = Field(max_length=24)
    rows: list[ListRow] = Field(min_length=1, max_length=10)


class ListMessage(BaseModel):
    kind: Literal["list"] = "list"
    header: str | None = Field(default=None, max_length=60)
    body: str = Field(max_length=1024)
    footer: str | None = Field(default=None, max_length=60)
    button: str = Field(max_length=20)
    sections: list[ListSection] = Field(min_length=1, max_length=10)


class ReplyButton(BaseModel):
    id: str = Field(max_length=256)
    title: str = Field(max_length=20)


class ButtonsMessage(BaseModel):
    kind: Literal["buttons"] = "buttons"
    body: str = Field(max_length=1024)
    buttons: list[ReplyButton] = Field(min_length=1, max_length=3)


class ImageMessage(BaseModel):
    kind: Literal["image"] = "image"
    image_url: str
    caption: str | None = Field(default=None, max_length=1024)


OutboundMessage = Annotated[
    Union[TextMessage, ListMessage, ButtonsMessage, ImageMessage],
    Field(discriminator="kind"),
]


class AgentReply(BaseModel):
    """The agent's full response to one inbound turn (1..4 WhatsApp messages).

    Example: "show me the burger" -> [ImageMessage(burger), ButtonsMessage("Add it?")].
    """

    messages: list[OutboundMessage] = Field(min_length=1, max_length=4)
    handoff: bool = False


# Stable button / row id prefixes the worker recognizes deterministically.
BTN_CONFIRM = "confirm_order"
BTN_EDIT = "edit_cart"
BTN_CANCEL = "cancel_order"
ROW_PRODUCT_PREFIX = "product:"
