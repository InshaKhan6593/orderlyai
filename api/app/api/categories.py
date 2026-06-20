"""Category CRUD (scoped to a business)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from sqlalchemy import select

from app.core.deps import BusinessDep, DbSession
from app.core.errors import NotFoundError
from app.models.menu import Category
from app.schemas.menu import CategoryCreate, CategoryOut, CategoryUpdate

router = APIRouter(prefix="/businesses/{business_id}/categories", tags=["menu"])


async def _get(db, business_id, category_id) -> Category:
    cat = await db.get(Category, category_id)
    if cat is None or cat.business_id != business_id:
        raise NotFoundError("Category not found")
    return cat


@router.get("", response_model=list[CategoryOut])
async def list_categories(business: BusinessDep, db: DbSession) -> list[Category]:
    rows = await db.execute(
        select(Category)
        .where(Category.business_id == business.id)
        .order_by(Category.sort_order, Category.name)
    )
    return list(rows.scalars().all())


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
async def create_category(data: CategoryCreate, business: BusinessDep, db: DbSession) -> Category:
    cat = Category(business_id=business.id, **data.model_dump())
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return cat


@router.patch("/{category_id}", response_model=CategoryOut)
async def update_category(
    category_id: uuid.UUID, data: CategoryUpdate, business: BusinessDep, db: DbSession
) -> Category:
    cat = await _get(db, business.id, category_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(cat, field, value)
    await db.commit()
    await db.refresh(cat)
    return cat


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(category_id: uuid.UUID, business: BusinessDep, db: DbSession) -> None:
    cat = await _get(db, business.id, category_id)
    await db.delete(cat)
    await db.commit()
