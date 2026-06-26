"""Customer schemas (responses + agent-collected contact details)."""
from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import ORMModel


def _blank_to_none(value: object) -> object:
    if value is None:
        return None
    cleaned = " ".join(str(value).split()).strip()
    return cleaned or None


class ContactDetails(BaseModel):
    """Validated customer contact details collected by the agent at checkout.

    Optional at the schema level — which are *required* to place an order is enforced in the
    ordering flow (name always; a delivery address for delivery). Email and phone are format-
    validated so a typo is caught before it is saved to the customer record.
    """

    name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = None
    alternate_phone: str | None = Field(default=None, max_length=32)

    @field_validator("name", "email", "alternate_phone", mode="before")
    @classmethod
    def _clean(cls, value: object) -> object:
        return _blank_to_none(value)

    @field_validator("alternate_phone")
    @classmethod
    def _valid_phone(cls, value: str | None) -> str | None:
        if value is not None and not 7 <= len(re.sub(r"\D", "", value)) <= 15:
            raise ValueError("Enter a valid phone number (7-15 digits, may start with +).")
        return value


class CustomerOut(ORMModel):
    id: uuid.UUID
    business_id: uuid.UUID
    wa_phone: str
    name: str | None
    email: str | None
    alternate_phone: str | None
    default_address: str | None
    order_count: int
    last_order_at: datetime | None
    marketing_opt_in: bool
    created_at: datetime
