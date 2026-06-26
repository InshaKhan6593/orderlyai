"""Order endpoints — list, create (server-priced), get, advance status."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.deps import BusinessDep, CurrentUser, DbSession
from app.core.errors import BadRequestError
from app.models.order import Order
from app.schemas.order import OrderCreate, OrderOut, OrderStatusUpdate
from app.services import notification_service, order_service

router = APIRouter(prefix="/businesses/{business_id}/orders", tags=["orders"])


@router.get("", response_model=list[OrderOut])
async def list_orders(
    business: BusinessDep,
    db: DbSession,
    status_filter: str | None = Query(default=None, alias="status"),
    fulfillment: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[Order]:
    stmt = (
        select(Order)
        .where(Order.business_id == business.id)
        .options(
            selectinload(Order.customer),
            selectinload(Order.zone),
            selectinload(Order.items),
            selectinload(Order.status_history),
        )
        .order_by(Order.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if status_filter:
        stmt = stmt.where(Order.status == status_filter)
    if fulfillment:
        stmt = stmt.where(Order.fulfillment == fulfillment)
    rows = await db.execute(stmt)
    return list(rows.scalars().all())


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def create_order(data: OrderCreate, business: BusinessDep, db: DbSession) -> Order:
    if not business.accepting_orders:
        raise BadRequestError("This business is not accepting orders right now")
    return await order_service.create_order(db, business, data)


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(order_id: uuid.UUID, business: BusinessDep, db: DbSession) -> Order:
    return await order_service.load_order(db, business.id, order_id)


@router.patch("/{order_id}/status", response_model=OrderOut)
async def update_order_status(
    order_id: uuid.UUID,
    data: OrderStatusUpdate,
    business: BusinessDep,
    user: CurrentUser,
    db: DbSession,
    background_tasks: BackgroundTasks,
) -> Order:
    # Lock the row so concurrent status changes serialize, and record the
    # authenticated user as the auditor (never a client-supplied value).
    order = await order_service.load_order(db, business.id, order_id, for_update=True)
    updated = await order_service.update_status(db, order, data.status, changed_by=str(user.id))
    # Tell the customer on WhatsApp (best-effort, after the response — never blocks the owner).
    if settings.whatsapp_notify_on_status_change:
        background_tasks.add_task(
            notification_service.notify_order_status, business.id, updated.id
        )
    return updated
