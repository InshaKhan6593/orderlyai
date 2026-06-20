"""Product CRUD with nested option groups/items (modifiers)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.deps import BusinessDep, DbSession
from app.core.errors import BadRequestError, NotFoundError
from app.models.menu import Category, Product, ProductOptionGroup, ProductOptionItem
from app.schemas.menu import OptionGroupIn, ProductCreate, ProductOut, ProductUpdate

router = APIRouter(prefix="/businesses/{business_id}/products", tags=["menu"])


async def _validate_category(db, business_id: uuid.UUID, category_id: uuid.UUID | None) -> None:
    """Reject a category that belongs to another tenant (or doesn't exist)."""
    if category_id is None:
        return
    owned = await db.scalar(
        select(Category.id).where(
            Category.id == category_id, Category.business_id == business_id
        )
    )
    if owned is None:
        raise BadRequestError("category_id does not belong to this business")


def _with_options():
    return selectinload(Product.option_groups).selectinload(ProductOptionGroup.items)


def _build_groups(
    business_id: uuid.UUID, groups: list[OptionGroupIn]
) -> list[ProductOptionGroup]:
    built: list[ProductOptionGroup] = []
    for g in groups:
        group = ProductOptionGroup(
            business_id=business_id,
            name=g.name,
            select_type=g.select_type,
            is_required=g.is_required,
            min_select=g.min_select,
            max_select=g.max_select,
            sort_order=g.sort_order,
        )
        group.items = [
            ProductOptionItem(
                business_id=business_id,
                name=i.name,
                price_delta=i.price_delta,
                is_default=i.is_default,
                sort_order=i.sort_order,
            )
            for i in g.items
        ]
        built.append(group)
    return built


async def _get(db, business_id: uuid.UUID, product_id: uuid.UUID) -> Product:
    product = await db.scalar(
        select(Product)
        .where(Product.id == product_id, Product.business_id == business_id)
        .options(_with_options())
    )
    if product is None:
        raise NotFoundError("Product not found")
    return product


@router.get("", response_model=list[ProductOut])
async def list_products(
    business: BusinessDep,
    db: DbSession,
    category_id: uuid.UUID | None = Query(default=None),
    include_archived: bool = Query(default=False),
) -> list[Product]:
    stmt = (
        select(Product)
        .where(Product.business_id == business.id)
        .options(_with_options())
        .order_by(Product.sort_order, Product.name)
    )
    if category_id is not None:
        stmt = stmt.where(Product.category_id == category_id)
    if not include_archived:
        stmt = stmt.where(Product.is_archived.is_(False))
    rows = await db.execute(stmt)
    return list(rows.scalars().all())


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(data: ProductCreate, business: BusinessDep, db: DbSession) -> Product:
    await _validate_category(db, business.id, data.category_id)
    product = Product(
        business_id=business.id,
        category_id=data.category_id,
        name=data.name,
        description=data.description,
        price=data.price,
        image_url=data.image_url,
        is_available=data.is_available,
        tags=data.tags,
        prep_minutes=data.prep_minutes,
        sort_order=data.sort_order,
    )
    product.option_groups = _build_groups(business.id, data.option_groups)
    db.add(product)
    await db.commit()
    return await _get(db, business.id, product.id)


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(product_id: uuid.UUID, business: BusinessDep, db: DbSession) -> Product:
    return await _get(db, business.id, product_id)


@router.patch("/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: uuid.UUID, data: ProductUpdate, business: BusinessDep, db: DbSession
) -> Product:
    product = await _get(db, business.id, product_id)
    payload = data.model_dump(exclude_unset=True)
    if payload.get("category_id") is not None:
        await _validate_category(db, business.id, payload["category_id"])
    groups = payload.pop("option_groups", None)
    for field, value in payload.items():
        setattr(product, field, value)
    if groups is not None:
        product.option_groups = _build_groups(
            business.id, [OptionGroupIn(**g) for g in groups]
        )
    await db.commit()
    return await _get(db, business.id, product.id)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(product_id: uuid.UUID, business: BusinessDep, db: DbSession) -> None:
    product = await _get(db, business.id, product_id)
    await db.delete(product)
    await db.commit()
