"""Order engine: server-side pricing, atomic order numbers, status transitions.

Pricing is authoritative here — the line total is always
``(product.price + Σ option deltas) × quantity`` computed from the DB, never trusted
from the client.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import BadRequestError, NotFoundError
from app.models.business import Business
from app.models.customer import Customer
from app.models.menu import Product, ProductOptionGroup
from app.models.order import Order, OrderItem, OrderStatusHistory
from app.models.ops import DeliveryZone
from app.schemas.order import OrderCreate

# Allowed status transitions (mirrors the dashboard state machine).
TRANSITIONS: dict[str, set[str]] = {
    "pending": {"accepted", "rejected", "cancelled"},
    "accepted": {"preparing", "cancelled"},
    "preparing": {"ready", "out_for_delivery", "cancelled"},
    "ready": {"completed", "cancelled"},
    "out_for_delivery": {"completed", "cancelled"},
    "completed": set(),
    "rejected": set(),
    "cancelled": set(),
}


async def load_order(db: AsyncSession, business_id: uuid.UUID, order_id: uuid.UUID) -> Order:
    order = await db.scalar(
        select(Order)
        .where(Order.id == order_id, Order.business_id == business_id)
        .options(selectinload(Order.items), selectinload(Order.status_history))
    )
    if order is None:
        raise NotFoundError("Order not found")
    return order


async def _next_order_no(db: AsyncSession, business_id: uuid.UUID) -> int:
    """Atomically increment and return the per-business order number."""
    result = await db.execute(
        update(Business)
        .where(Business.id == business_id)
        .values(next_order_no=Business.next_order_no + 1)
        .returning(Business.next_order_no)
    )
    return int(result.scalar_one()) - 1


async def _get_or_create_customer(
    db: AsyncSession, business_id: uuid.UUID, phone: str, name: str | None
) -> Customer:
    customer = await db.scalar(
        select(Customer).where(
            Customer.business_id == business_id, Customer.wa_phone == phone
        )
    )
    if customer is None:
        customer = Customer(business_id=business_id, wa_phone=phone, name=name)
        db.add(customer)
        await db.flush()
    elif name and not customer.name:
        customer.name = name
    return customer


async def create_order(db: AsyncSession, business: Business, data: OrderCreate) -> Order:
    if data.fulfillment == "delivery" and not business.offers_delivery:
        raise BadRequestError("This business does not offer delivery")
    if data.fulfillment == "pickup" and not business.offers_pickup:
        raise BadRequestError("This business does not offer pickup")

    customer = await _get_or_create_customer(
        db, business.id, data.customer_phone, data.customer_name
    )

    subtotal = Decimal("0")
    items: list[OrderItem] = []
    for line in data.items:
        product = await db.scalar(
            select(Product)
            .where(Product.id == line.product_id, Product.business_id == business.id)
            .options(selectinload(Product.option_groups).selectinload(ProductOptionGroup.items))
        )
        if product is None or product.is_archived:
            raise BadRequestError(f"Product {line.product_id} is not on this menu")
        if not product.is_available:
            raise BadRequestError(f"'{product.name}' is currently unavailable")

        # Validate the selected options against THIS product's own groups.
        item_by_id = {i.id: i for g in product.option_groups for i in g.items}
        group_of_item = {i.id: g for g in product.option_groups for i in g.items}
        for oid in line.option_item_ids:
            if oid not in item_by_id:
                raise BadRequestError(f"Invalid option selected for '{product.name}'")

        counts: dict = {}
        for oid in line.option_item_ids:
            gid = group_of_item[oid].id
            counts[gid] = counts.get(gid, 0) + 1

        for group in product.option_groups:
            n = counts.get(group.id, 0)
            floor = max(group.min_select, 1) if group.is_required else group.min_select
            if n < floor:
                raise BadRequestError(f"Please choose an option for '{group.name}'")
            if group.max_select is not None and n > group.max_select:
                raise BadRequestError(f"Too many options selected for '{group.name}'")
            if group.select_type == "single" and n > 1:
                raise BadRequestError(f"Only one option allowed for '{group.name}'")

        deltas = Decimal("0")
        options_snapshot: list[dict] = []
        for oid in line.option_item_ids:
            opt = item_by_id[oid]
            deltas += opt.price_delta
            options_snapshot.append(
                {"id": str(opt.id), "name": opt.name, "price_delta": str(opt.price_delta)}
            )

        unit_price = product.price + deltas
        line_total = unit_price * line.quantity
        subtotal += line_total
        items.append(
            OrderItem(
                business_id=business.id,
                product_id=product.id,
                name_snapshot=product.name,
                price_snapshot=product.price,
                quantity=line.quantity,
                options_json=options_snapshot,
                line_total=line_total,
            )
        )

    delivery_fee = Decimal("0")
    zone_id: uuid.UUID | None = None
    if data.fulfillment == "delivery" and data.zone_id is not None:
        zone = await db.get(DeliveryZone, data.zone_id)
        if zone is None or zone.business_id != business.id:
            raise BadRequestError("Invalid delivery zone")
        delivery_fee = zone.fee
        zone_id = zone.id

    packaging_fee = business.packaging_fee or Decimal("0")
    total = subtotal + delivery_fee + packaging_fee

    order = Order(
        business_id=business.id,
        customer_id=customer.id,
        order_no=await _next_order_no(db, business.id),
        fulfillment=data.fulfillment,
        address=data.address,
        zone_id=zone_id,
        subtotal=subtotal,
        delivery_fee=delivery_fee,
        packaging_fee=packaging_fee,
        total=total,
        payment_method=data.payment_method,
        notes=data.notes,
        status="pending",
    )
    order.items = items
    order.status_history = [
        OrderStatusHistory(business_id=business.id, status="pending", changed_by="system")
    ]
    db.add(order)

    customer.order_count += 1
    customer.last_order_at = datetime.now(timezone.utc)

    await db.commit()
    return await load_order(db, business.id, order.id)


async def update_status(
    db: AsyncSession, order: Order, new_status: str, changed_by: str | None
) -> Order:
    allowed = TRANSITIONS.get(order.status, set())
    if new_status not in allowed:
        raise BadRequestError(
            f"Cannot change status from '{order.status}' to '{new_status}'"
        )
    order.status = new_status
    db.add(
        OrderStatusHistory(
            order_id=order.id,
            business_id=order.business_id,
            status=new_status,
            changed_by=changed_by,
        )
    )
    await db.commit()
    return await load_order(db, order.business_id, order.id)
