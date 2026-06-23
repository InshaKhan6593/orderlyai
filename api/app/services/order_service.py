"""Order engine: server-side pricing, atomic order numbers, status transitions.

Pricing is authoritative here — the line total is always
``(product.price + Σ effective option deltas) × quantity`` computed from the DB,
never trusted from the client.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import BadRequestError, NotFoundError
from app.models.business import Business
from app.models.customer import Customer
from app.models.menu import ModifierGroup, Product, ProductModifierGroup
from app.models.order import Order, OrderItem, OrderStatusHistory
from app.models.ops import DeliveryZone
from app.schemas.order import OrderCreate

# Allowed status transitions, per fulfillment type. `ready` and `out_for_delivery`
# are the parallel stage-4 states keyed by fulfillment (see design docs 07 §3 and
# the dashboard "Preparing → [Mark ready] (pickup) or [Out for delivery]
# (delivery)" buttons): pickup goes `preparing → ready → completed`; delivery
# dispatches directly `preparing → out_for_delivery → completed`.
_COMMON: dict[str, set[str]] = {
    "pending": {"accepted", "rejected", "cancelled"},
    "accepted": {"preparing", "cancelled"},
    "completed": set(),
    "rejected": set(),
    "cancelled": set(),
}
TRANSITIONS: dict[str, dict[str, set[str]]] = {
    "pickup": {
        **_COMMON,
        "preparing": {"ready", "cancelled"},
        "ready": {"completed", "cancelled"},
    },
    "delivery": {
        **_COMMON,
        "preparing": {"out_for_delivery", "cancelled"},
        "out_for_delivery": {"completed", "cancelled"},
    },
}


async def load_order(
    db: AsyncSession,
    business_id: uuid.UUID,
    order_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> Order:
    stmt = (
        select(Order)
        .where(Order.id == order_id, Order.business_id == business_id)
        .options(selectinload(Order.items), selectinload(Order.status_history))
        # `expire_on_commit=False` keeps committed objects in the identity map;
        # repopulate so a re-read after a write returns fresh rows/collections.
        .execution_options(populate_existing=True)
    )
    if for_update:
        # Lock only the orders row; the selectinload children load separately.
        stmt = stmt.with_for_update(of=Order)
    order = await db.scalar(stmt)
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


async def _upsert_customer_id(
    db: AsyncSession, business_id: uuid.UUID, phone: str, name: str | None
) -> uuid.UUID:
    """Atomically upsert (business_id, wa_phone) and return the customer id.

    Uses PostgreSQL ``ON CONFLICT`` so concurrent first orders from the same
    phone can't violate the unique constraint. An existing name is preserved;
    a missing name is backfilled.
    """
    stmt = pg_insert(Customer).values(
        business_id=business_id, wa_phone=phone, name=name
    )
    stmt = stmt.on_conflict_do_update(
        constraint="customers_business_phone",
        set_={"name": func.coalesce(Customer.name, stmt.excluded.name)},
    ).returning(Customer.id)
    result = await db.execute(stmt)
    return result.scalar_one()


async def create_order(db: AsyncSession, business: Business, data: OrderCreate) -> Order:
    if data.fulfillment == "delivery" and not business.offers_delivery:
        raise BadRequestError("This business does not offer delivery")
    if data.fulfillment == "pickup" and not business.offers_pickup:
        raise BadRequestError("This business does not offer pickup")

    customer_id = await _upsert_customer_id(
        db, business.id, data.customer_phone, data.customer_name
    )

    # Bulk-fetch every referenced product (with its assigned modifiers) in one query.
    product_ids = {line.product_id for line in data.items}
    rows = await db.execute(
        select(Product)
        .where(Product.id.in_(product_ids), Product.business_id == business.id)
        .options(
            selectinload(Product.modifier_groups)
            .selectinload(ProductModifierGroup.group)
            .selectinload(ModifierGroup.items),
            selectinload(Product.modifier_groups).selectinload(
                ProductModifierGroup.option_prices
            ),
        )
    )
    products = {p.id: p for p in rows.scalars().all()}

    subtotal = Decimal("0")
    items: list[OrderItem] = []
    for line in data.items:
        product = products.get(line.product_id)
        if product is None or product.is_archived:
            raise BadRequestError(f"Product {line.product_id} is not on this menu")
        if not product.is_available:
            raise BadRequestError(f"'{product.name}' is currently unavailable")

        if len(set(line.option_item_ids)) != len(line.option_item_ids):
            raise BadRequestError(f"Duplicate options selected for '{product.name}'")

        # An option is valid only when it is enabled on this product assignment.
        item_by_id = {
            item.id: item
            for assignment in product.modifier_groups
            for item in assignment.items
        }
        assignment_of_item = {
            item.id: assignment
            for assignment in product.modifier_groups
            for item in assignment.items
        }
        for oid in line.option_item_ids:
            if oid not in item_by_id:
                raise BadRequestError(f"Invalid option selected for '{product.name}'")

        counts: dict = {}
        for oid in line.option_item_ids:
            assignment_id = assignment_of_item[oid].id
            counts[assignment_id] = counts.get(assignment_id, 0) + 1

        for assignment in product.modifier_groups:
            n = counts.get(assignment.id, 0)
            floor = (
                max(assignment.min_select, 1)
                if assignment.is_required
                else assignment.min_select
            )
            if n < floor:
                raise BadRequestError(
                    f"Please choose an option for '{assignment.group.display_name}'"
                )
            if assignment.max_select is not None and n > assignment.max_select:
                raise BadRequestError(
                    f"Too many options selected for '{assignment.group.display_name}'"
                )
            if assignment.group.select_type == "single" and n > 1:
                raise BadRequestError(
                    f"Only one option allowed for '{assignment.group.display_name}'"
                )

        deltas = Decimal("0")
        options_snapshot: list[dict] = []
        for oid in line.option_item_ids:
            opt = item_by_id[oid]
            price_delta = assignment_of_item[oid].price_delta_for(oid)
            deltas += price_delta
            options_snapshot.append(
                {
                    "id": str(opt.id),
                    "name": opt.name,
                    "description": opt.description,
                    "price_delta": str(price_delta),
                }
            )

        unit_price = product.price + deltas
        if unit_price < 0:
            # Negative modifier deltas (discounts) are allowed, but they can
            # never drive a line price below zero.
            raise BadRequestError(f"Invalid option pricing for '{product.name}'")
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
        if not zone.is_active:
            raise BadRequestError(f"Delivery zone '{zone.name}' is not active")
        if subtotal < zone.min_order:
            raise BadRequestError(
                f"Minimum order for '{zone.name}' is {zone.min_order}"
            )
        delivery_fee = zone.fee
        zone_id = zone.id

    packaging_fee = business.packaging_fee or Decimal("0")
    total = subtotal + delivery_fee + packaging_fee

    order = Order(
        business_id=business.id,
        customer_id=customer_id,
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

    # Atomic counter bump — avoids the lost-update race of read-modify-write.
    # Scoped by business_id per the tenant-isolation rule (defense in depth).
    await db.execute(
        update(Customer)
        .where(Customer.id == customer_id, Customer.business_id == business.id)
        .values(
            order_count=Customer.order_count + 1,
            last_order_at=datetime.now(timezone.utc),
        )
    )

    await db.commit()
    return await load_order(db, business.id, order.id)


async def update_status(
    db: AsyncSession, order: Order, new_status: str, changed_by: str | None
) -> Order:
    allowed = TRANSITIONS.get(order.fulfillment, {}).get(order.status, set())
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
