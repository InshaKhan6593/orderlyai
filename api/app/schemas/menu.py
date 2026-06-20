"""Category, product, and modifier (option group/item) schemas."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


# ── Categories ──────────────────────────────────────
class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    sort_order: int = 0
    is_active: bool = True


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    sort_order: int | None = None
    is_active: bool | None = None


class CategoryOut(ORMModel):
    id: uuid.UUID
    business_id: uuid.UUID
    name: str
    sort_order: int
    is_active: bool
    created_at: datetime


# ── Modifiers ───────────────────────────────────────
class OptionItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    price_delta: Decimal = Field(default=Decimal("0"))
    is_default: bool = False
    sort_order: int = 0


class OptionItemOut(ORMModel):
    id: uuid.UUID
    name: str
    price_delta: Decimal
    is_default: bool
    sort_order: int


class OptionGroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    select_type: str = Field(default="single", pattern="^(single|multi)$")
    is_required: bool = False
    min_select: int = Field(default=0, ge=0)
    max_select: int | None = Field(default=None, ge=0)
    sort_order: int = 0
    items: list[OptionItemIn] = Field(default_factory=list)


class OptionGroupOut(ORMModel):
    id: uuid.UUID
    name: str
    select_type: str
    is_required: bool
    min_select: int
    max_select: int | None
    sort_order: int
    items: list[OptionItemOut]


# ── Products ────────────────────────────────────────
class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    category_id: uuid.UUID | None = None
    description: str | None = None
    price: Decimal = Field(ge=0)
    image_url: str | None = None
    is_available: bool = True
    tags: list[str] = Field(default_factory=list)
    prep_minutes: int | None = Field(default=None, ge=0)
    sort_order: int = 0
    option_groups: list[OptionGroupIn] = Field(default_factory=list)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    category_id: uuid.UUID | None = None
    description: str | None = None
    price: Decimal | None = Field(default=None, ge=0)
    image_url: str | None = None
    is_available: bool | None = None
    is_archived: bool | None = None
    tags: list[str] | None = None
    prep_minutes: int | None = Field(default=None, ge=0)
    sort_order: int | None = None
    # If provided, replaces ALL option groups for the product.
    option_groups: list[OptionGroupIn] | None = None


class ProductOut(ORMModel):
    id: uuid.UUID
    business_id: uuid.UUID
    category_id: uuid.UUID | None
    name: str
    description: str | None
    price: Decimal
    image_url: str | None
    is_available: bool
    is_archived: bool
    tags: list[str]
    prep_minutes: int | None
    sort_order: int
    option_groups: list[OptionGroupOut]
