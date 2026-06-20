"""Business hours — read and bulk replace."""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import delete, select

from app.core.deps import BusinessDep, DbSession
from app.models.ops import BusinessHours
from app.schemas.ops import HoursBulkIn, HoursOut

router = APIRouter(prefix="/businesses/{business_id}/hours", tags=["hours"])


@router.get("", response_model=list[HoursOut])
async def get_hours(business: BusinessDep, db: DbSession) -> list[BusinessHours]:
    rows = await db.execute(
        select(BusinessHours)
        .where(BusinessHours.business_id == business.id)
        .order_by(BusinessHours.day_of_week)
    )
    return list(rows.scalars().all())


@router.put("", response_model=list[HoursOut])
async def replace_hours(
    data: HoursBulkIn, business: BusinessDep, db: DbSession
) -> list[BusinessHours]:
    await db.execute(delete(BusinessHours).where(BusinessHours.business_id == business.id))
    new_rows = [
        BusinessHours(business_id=business.id, **item.model_dump()) for item in data.hours
    ]
    db.add_all(new_rows)
    await db.commit()
    rows = await db.execute(
        select(BusinessHours)
        .where(BusinessHours.business_id == business.id)
        .order_by(BusinessHours.day_of_week)
    )
    return list(rows.scalars().all())
