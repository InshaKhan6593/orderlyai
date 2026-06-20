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
    option_groups: Mapped[list["ProductOptionGroup"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", order_by="ProductOptionGroup.sort_order"
    )


class ProductOptionGroup(UUIDMixin, Base):
    __tablename__ = "product_option_groups"
    __table_args__ = (
        CheckConstraint("select_type in ('single','multi')", name="option_group_select_type"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    select_type: Mapped[str] = mapped_column(String(16), default="single", nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    min_select: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_select: Mapped[int | None] = mapped_column(Integer)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    product: Mapped["Product"] = relationship(back_populates="option_groups")
    items: Mapped[list["ProductOptionItem"]] = relationship(
        back_populates="group", cascade="all, delete-orphan", order_by="ProductOptionItem.sort_order"
    )


class ProductOptionItem(UUIDMixin, Base):
    __tablename__ = "product_option_items"

    group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("product_option_groups.id", ondelete="CASCADE"), index=True, nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    price_delta: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    group: Mapped["ProductOptionGroup"] = relationship(back_populates="items")
