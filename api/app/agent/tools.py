"""Tenant-scoped agent tools (context-mode).

Every tool reads ``business_id`` / ``customer_phone`` from ``runtime.context`` — never
from an LLM-supplied argument — and opens its own DB session. So one compiled graph
serves every tenant (Studio / worker / CLI) and the model can't cross tenants. All
writes go through ``order_service`` so pricing stays server-authoritative. Read tools
return model-friendly text; cart/flow tools return ``Command`` to update graph state.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from langchain.messages import ToolMessage  # type: ignore[import-not-found]
from langchain.tools import ToolRuntime, tool  # type: ignore[import-not-found]
from langgraph.types import Command  # type: ignore[import-not-found]
from sqlalchemy import select

from app.agent import catalog
from app.agent.context import ctx_dict
from app.agent.state import new_line
from app.core.db import SessionLocal
from app.core.errors import AppError
from app.models.customer import Customer
from app.models.order import Order
from app.schemas.order import OrderCreate, OrderLineIn
from app.services import order_service
from app.services.order_service import (
    CartLineInput,
    _load_products,
    _validate_and_price_line,
)

# Tools that only make sense once the cart has something in it (gated in middleware).
CART_ONLY_TOOLS = {"update_cart_quantity", "remove_from_cart", "view_cart", "place_order"}


def _bid(runtime: ToolRuntime) -> uuid.UUID:
    return uuid.UUID(ctx_dict(runtime)["business_id"])


def _phone(runtime: ToolRuntime) -> str:
    return ctx_dict(runtime)["customer_phone"]


def _uuids(values: list[str]) -> list[uuid.UUID]:
    return [uuid.UUID(v) for v in values]


def _msg(text: str, runtime: ToolRuntime, **state: object) -> Command:
    return Command(
        update={
            **state,
            "messages": [ToolMessage(content=text, tool_call_id=runtime.tool_call_id)],
        }
    )


# --------------------------------------------------------------------------- #
# Read tools
# --------------------------------------------------------------------------- #
@tool(parse_docstring=True)
async def get_menu(category: str | None = None, runtime: ToolRuntime = None) -> str:  # type: ignore[assignment]
    """List the menu — the whole menu, or just one category. Items show price, owner tags, id.

    The business's categories are named in your instructions. Map the customer's request
    (e.g. "burgers", "fast food", "something sweet") to the closest of THOSE categories and
    pass it as `category`. Omit `category` for the full menu, or to answer cross-category
    questions ("what's vegetarian / cheap"); read the owner tags in brackets to filter. If the
    category name doesn't exist, the reply lists the real categories so you can map or ask.
    Always call this before add_to_cart so you use real product ids.

    Args:
        category: A category name to show only that section (case-insensitive). Omit for the
            full menu.
    """
    async with SessionLocal() as s:
        b = await catalog.load_business_for_agent(s, _bid(runtime))
        if b is None:
            return "This business isn't available."
        return await catalog.menu_overview(s, b, category=category)


@tool(parse_docstring=True)
async def get_item_details(product_id: str, runtime: ToolRuntime = None) -> str:  # type: ignore[assignment]
    """Get full detail for ONE menu item before ordering it.

    Returns the description, price, owner tags, image, and every option group (required
    choices and optional add-ons) with each option's price delta and option_id. Call this
    when the customer asks about a specific dish, or before adding an item that has options,
    so you can pass the right option ids to add_to_cart.

    Args:
        product_id: The item's id, exactly as shown by get_menu (a UUID).
    """
    async with SessionLocal() as s:
        b = await catalog.load_business_for_agent(s, _bid(runtime))
        if b is None:
            return "This business isn't available."
        return await catalog.item_detail(s, b, product_id)


@tool
async def check_hours(runtime: ToolRuntime = None) -> str:  # type: ignore[assignment]
    """Report whether the business is open right now and list the weekly opening hours.

    Call this when the customer asks if you're open, when you'll be ready, or before
    promising fulfilment — orders cannot be placed while the business is closed.
    """
    async with SessionLocal() as s:
        b = await catalog.load_business_for_agent(s, _bid(runtime))
        if b is None:
            return "This business isn't available."
        hours = list(b.hours)
        state = "OPEN now" if catalog.is_open_now(hours, b.timezone) else "CLOSED right now"
        return f"{state}. Hours - {catalog.format_hours(hours)}."


@tool(parse_docstring=True)
async def get_order_status(order_no: int | None = None, runtime: ToolRuntime = None) -> str:  # type: ignore[assignment]
    """Look up the status of this customer's recent orders.

    Returns up to the five most recent orders for this WhatsApp number with their status,
    fulfillment type, and total. Use it for "where's my order / what's the status".

    Args:
        order_no: A specific order number to look up. Omit to list recent orders.
    """
    async with SessionLocal() as s:
        b = await catalog.load_business_for_agent(s, _bid(runtime))
        if b is None:
            return "This business isn't available."
        stmt = (
            select(Order)
            .join(Customer, Order.customer_id == Customer.id)
            .where(Order.business_id == b.id, Customer.wa_phone == _phone(runtime))
            .order_by(Order.created_at.desc())
            .limit(5)
        )
        if order_no is not None:
            stmt = stmt.where(Order.order_no == order_no)
        orders = (await s.execute(stmt)).scalars().all()
        cur = b.currency
    if not orders:
        return "No orders found for you yet."
    return "\n".join(
        f"Order #{o.order_no}: {o.status} · {o.fulfillment} · {o.total} {cur}" for o in orders
    )


# --------------------------------------------------------------------------- #
# Cart / flow tools
# --------------------------------------------------------------------------- #
@tool(parse_docstring=True)
async def add_to_cart(
    product_id: str,
    quantity: int,
    option_item_ids: list[str] | None = None,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> Command:
    """Add one menu item, with any chosen options, to the cart.

    Resolve the item with get_menu / get_item_details first so the ids are real. Required
    option groups don't have to be set here, but they must be chosen before place_order.
    The line price is computed server-side, never by you.

    Args:
        product_id: The item's id from get_menu (a UUID).
        quantity: How many to add (1-999).
        option_item_ids: Chosen option ids (sizes/add-ons) from get_item_details, if any.
    """
    option_item_ids = option_item_ids or []
    if quantity < 1 or quantity > 999:
        return _msg("Quantity must be between 1 and 999.", runtime)
    try:
        pid = uuid.UUID(product_id)
        opt_ids = _uuids(option_item_ids)
    except (ValueError, AttributeError):
        return _msg("That item/option id isn't valid - call get_menu first.", runtime)

    async with SessionLocal() as s:
        products = await _load_products(s, _bid(runtime), {pid})
        try:
            pl = _validate_and_price_line(
                products.get(pid), pid, quantity, opt_ids, enforce_required=False
            )
        except AppError as e:
            return _msg(e.message, runtime)

    label = ", ".join(o["name"] for o in pl.options_snapshot)
    line = new_line(str(pid), pl.name, quantity, [str(o) for o in opt_ids], label)
    cart = list(runtime.state.get("cart") or []) + [line]
    suffix = f" ({label})" if label else ""
    return _msg(
        f"Added {quantity} x {pl.name}{suffix}. Cart now has {len(cart)} line(s).",
        runtime,
        cart=cart,
        step="building",
        selected_product_id=str(pid),
    )


@tool(parse_docstring=True)
async def update_cart_quantity(
    line_index: int, quantity: int, runtime: ToolRuntime = None  # type: ignore[assignment]
) -> Command:
    """Change the quantity of one cart line.

    Args:
        line_index: Which cart line to change, 1-based (line 1 is the first item). See view_cart.
        quantity: The new quantity (1-999). Use 0 to remove the line entirely.
    """
    cart = list(runtime.state.get("cart") or [])
    if line_index < 1 or line_index > len(cart):
        return _msg(f"There's no line {line_index}. The cart has {len(cart)} line(s).", runtime)
    if quantity <= 0:
        removed = cart.pop(line_index - 1)
        return _msg(f"Removed {removed['name']}.", runtime, cart=cart)
    if quantity > 999:
        return _msg("Quantity must be 999 or less.", runtime)
    cart[line_index - 1] = {**cart[line_index - 1], "quantity": quantity}
    return _msg(f"Updated line {line_index} to {quantity}.", runtime, cart=cart)


@tool(parse_docstring=True)
async def remove_from_cart(
    line_index: int, runtime: ToolRuntime = None  # type: ignore[assignment]
) -> Command:
    """Remove one line from the cart.

    Args:
        line_index: Which cart line to remove, 1-based (see view_cart for the numbering).
    """
    cart = list(runtime.state.get("cart") or [])
    if line_index < 1 or line_index > len(cart):
        return _msg(f"There's no line {line_index}.", runtime)
    removed = cart.pop(line_index - 1)
    return _msg(f"Removed {removed['name']}.", runtime, cart=cart)


@tool(parse_docstring=True)
async def set_fulfillment(
    fulfillment: str, address: str | None = None, runtime: ToolRuntime = None  # type: ignore[assignment]
) -> Command:
    """Set how the order is fulfilled: delivery or pickup.

    For delivery, also collect the customer's address here and then call check_delivery_area
    to confirm it's in a serviceable zone. Rejected if the business doesn't offer the chosen
    method.

    Args:
        fulfillment: Either "delivery" or "pickup".
        address: The delivery address. Required for delivery; ignored for pickup.
    """
    fulfillment = (fulfillment or "").lower().strip()
    if fulfillment not in ("delivery", "pickup"):
        return _msg("Choose either 'delivery' or 'pickup'.", runtime)
    async with SessionLocal() as s:
        b = await catalog.load_business_for_agent(s, _bid(runtime))
    if b is None:
        return _msg("This business isn't available.", runtime)
    if fulfillment == "delivery" and not b.offers_delivery:
        return _msg("Sorry, we don't offer delivery - only pickup.", runtime)
    if fulfillment == "pickup" and not b.offers_pickup:
        return _msg("Sorry, we don't offer pickup - only delivery.", runtime)
    update: dict[str, object] = {"fulfillment": fulfillment}
    if address is not None:
        update["address"] = address
    return _msg(f"Set fulfillment to {fulfillment}.", runtime, **update)


@tool(parse_docstring=True)
async def check_delivery_area(
    area_or_address: str, runtime: ToolRuntime = None  # type: ignore[assignment]
) -> Command:
    """Check whether an address/area is within a delivery zone, and record the matched zone.

    Call this for every delivery order before place_order: it sets the delivery fee and the
    zone's minimum order. If no zone matches, offer pickup instead.

    Args:
        area_or_address: The customer's area name or full delivery address, in free text.
    """
    async with SessionLocal() as s:
        b = await catalog.load_business_for_agent(s, _bid(runtime))
        if b is None:
            return _msg("This business isn't available.", runtime)
        if not b.offers_delivery:
            return _msg("We don't offer delivery.", runtime)
        zones = await catalog.delivery_zones(s, b)
        cur = b.currency
    if not zones:
        return _msg("No delivery zones are set up - delivery isn't available.", runtime)
    zone = catalog.match_zone(zones, area_or_address)
    if zone is None:
        names = ", ".join(z.name for z in zones)
        return _msg(
            f"That area isn't in our delivery zones ({names}). Offer pickup instead.",
            runtime,
            zone_serviceable=False,
            address=area_or_address,
        )
    eta = f", ETA ~{zone.eta_minutes} min" if zone.eta_minutes else ""
    return _msg(
        f"'{zone.name}' is serviceable: delivery fee {zone.fee} {cur}, "
        f"minimum {zone.min_order} {cur}{eta}.",
        runtime,
        zone_id=str(zone.id),
        zone_serviceable=True,
        address=area_or_address,
    )


@tool
async def view_cart(runtime: ToolRuntime = None) -> str:  # type: ignore[assignment]
    """Show an itemized, server-priced summary of the current cart with the running total.

    Always call this to show the customer their order and total BEFORE asking them to
    confirm. Quantities, option prices, delivery, and packaging fees are all computed by the
    server here — show these numbers, never your own.
    """
    cart = runtime.state.get("cart") or []
    if not cart:
        return "The cart is empty."
    fulfillment = runtime.state.get("fulfillment")
    zone_id = runtime.state.get("zone_id")
    lines = [
        CartLineInput(
            product_id=uuid.UUID(c["product_id"]),
            quantity=c["quantity"],
            option_item_ids=_uuids(c["option_item_ids"]),
        )
        for c in cart
    ]
    async with SessionLocal() as s:
        b = await catalog.load_business_for_agent(s, _bid(runtime))
        if b is None:
            return "This business isn't available."
        cur = b.currency
        try:
            q = await order_service.quote_cart(
                s,
                b,
                lines=lines,
                fulfillment=fulfillment,
                zone_id=uuid.UUID(zone_id) if zone_id else None,
                enforce_required=False,
            )
        except AppError as e:
            return f"Can't price the cart yet: {e.message}"
    out = ["Cart:"]
    for i, (c, pl) in enumerate(zip(cart, q.lines), start=1):
        opt = f" ({c['options_label']})" if c["options_label"] else ""
        out.append(f"  {i}. {pl.quantity} x {pl.name}{opt} - {pl.line_total} {cur}")
    out.append(f"Subtotal: {q.subtotal} {cur}")
    if q.delivery_fee:
        out.append(f"Delivery: {q.delivery_fee} {cur}")
    if q.packaging_fee:
        out.append(f"Packaging: {q.packaging_fee} {cur}")
    out.append(f"Total: {q.total} {cur}")
    return "\n".join(out)


@tool
async def place_order(runtime: ToolRuntime = None) -> Command:  # type: ignore[assignment]
    """Place the order — the final step. Only call this after the customer has confirmed.

    REFUSES unless the cart was priced with view_cart and the customer tapped Confirm,
    fulfillment is set, and (for delivery) a serviceable address exists. Re-validates the
    whole cart server-side, enforces the business minimum and opening hours, and computes
    the authoritative total before creating the order.
    """
    state = runtime.state
    cart = state.get("cart") or []
    if not cart:
        return _msg("The cart is empty - add items first.", runtime)
    if not state.get("confirmed"):
        return _msg(
            "I can't place the order until you've reviewed the total and tapped Confirm.",
            runtime,
        )
    fulfillment = state.get("fulfillment")
    if fulfillment not in ("delivery", "pickup"):
        return _msg("Do you want delivery or pickup?", runtime)
    address = state.get("address")
    zone_id = state.get("zone_id")
    if fulfillment == "delivery":
        if not address:
            return _msg("I need a delivery address first.", runtime)
        if not state.get("zone_serviceable"):
            return _msg("I still need to confirm your address is in our delivery area.", runtime)

    lines = [
        CartLineInput(
            product_id=uuid.UUID(c["product_id"]),
            quantity=c["quantity"],
            option_item_ids=_uuids(c["option_item_ids"]),
        )
        for c in cart
    ]
    async with SessionLocal() as s:
        b = await catalog.load_business_for_agent(s, _bid(runtime))
        if b is None:
            return _msg("This business isn't available.", runtime)
        cur = b.currency
        if not b.accepting_orders:
            return _msg("We're not accepting orders right now.", runtime)
        if not catalog.is_open_now(list(b.hours), b.timezone):
            return _msg("We're closed right now, so I can't place the order.", runtime)
        try:
            quote = await order_service.quote_cart(
                s,
                b,
                lines=lines,
                fulfillment=fulfillment,
                zone_id=uuid.UUID(zone_id) if zone_id else None,
                enforce_required=True,
            )
        except AppError as e:
            return _msg(e.message, runtime, confirmed=False, step="building")

        # Business-level minimum (distinct from per-zone minimum) — deferred guard, enforced here.
        if quote.subtotal < (b.min_order_amount or Decimal("0")):
            return _msg(
                f"The minimum order is {b.min_order_amount} {cur}; "
                f"your subtotal is {quote.subtotal} {cur}. Add a bit more?",
                runtime,
                confirmed=False,
                step="building",
            )

        data = OrderCreate(
            customer_phone=_phone(runtime),
            customer_name=None,
            fulfillment=fulfillment,
            address=address,
            zone_id=uuid.UUID(zone_id) if zone_id else None,
            payment_method="cod",
            notes=state.get("notes"),
            items=[
                OrderLineIn(
                    product_id=uuid.UUID(c["product_id"]),
                    quantity=c["quantity"],
                    option_item_ids=_uuids(c["option_item_ids"]),
                )
                for c in cart
            ],
        )
        try:
            order = await order_service.create_order(s, b, data)
        except AppError as e:
            return _msg(e.message, runtime, confirmed=False, step="building")
        order_no, total, ful = order.order_no, order.total, order.fulfillment

    return _msg(
        f"Order #{order_no} placed · {ful} · total {total} {cur} "
        f"(cash on {'delivery' if ful == 'delivery' else 'pickup'}).",
        runtime,
        cart=[],
        confirmed=False,
        step="placed",
    )


@tool(parse_docstring=True)
async def request_human(reason: str, runtime: ToolRuntime = None) -> Command:  # type: ignore[assignment]
    """Hand the conversation to a human and stop auto-replying.

    Use for anything you can't do yourself: refunds, complaints, anger, or an explicit
    request to talk to a person. After this the agent goes silent for the thread.

    Args:
        reason: A short note on why you're escalating, for the team that picks it up.
    """
    return _msg(
        "Okay - I've let a team member know and they'll follow up with you here.",
        runtime,
        step="handed_off",
        handoff_reason=reason,
    )


TOOLS = [
    get_menu,
    get_item_details,
    check_hours,
    get_order_status,
    add_to_cart,
    update_cart_quantity,
    remove_from_cart,
    set_fulfillment,
    check_delivery_area,
    view_cart,
    place_order,
    request_human,
]
