"""WhatsApp Cloud API connection schemas."""
from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class WhatsAppConnectionIn(BaseModel):
    mode: Literal["test", "live"] = "test"
    waba_id: str = Field(min_length=1, max_length=64)
    phone_number_id: str = Field(min_length=1, max_length=64)
    display_phone_number: str | None = Field(default=None, max_length=32)
    display_name: str | None = Field(default=None, max_length=255)
    access_token: str | None = Field(default=None, min_length=1, max_length=4096)


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
