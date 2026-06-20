"""Business request/response schemas."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel

_TYPE = "^(restaurant|cafe|bakery|home_kitchen|other)$"
_STATUS = "^(onboarding|active|paused|suspended)$"


class BusinessCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    type: str = Field(pattern=_TYPE)
    timezone: str = "UTC"
    currency: str = "PKR"


class BusinessUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    type: str | None = Field(default=None, pattern=_TYPE)
    description: str | None = None
    logo_url: str | None = None
    cover_url: str | None = None
    timezone: str | None = None
    currency: str | None = None
    languages: list[str] | None = None
    helpline_phone: str | None = None
    email: str | None = None
    address: str | None = None
    maps_url: str | None = None
    offers_delivery: bool | None = None
    offers_pickup: bool | None = None
    min_order_amount: Decimal | None = Field(default=None, ge=0)
    default_prep_minutes: int | None = Field(default=None, ge=0)
    packaging_fee: Decimal | None = Field(default=None, ge=0)
    accepting_orders: bool | None = None
    status: str | None = Field(default=None, pattern=_STATUS)


class BusinessOut(ORMModel):
    id: uuid.UUID
    name: str
    slug: str
    type: str
    description: str | None
    logo_url: str | None
    cover_url: str | None
    timezone: str
    currency: str
    languages: list[str]
    helpline_phone: str | None
    email: str | None
    address: str | None
    maps_url: str | None
    offers_delivery: bool
    offers_pickup: bool
    min_order_amount: Decimal
    default_prep_minutes: int
    packaging_fee: Decimal
    accepting_orders: bool
    status: str
    plan_code: str
    created_at: datetime
