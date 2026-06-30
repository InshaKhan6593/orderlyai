"""WhatsApp Cloud API connection schemas."""
from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel


class WhatsAppConnectionIn(BaseModel):
    mode: Literal["test", "live"] = "test"
    waba_id: str = Field(min_length=1, max_length=64)
    phone_number_id: str = Field(min_length=1, max_length=64)
    display_phone_number: str | None = Field(default=None, max_length=32)
    display_name: str | None = Field(default=None, max_length=255)
    access_token: str | None = Field(default=None, min_length=1, max_length=4096)

    @field_validator("access_token")
    @classmethod
    def _ascii_access_token(cls, value: str | None) -> str | None:
        """Meta access tokens are plain ASCII. Trim copy-paste whitespace and reject any non-ASCII
        character (e.g. a "smart" em-dash/quote) up front — otherwise it only fails later, deep in
        the outbound send where an HTTP header can't be ASCII-encoded."""
        if value is None:
            return None
        token = value.strip()
        if not token:
            return None
        if not token.isascii():
            raise ValueError(
                "Access token must be plain ASCII - re-copy it from Meta (a smart dash or quote "
                "may have crept in via copy-paste)."
            )
        return token


class WhatsAppConnectionOut(ORMModel):
    id: uuid.UUID | None
    business_id: uuid.UUID
    mode: Literal["test", "live"]
    waba_id: str
    phone_number_id: str
    display_phone_number: str | None
    display_name: str | None
    status: Literal["not_configured", "configured", "verified", "error"]
    has_access_token: bool
