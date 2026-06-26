"""Order engine: server-side pricing, atomic order numbers, status transitions.

Pricing is authoritative here — the line total is always
``(product.price + Σ effective option deltas) × quantity`` computed from the DB,
never trusted from the client.

Both the REST order endpoint and the WhatsApp agent go through this module:
- ``create_order``  writes a real order (full validation, enforce_required=True).
- ``quote_cart``    is the read-only preview the agent's ``view_cart`` tool uses
  (same math, nothing written). They share ``_validate_and_price_line`` /
  ``_resolve_fees`` so there is exactly one pricing implementation.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
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


# --------------------------------------------------------------------------- #
# Shared pricing primitives (the single source of pricing truth)
# --------------------------------------------------------------------------- #
@dataclass
class PricedLine:
    """One validated, server-priced cart line. Maps 1:1 to an ``OrderItem``."""

    product_id: uuid.UUID
    name: str
    price_snapshot: Decimal
    quantity: int
    options_snapshot: list[dict]
    unit_price: Decimal
    line_total: Decimal


@dataclass
class Quote:
    """Read-only price preview for a cart (no order written)."""

    lines: list[PricedLine] = field(default_factory=list)
    subtotal: Decimal = Decimal("0")
    delivery_fee: Decimal = Decimal("0")
    packaging_fee: Decimal = Decimal("0")
    total: Decimal = Decimal("0")
    zone_id: uuid.UUID | None = None


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
        .options(
            selectinload(Order.customer),
            selectinload(Order.zone),
            selectinload(Order.items),
            selectinload(Order.status_history),
        )
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


async def _load_products(
    db: AsyncSession, business_id: uuid.UUID, product_ids: set[uuid.UUID]
) -> dict[uuid.UUID, Product]:
    """Bulk-fetch referenced products (with assigned modifiers + option prices)."""
    rows = await db.execute(
        select(Product)
        .where(Product.id.in_(product_ids), Product.business_id == business_id)
        .options(
            selectinload(Product.modifier_groups)
            .selectinload(ProductModifierGroup.group)
            .selectinload(ModifierGroup.items),
            selectinload(Product.modifier_groups).selectinload(
                ProductModifierGroup.option_prices
            ),
        )
    )
    return {p.id: p for p in rows.scalars().all()}


def _validate_and_price_line(
    product: Product | None,
    product_id: uuid.UUID,
    quantity: int,
    option_item_ids: list[uuid.UUID],
    *,
    enforce_required: bool = True,
) -> PricedLine:
    """Validate one line against the menu and compute its authoritative price.

    Raises ``BadRequestError`` on any invalid selection. When ``enforce_required``
    is False (cart preview mid-build), required/min-select rules are skipped so a
    half-built line can still be priced — the full check runs again at order time.
    """
    if product is None or product.is_archived:
        raise BadRequestError(f"Product {product_id} is not on this menu")
    if not product.is_available:
        raise BadRequestError(f"'{product.name}' is currently unavailable")

    if len(set(option_item_ids)) != len(option_item_ids):
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
    for oid in option_item_ids:
        if oid not in item_by_id:
            raise BadRequestError(f"Invalid option selected for '{product.name}'")

    counts: dict = {}
    for oid in option_item_ids:
        assignment_id = assignment_of_item[oid].id
        counts[assignment_id] = counts.get(assignment_id, 0) + 1

    for assignment in product.modifier_groups:
        n = counts.get(assignment.id, 0)
        if enforce_required:
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
    for oid in option_item_ids:
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

    return PricedLine(
        product_id=product.id,
        name=product.name,
        price_snapshot=product.price,
        quantity=quantity,
        options_snapshot=options_snapshot,
        unit_price=unit_price,
        line_total=unit_price * quantity,
    )


async def _resolve_fees(
    db: AsyncSession,
    business: Business,
    fulfillment: str,
    zone_id: uuid.UUID | None,
    subtotal: Decimal,
) -> tuple[Decimal, uuid.UUID | None, Decimal]:
    """Validate the delivery zone and return (delivery_fee, zone_id, packaging_fee)."""
    delivery_fee = Decimal("0")
    resolved_zone: uuid.UUID | None = None
    if fulfillment == "delivery" and zone_id is not None:
        zone = await db.get(DeliveryZone, zone_id)
        if zone is None or zone.business_id != business.id:
            raise BadRequestError("Invalid delivery zone")
        if not zone.is_active:
            raise BadRequestError(f"Delivery zone '{zone.name}' is not active")
        if subtotal < zone.min_order:
            raise BadRequestError(f"Minimum order for '{zone.name}' is {zone.min_order}")
        delivery_fee = zone.fee
        resolved_zone = zone.id

    packaging_fee = business.packaging_fee or Decimal("0")
    return delivery_fee, resolved_zone, packaging_fee


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
    db: AsyncSession,
    business_id: uuid.UUID,
    phone: str,
    name: str | None,
    *,
    email: str | None = None,
    alternate_phone: str | None = None,
    default_address: str | None = None,
) -> uuid.UUID:
    """Atomically upsert (business_id, wa_phone) and return the customer id.

    Uses PostgreSQL ``ON CONFLICT`` so concurrent first orders from the same phone can't
    violate the unique constraint. Contact details follow "latest provided wins, else keep":
    a value supplied now overwrites the stored one (so a customer can correct their name,
    email, phone, or default address), while fields left ``None`` preserve what's on file.
    """
    stmt = pg_insert(Customer).values(
        business_id=business_id,
        wa_phone=phone,
        name=name,
        email=email,
        alternate_phone=alternate_phone,
        default_address=default_address,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="customers_business_phone",
        set_={
            "name": func.coalesce(stmt.excluded.name, Customer.name),
            "email": func.coalesce(stmt.excluded.email, Customer.email),
            "alternate_phone": func.coalesce(
                stmt.excluded.alternate_phone, Customer.alternate_phone
            ),
            "default_address": func.coalesce(
                stmt.excluded.default_address, Customer.default_address
            ),
        },
    ).returning(Customer.id)
    result = await db.execute(stmt)
    return result.scalar_one()


@dataclass
class CartLineInput:
    """Normalized cart line accepted by ``quote_cart`` (agent-friendly)."""

    product_id: uuid.UUID
    quantity: int
    option_item_ids: list[uuid.UUID] = field(default_factory=list)


async def quote_cart(
    db: AsyncSession,
    business: Business,
    *,
    lines: list[CartLineInput],
    fulfillment: str | None = None,
    zone_id: uuid.UUID | None = None,
    enforce_required: bool = False,
) -> Quote:
    """Price a cart **without writing anything** — the agent's preview path.

    Mirrors ``create_order`` validation/pricing exactly (shared helpers), but
    raises nothing to the DB. Fees are included only when ``fulfillment`` is set.
    """
    if not lines:
        return Quote()

    products = await _load_products(db, business.id, {ln.product_id for ln in lines})
    priced: list[PricedLine] = []
    subtotal = Decimal("0")
    for ln in lines:
        pl = _validate_and_price_line(
            products.get(ln.product_id),
            ln.product_id,
            ln.quantity,
            ln.option_item_ids,
            enforce_required=enforce_required,
        )
        priced.append(pl)
        subtotal += pl.line_total

    delivery_fee = Decimal("0")
    packaging_fee = Decimal("0")
    resolved_zone: uuid.UUID | None = None
    if fulfillment is not None:
        delivery_fee, resolved_zone, packaging_fee = await _resolve_fees(
            db, business, fulfillment, zone_id, subtotal
        )

    return Quote(
        lines=priced,
        subtotal=subtotal,
        delivery_fee=delivery_fee,
        packaging_fee=packaging_fee,
        total=subtotal + delivery_fee + packaging_fee,
        zone_id=resolved_zone,
    )


async def create_order(db: AsyncSession, business: Business, data: OrderCreate) -> Order:
    if data.fulfillment == "delivery" and not business.offers_delivery:
        raise BadRequestError("This business does not offer delivery")
    if data.fulfillment == "pickup" and not business.offers_pickup:
        raise BadRequestError("This business does not offer pickup")

    customer_id = await _upsert_customer_id(
        db,
        business.id,
        data.customer_phone,
        data.customer_name,
        email=data.customer_email,
        alternate_phone=data.customer_alt_phone,
        # Save a delivery address as the customer's default so it prefills next time.
        default_address=data.address if data.fulfillment == "delivery" else None,
    )

    products = await _load_products(
        db, business.id, {line.product_id for line in data.items}
    )

    subtotal = Decimal("0")
    items: list[OrderItem] = []
    for line in data.items:
        pl = _validate_and_price_line(
            products.get(line.product_id),
            line.product_id,
            line.quantity,
            line.option_item_ids,
            enforce_required=True,
        )
        subtotal += pl.line_total
        items.append(
            OrderItem(
                business_id=business.id,
                product_id=pl.product_id,
                name_snapshot=pl.name,
                price_snapshot=pl.price_snapshot,
                quantity=pl.quantity,
                options_json=pl.options_snapshot,
                line_total=pl.line_total,
            )
        )

    delivery_fee, zone_id, packaging_fee = await _resolve_fees(
        db, business, data.fulfillment, data.zone_id, subtotal
    )
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
