"""Customer read endpoints (customers are created by the order flow)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter
from sqlalchemy import select

from app.core.deps import BusinessDep, DbSession
from app.core.errors import NotFoundError
from app.models.customer import Customer
from app.schemas.customer import CustomerOut

router = APIRouter(prefix="/businesses/{business_id}/customers", tags=["customers"])


@router.get("", response_model=list[CustomerOut])
async def list_customers(business: BusinessDep, db: DbSession) -> list[Customer]:
    rows = await db.execute(
        select(Customer)
        .where(Customer.business_id == business.id)
        .order_by(Customer.last_order_at.desc().nullslast())
    )
    return list(rows.scalars().all())


@router.get("/{customer_id}", response_model=CustomerOut)
async def get_customer(customer_id: uuid.UUID, business: BusinessDep, db: DbSession) -> Customer:
    customer = await db.get(Customer, customer_id)
    if customer is None or customer.business_id != business.id:
        raise NotFoundError("Customer not found")
    return customer
