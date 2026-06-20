"""Business CRUD (the tenant root)."""
from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import select

from app.core.deps import BusinessDep, CurrentUser, DbSession
from app.models.business import Business, Membership
from app.schemas.business import BusinessCreate, BusinessOut, BusinessUpdate
from app.services import business_service

router = APIRouter(tags=["businesses"])


@router.post("/businesses", response_model=BusinessOut, status_code=status.HTTP_201_CREATED)
async def create_business(data: BusinessCreate, user: CurrentUser, db: DbSession) -> Business:
    return await business_service.create_business(db, user, data)


@router.get("/businesses", response_model=list[BusinessOut])
async def list_my_businesses(user: CurrentUser, db: DbSession) -> list[Business]:
    rows = await db.execute(
        select(Business)
        .join(Membership, Membership.business_id == Business.id)
        .where(Membership.user_id == user.id)
        .order_by(Business.created_at)
    )
    return list(rows.scalars().all())


@router.get("/businesses/{business_id}", response_model=BusinessOut)
async def get_business(business: BusinessDep) -> Business:
    return business


@router.patch("/businesses/{business_id}", response_model=BusinessOut)
async def update_business(data: BusinessUpdate, business: BusinessDep, db: DbSession) -> Business:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(business, field, value)
    await db.commit()
    await db.refresh(business)
    return business
