"""Delivery zone CRUD (scoped to a business)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from sqlalchemy import select

from app.core.deps import BusinessDep, DbSession
from app.core.errors import NotFoundError
from app.models.ops import DeliveryZone
from app.schemas.ops import ZoneCreate, ZoneOut, ZoneUpdate

router = APIRouter(prefix="/businesses/{business_id}/delivery-zones", tags=["delivery"])


async def _get(db, business_id, zone_id) -> DeliveryZone:
    zone = await db.get(DeliveryZone, zone_id)
    if zone is None or zone.business_id != business_id:
        raise NotFoundError("Delivery zone not found")
    return zone


@router.get("", response_model=list[ZoneOut])
async def list_zones(business: BusinessDep, db: DbSession) -> list[DeliveryZone]:
    rows = await db.execute(
        select(DeliveryZone).where(DeliveryZone.business_id == business.id).order_by(DeliveryZone.name)
    )
    return list(rows.scalars().all())


@router.post("", response_model=ZoneOut, status_code=status.HTTP_201_CREATED)
async def create_zone(data: ZoneCreate, business: BusinessDep, db: DbSession) -> DeliveryZone:
    zone = DeliveryZone(business_id=business.id, **data.model_dump())
    db.add(zone)
    await db.commit()
    await db.refresh(zone)
    return zone


@router.patch("/{zone_id}", response_model=ZoneOut)
async def update_zone(
    zone_id: uuid.UUID, data: ZoneUpdate, business: BusinessDep, db: DbSession
) -> DeliveryZone:
    zone = await _get(db, business.id, zone_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(zone, field, value)
    await db.commit()
    await db.refresh(zone)
    return zone


@router.delete("/{zone_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_zone(zone_id: uuid.UUID, business: BusinessDep, db: DbSession) -> None:
    zone = await _get(db, business.id, zone_id)
    await db.delete(zone)
    await db.commit()
