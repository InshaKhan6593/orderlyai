"""AI assistant configuration schemas."""
from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class AgentConfigIn(BaseModel):
    greeting_message: str | None = Field(default=None, min_length=1, max_length=500)
    upsell_enabled: bool | None = None
    human_handoff_phone: str | None = Field(default=None, max_length=32)
    extra_instructions: str | None = Field(default=None, max_length=1000)


class AgentConfigOut(ORMModel):
    id: uuid.UUID | None
    business_id: uuid.UUID
    greeting_message: str
    language: str
    upsell_enabled: bool
    human_handoff_phone: str | None
    extra_instructions: str | None
