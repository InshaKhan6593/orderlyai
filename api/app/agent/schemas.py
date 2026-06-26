"""Structured WhatsApp output — the agent's reply is a validated Pydantic object.

The agent never emits free-form WhatsApp JSON. `create_agent(response_format=...)`
forces the final turn into `AgentReply`, and the renderer (`whatsapp_render.py`)
maps it 1:1 to Graph API payloads. WhatsApp's hard limits are encoded as field
constraints here (verified against the Cloud API docs). User-visible strings are
normalized before validation so model-copied menu names cannot break exact WhatsApp
length limits:

  text body        <= 4096        list: <= 10 sections, <= 10 rows TOTAL
  list row title   <= 24          list row description <= 72
  reply buttons    <= 3           button title <= 20
  header/footer    <= 60          image caption <= 1024

No LangChain import here on purpose — keep this unit-testable standalone.
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator, model_validator


_TRUNCATION_SUFFIX = "..."


def _clip(value: object, limit: int, *, single_line: bool = False) -> object:
    if not isinstance(value, str):
        return value
    text = " ".join(value.split()) if single_line else value
    if len(text) <= limit:
        return text
    if limit <= len(_TRUNCATION_SUFFIX):
        return text[:limit]
    head = text[: limit - len(_TRUNCATION_SUFFIX)].rstrip()
    if single_line:
        word_boundary = head.rfind(" ")
        if word_boundary >= limit // 2:
            head = head[:word_boundary].rstrip()
    return (head or text[: limit - len(_TRUNCATION_SUFFIX)]) + _TRUNCATION_SUFFIX


def _clip_text(value: object, limit: int) -> object:
    return _clip(value, limit)


def _clip_line(value: object, limit: int) -> object:
    return _clip(value, limit, single_line=True)


# `kind` is REQUIRED on every message (no default on purpose): the model must emit the
# discriminator, or the OutboundMessage union can't be resolved (union_tag_not_found).
# Do not give `kind` a default — that marks it optional in the tool schema and the model drops it.
class TextMessage(BaseModel):
    kind: Literal["text"]
    body: str = Field(max_length=4096)

    @field_validator("body", mode="before")
    @classmethod
    def _sanitize_body(cls, value: object) -> object:
        return _clip_text(value, 4096)


class ListRow(BaseModel):
    # Self-describing ids let the worker interpret a tap deterministically:
    # "product:<uuid>", "confirm_order", "edit_cart", "cancel_order".
    id: str = Field(max_length=200)
    title: str = Field(max_length=24)
    description: str | None = Field(default=None, max_length=72)

    @field_validator("title", mode="before")
    @classmethod
    def _sanitize_title(cls, value: object) -> object:
        return _clip_line(value, 24)

    @field_validator("description", mode="before")
    @classmethod
    def _sanitize_description(cls, value: object) -> object:
        return _clip_line(value, 72)


class ListSection(BaseModel):
    title: str = Field(max_length=24)
    rows: list[ListRow] = Field(min_length=1, max_length=10)

    @field_validator("title", mode="before")
    @classmethod
    def _sanitize_title(cls, value: object) -> object:
        return _clip_line(value, 24)


class ListMessage(BaseModel):
    kind: Literal["list"]
    header: str | None = Field(default=None, max_length=60)
    body: str = Field(max_length=1024)
    footer: str | None = Field(default=None, max_length=60)
    button: str = Field(max_length=20)
    sections: list[ListSection] = Field(min_length=1, max_length=10)

    @field_validator("header", "footer", mode="before")
    @classmethod
    def _sanitize_header_footer(cls, value: object) -> object:
        return _clip_line(value, 60)

    @field_validator("body", mode="before")
    @classmethod
    def _sanitize_body(cls, value: object) -> object:
        return _clip_text(value, 1024)

    @field_validator("button", mode="before")
    @classmethod
    def _sanitize_button(cls, value: object) -> object:
        return _clip_line(value, 20)

    @model_validator(mode="after")
    def _whatsapp_list_limits(self) -> "ListMessage":
        # WhatsApp caps a list at 10 rows TOTAL across all sections, and row ids must be
        # unique within the message. Field constraints can't express these, so enforce here —
        # an over-long or ambiguous list fails loudly (and the model is asked to fix it).
        rows = [r for s in self.sections for r in s.rows]
        if len(rows) > 10:
            raise ValueError(
                f"A WhatsApp list allows at most 10 rows total across sections; got {len(rows)}. "
                "Show the 10 best and offer to narrow down."
            )
        ids = [r.id for r in rows]
        if len(set(ids)) != len(ids):
            raise ValueError("WhatsApp list row ids must be unique within the message.")
        return self


class ReplyButton(BaseModel):
    id: str = Field(max_length=256)
    title: str = Field(max_length=20)

    @field_validator("title", mode="before")
    @classmethod
    def _sanitize_title(cls, value: object) -> object:
        return _clip_line(value, 20)


class ButtonsMessage(BaseModel):
    kind: Literal["buttons"]
    body: str = Field(max_length=1024)
    buttons: list[ReplyButton] = Field(min_length=1, max_length=3)

    @field_validator("body", mode="before")
    @classmethod
    def _sanitize_body(cls, value: object) -> object:
        return _clip_text(value, 1024)


class ImageMessage(BaseModel):
    kind: Literal["image"]
    image_url: str
    caption: str | None = Field(default=None, max_length=1024)

    @field_validator("caption", mode="before")
    @classmethod
    def _sanitize_caption(cls, value: object) -> object:
        return _clip_text(value, 1024)


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
