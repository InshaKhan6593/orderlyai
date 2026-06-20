"""Order request/response schemas."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel

_STATUS = (
    "^(pending|accepted|rejected|preparing|ready|out_for_delivery|completed|cancelled)$"
)


class OrderLineIn(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(ge=1)
    option_item_ids: list[uuid.UUID] = Field(default_factory=list)


class OrderCreate(BaseModel):
    customer_phone: str = Field(min_length=3, max_length=32)
    customer_name: str | None = None
    fulfillment: str = Field(pattern="^(delivery|pickup)$")
    address: str | None = None
    zone_id: uuid.UUID | None = None
    payment_method: str = Field(default="cod", pattern="^(cod|link|paid)$")
    notes: str | None = None
    items: list[OrderLineIn] = Field(min_length=1)


class OrderStatusUpdate(BaseModel):
    status: str = Field(pattern=_STATUS)
    changed_by: str | None = None


class OrderItemOut(ORMModel):
    id: uuid.UUID
    product_id: uuid.UUID | None
    name_snapshot: str
    price_snapshot: Decimal
    quantity: int
    options_json: list[dict[str, Any]]
    line_total: Decimal


class OrderStatusHistoryOut(ORMModel):
    id: uuid.UUID
    status: str
    changed_by: str | None
    created_at: datetime


class OrderOut(ORMModel):
    id: uuid.UUID
    business_id: uuid.UUID
    customer_id: uuid.UUID
    order_no: int
    channel: str
    status: str
    fulfillment: str
    address: str | None
    zone_id: uuid.UUID | None
    subtotal: Decimal
    delivery_fee: Decimal
    packaging_fee: Decimal
    total: Decimal
    payment_method: str
    payment_status: str
    notes: str | None
    created_at: datetime
    items: list[OrderItemOut] = Field(default_factory=list)
    status_history: list[OrderStatusHistoryOut] = Field(default_factory=list)
