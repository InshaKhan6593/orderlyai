"""Business hours and delivery zone schemas."""
from __future__ import annotations

import uuid
from datetime import time
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORMModel


class HoursItem(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    open_time: time | None = None
    close_time: time | None = None
    is_closed: bool = False


class HoursBulkIn(BaseModel):
    hours: list[HoursItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def _no_duplicate_days(self) -> "HoursBulkIn":
        days = [h.day_of_week for h in self.hours]
        if len(days) != len(set(days)):
            raise ValueError("duplicate day_of_week entries are not allowed")
        return self


class HoursOut(ORMModel):
    id: uuid.UUID
    day_of_week: int
    open_time: time | None
    close_time: time | None
    is_closed: bool


class ZoneCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    fee: Decimal = Field(default=Decimal("0"), ge=0)
    min_order: Decimal = Field(default=Decimal("0"), ge=0)
    eta_minutes: int | None = Field(default=None, ge=0)
    is_active: bool = True


class ZoneUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    fee: Decimal | None = Field(default=None, ge=0)
    min_order: Decimal | None = Field(default=None, ge=0)
    eta_minutes: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class ZoneOut(ORMModel):
    id: uuid.UUID
    business_id: uuid.UUID
    name: str
    fee: Decimal
    min_order: Decimal
    eta_minutes: int | None
    is_active: bool
