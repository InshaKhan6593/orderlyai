"""Category, product, and modifier (option group/item) schemas."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

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
class ModifierOptionIn(BaseModel):
    id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=500)
    price_delta: Decimal = Field(default=Decimal("0"))
    is_default: bool = False
    sort_order: int = 0


class ModifierOptionOut(ORMModel):
    id: uuid.UUID
    name: str
    description: str | None
    price_delta: Decimal
    is_default: bool
    sort_order: int


class ModifierGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    select_type: str = Field(default="single", pattern="^(single|multi)$")
    is_template: bool = True
    items: list[ModifierOptionIn] = Field(default_factory=list)


class ModifierGroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    select_type: str | None = Field(default=None, pattern="^(single|multi)$")
    is_template: bool | None = None
    items: list[ModifierOptionIn] | None = None


class ModifierGroupOut(ORMModel):
    id: uuid.UUID
    business_id: uuid.UUID
    name: str
    display_name: str
    select_type: str
    is_template: bool
    items: list[ModifierOptionOut]


class ProductModifierOptionPriceIn(BaseModel):
    option_id: uuid.UUID
    price_delta: Decimal | None = None
    is_default: bool = False


class ProductModifierAssignmentIn(BaseModel):
    modifier_group_id: uuid.UUID | None = None
    definition: ModifierGroupCreate | None = None
    is_required: bool = False
    min_select: int = Field(default=0, ge=0)
    max_select: int | None = Field(default=None, ge=0)
    sort_order: int = 0
    items: list[ProductModifierOptionPriceIn] | None = None

    @model_validator(mode="after")
    def validate_selection_range(self):
        if self.modifier_group_id is None and self.definition is None:
            raise ValueError("modifier_group_id or definition is required")
        if self.max_select is not None and self.max_select < self.min_select:
            raise ValueError("max_select must be greater than or equal to min_select")
        return self


class ProductModifierOptionOut(ORMModel):
    id: uuid.UUID
    name: str
    description: str | None
    price_delta: Decimal
    price_delta_override: Decimal | None
    is_default: bool
    sort_order: int


class ProductModifierAssignmentOut(ORMModel):
    assignment_id: uuid.UUID
    modifier_group_id: uuid.UUID
    name: str
    display_name: str
    select_type: str
    is_template: bool
    is_required: bool
    min_select: int
    max_select: int | None
    sort_order: int
    items: list[ProductModifierOptionOut]


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
    modifier_groups: list[ProductModifierAssignmentIn] = Field(default_factory=list)


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
    # If provided, replaces every modifier-group assignment for the product.
    modifier_groups: list[ProductModifierAssignmentIn] | None = None


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
    modifier_groups: list[ProductModifierAssignmentOut]


class ProductImageUploadOut(BaseModel):
    image_url: str
