"""Menu: categories, products, and product option groups/items (modifiers)."""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.business import Business


class Category(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "categories"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    business: Mapped["Business"] = relationship(back_populates="categories")
    products: Mapped[list["Product"]] = relationship(back_populates="category")


class Product(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (CheckConstraint("price >= 0", name="product_price_nonneg"),)

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(512))
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    prep_minutes: Mapped[int | None] = mapped_column(Integer)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    business: Mapped["Business"] = relationship(back_populates="products")
    category: Mapped["Category | None"] = relationship(back_populates="products")
    modifier_groups: Mapped[list["ProductModifierGroup"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductModifierGroup.sort_order",
    )


class ModifierGroup(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "modifier_groups"
    __table_args__ = (
        CheckConstraint("select_type in ('single','multi')", name="modifier_group_select_type"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    select_type: Mapped[str] = mapped_column(String(16), default="single", nullable=False)
    is_template: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    business: Mapped["Business"] = relationship(back_populates="modifier_groups")
    items: Mapped[list["ModifierOption"]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
        order_by="ModifierOption.sort_order",
    )
    assignments: Mapped[list["ProductModifierGroup"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )


class ModifierOption(UUIDMixin, Base):
    __tablename__ = "modifier_options"

    group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("modifier_groups.id", ondelete="CASCADE"), index=True, nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    price_delta: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    group: Mapped["ModifierGroup"] = relationship(back_populates="items")


class EffectiveModifierOption:
    def __init__(
        self,
        option: ModifierOption,
        price_delta: Decimal,
        price_delta_override: Decimal | None,
        is_default: bool,
    ) -> None:
        self.id = option.id
        self.name = option.name
        self.description = option.description
        self.price_delta = price_delta
        self.price_delta_override = price_delta_override
        self.is_default = is_default
        self.sort_order = option.sort_order


class ProductModifierGroup(UUIDMixin, Base):
    __tablename__ = "product_modifier_groups"
    __table_args__ = (
        CheckConstraint("min_select >= 0", name="product_modifier_min_nonneg"),
        CheckConstraint(
            "max_select is null or max_select >= 0",
            name="product_modifier_max_nonneg",
        ),
        UniqueConstraint(
            "product_id", "modifier_group_id", name="product_modifier_group_once"
        ),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True, nullable=False
    )
    modifier_group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("modifier_groups.id", ondelete="CASCADE"), index=True, nullable=False
    )
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    min_select: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_select: Mapped[int | None] = mapped_column(Integer)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    product: Mapped["Product"] = relationship(back_populates="modifier_groups")
    group: Mapped["ModifierGroup"] = relationship(back_populates="assignments")
    option_prices: Mapped[list["ProductModifierOptionPrice"]] = relationship(
        back_populates="assignment",
        cascade="all, delete-orphan",
    )

    @property
    def assignment_id(self) -> uuid.UUID:
        return self.id

    @property
    def name(self) -> str:
        return self.group.name

    @property
    def display_name(self) -> str:
        return self.group.display_name

    @property
    def is_template(self) -> bool:
        return self.group.is_template

    @property
    def select_type(self) -> str:
        return self.group.select_type

    @property
    def items(self) -> list[EffectiveModifierOption]:
        options = {item.id: item for item in self.group.items}
        effective: list[EffectiveModifierOption] = []
        for config in self.option_prices:
            option = options.get(config.modifier_option_id)
            if option is None:
                continue
            effective.append(
                EffectiveModifierOption(
                    option,
                    config.price_delta
                    if config.price_delta is not None
                    else option.price_delta,
                    config.price_delta,
                    config.is_default,
                )
            )
        return sorted(effective, key=lambda item: item.sort_order)

    def price_delta_for(self, option_id: uuid.UUID) -> Decimal:
        options = {item.id: item for item in self.group.items}
        for config in self.option_prices:
            if config.modifier_option_id == option_id:
                if config.price_delta is not None:
                    return config.price_delta
                option = options.get(option_id)
                return option.price_delta if option is not None else Decimal("0")
        return Decimal("0")


class ProductModifierOptionPrice(UUIDMixin, Base):
    __tablename__ = "product_modifier_option_prices"
    __table_args__ = (
        UniqueConstraint(
            "product_modifier_group_id",
            "modifier_option_id",
            name="product_modifier_option_price_once",
        ),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    product_modifier_group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("product_modifier_groups.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    modifier_option_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("modifier_options.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    price_delta: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    assignment: Mapped["ProductModifierGroup"] = relationship(
        back_populates="option_prices"
    )
    option: Mapped["ModifierOption"] = relationship()
