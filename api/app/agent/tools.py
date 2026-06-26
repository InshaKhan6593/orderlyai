"""Tenant-scoped agent tools (context-mode).

Every tool reads ``business_id`` / ``customer_phone`` from ``runtime.context`` — never
from an LLM-supplied argument — and opens its own DB session. So one compiled graph
serves every tenant (Studio / worker / CLI) and the model can't cross tenants. All
writes go through ``order_service`` so pricing stays server-authoritative. Read tools
return model-friendly text; cart/flow tools return ``Command`` to update graph state.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from langchain.messages import ToolMessage  # type: ignore[import-not-found]
from langchain.tools import ToolRuntime, tool  # type: ignore[import-not-found]
from langgraph.types import Command  # type: ignore[import-not-found]
from sqlalchemy import select
from sqlalchemy.orm import selectinload

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
    If the current menu is already shown in your instructions, read it from there — only call
    this when the menu was not inlined. Always add items to the cart by their real product ids.

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


def _order_item_lines(order: Order) -> list[str]:
    """The 'name x qty (options)' lines for one order, for the get_order_status summary."""
    lines: list[str] = []
    for it in order.items:
        opts = ", ".join(
            o["name"] for o in (it.options_json or []) if isinstance(o, dict) and o.get("name")
        )
        suffix = f" ({opts})" if opts else ""
        lines.append(f"  - {it.name_snapshot} x{it.quantity}{suffix}")
    return lines


def _format_order(order: Order, cur: str) -> str:
    """One order rendered with its header and itemized lines, for the model to relay."""
    head = f"Order #{order.order_no}: {order.status} · {order.fulfillment} · {order.total} {cur}"
    return "\n".join([head, *_order_item_lines(order)])


@tool(parse_docstring=True)
async def get_order_status(order_no: int | None = None, runtime: ToolRuntime = None) -> str:  # type: ignore[assignment]
    """Look up this customer's recent orders, each with its items and quantities.

    Returns up to the five most recent orders for this WhatsApp number — each with its status,
    fulfillment type, total, and the items ordered (name and quantity). Use it for "where's my
    order / what's the status", "what did I order", or to show a past order before reordering it.

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
            .options(selectinload(Order.items))
            .limit(5)
        )
        if order_no is not None:
            stmt = stmt.where(Order.order_no == order_no)
        orders = (await s.execute(stmt)).scalars().all()
        cur = b.currency
        if not orders:
            return "No orders found for you yet."
        return "\n".join(_format_order(o, cur) for o in orders)


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


async def _saved_customer(s, business_id: uuid.UUID, phone: str) -> Customer | None:
    """The stored customer row (for prefilling saved contact details at checkout)."""
    return await s.scalar(
        select(Customer).where(
            Customer.business_id == business_id, Customer.wa_phone == phone
        )
    )


def _format_quote(cart: list, quote, cur: str) -> str:
    """Itemized, server-priced cart summary — shown by view_cart and on the confirm prompt."""
    out = ["Cart:"]
    for i, (c, pl) in enumerate(zip(cart, quote.lines), start=1):
        opt = f" ({c['options_label']})" if c["options_label"] else ""
        out.append(f"  {i}. {pl.quantity} x {pl.name}{opt} - {pl.line_total} {cur}")
    out.append(f"Subtotal: {quote.subtotal} {cur}")
    if quote.delivery_fee:
        out.append(f"Delivery: {quote.delivery_fee} {cur}")
    if quote.packaging_fee:
        out.append(f"Packaging: {quote.packaging_fee} {cur}")
    out.append(f"Total: {quote.total} {cur}")
    return "\n".join(out)


def _format_confirm(
    cart: list,
    quote,
    cur: str,
    fulfillment: str,
    address: str | None,
    name: str | None,
    email: str | None,
    alt_phone: str | None,
) -> str:
    """The full confirm summary: priced cart + fulfillment + the customer's contact details."""
    lines = [_format_quote(cart, quote, cur), ""]
    lines.append(f"Delivery to: {address}" if fulfillment == "delivery" else "Pickup")
    if name:
        lines.append(f"Name: {name}")
    if alt_phone:
        lines.append(f"Alt. phone: {alt_phone}")
    if email:
        lines.append(f"Email: {email}")
    return "\n".join(lines)


def _format_placed(
    order_no: int, total, ful: str, cur: str, name: str | None, address: str | None
) -> str:
    """The deterministic 'order placed' confirmation message sent to the customer."""
    where = (
        f"We'll deliver to: {address}"
        if ful == "delivery" and address
        else "Your order will be ready for pickup shortly."
    )
    pay = "delivery" if ful == "delivery" else "pickup"
    greeting = f"Thanks, {name}! " if name else "Thanks! "
    return (
        "Your order is confirmed!\n\n"
        f"Order #{order_no}\n"
        f"Total: {total} {cur} (cash on {pay})\n"
        f"{where}\n\n"
        f"{greeting}We'll message you here with updates."
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
    return _format_quote(cart, q, cur)


@tool
async def place_order(runtime: ToolRuntime = None) -> Command:  # type: ignore[assignment]
    """Take the order to checkout and finalize it once the customer taps Confirm.

    PREREQUISITE: delivery-or-pickup must already be set via set_fulfillment (ask the customer
    first if you offer both; for delivery also confirm the address with check_delivery_area). Do
    NOT call place_order just to discover the fulfillment — it will only bounce back asking for it.

    Call this once the cart is ready and fulfillment is set. It re-validates and re-prices the whole
    cart server-side (fulfillment, delivery area, opening hours, business minimum) and uses the
    customer's saved contact details — the name is required (loaded from their saved record /
    WhatsApp profile when known; the system asks for it deterministically if it's missing, so you
    never collect it yourself). If everything checks out but the customer has not yet TAPPED
    Confirm, it does NOT create the order — the system then shows them the priced total and their
    details with the [Confirm][Edit][Cancel] buttons. Once they tap Confirm, call this again and
    the order is created.
    """
    state = runtime.state
    cart = state.get("cart") or []
    if not cart:
        return _msg("The cart is empty - add items first.", runtime)
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

        # Contact details: prefer what was collected this session, falling back to the saved
        # customer record (the WhatsApp profile name lands there too, so a returning customer
        # rarely has to re-enter anything). Any value prefilled here is written back into state
        # so the confirm summary and the order see it. The name is required to place an order.
        name = state.get("customer_name")
        email = state.get("customer_email")
        alt_phone = state.get("customer_alt_phone")
        prefill: dict[str, object] = {}
        if not (name and email and alt_phone):
            saved = await _saved_customer(s, b.id, _phone(runtime))
            if saved is not None:
                name = name or saved.name
                email = email or saved.email
                alt_phone = alt_phone or saved.alternate_phone
            if name and not state.get("customer_name"):
                prefill["customer_name"] = name
            if email and not state.get("customer_email"):
                prefill["customer_email"] = email
            if alt_phone and not state.get("customer_alt_phone"):
                prefill["customer_alt_phone"] = alt_phone
        if not name:
            # No name on file and none captured yet → hand off to the deterministic contact
            # collector: run_turn asks for it and validates/saves the reply in code (the model
            # never sets contact values). The cart and pricing are untouched.
            return _msg(
                "The order needs a name; the system will ask the customer and record it.",
                runtime,
                pending_contact_field="name",
                **prefill,
            )

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
            return _msg(e.message, runtime, confirmed=False, step="building", **prefill)

        # Business-level minimum (distinct from per-zone minimum) — deferred guard, enforced here.
        if quote.subtotal < (b.min_order_amount or Decimal("0")):
            return _msg(
                f"The minimum order is {b.min_order_amount} {cur}; "
                f"your subtotal is {quote.subtotal} {cur}. Add a bit more?",
                runtime,
                confirmed=False,
                step="building",
                **prefill,
            )

        # Final gate: the cart is valid and priced, but the order is placed only once the
        # customer TAPS Confirm (the deterministic `confirmed` flag — never inferred from text).
        # Until then, signal run_turn to GUARANTEE the [Confirm][Edit][Cancel] buttons render
        # next to this server-priced total + contact details, so the customer always has a real
        # button to tap and can see exactly what (and to whom) they're confirming.
        if not state.get("confirmed"):
            return _msg(
                "Cart is valid and priced but NOT confirmed — do not finalize. The customer is "
                "shown this total with the Confirm / Edit / Cancel buttons automatically; wait "
                "for them to tap Confirm, then place_order will finalize it.",
                runtime,
                awaiting_confirm=True,
                confirm_summary=_format_confirm(
                    cart, quote, cur, fulfillment, address, name, email, alt_phone
                ),
                step="confirming",
                **prefill,
            )

        data = OrderCreate(
            customer_phone=_phone(runtime),
            customer_name=name,
            customer_email=email,
            customer_alt_phone=alt_phone,
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
            return _msg(e.message, runtime, confirmed=False, step="building", **prefill)
        order_no, total, ful = order.order_no, order.total, order.fulfillment

    # The order is committed. run_turn sends `order_placed_summary` to the customer verbatim and
    # ALONE (the deterministic, server-authoritative confirmation), so this tool message is for
    # the model only — tell it the customer has already been confirmed, so it does not compose a
    # second, possibly wrong, order summary of its own.
    return _msg(
        f"Order #{order_no} created and the confirmation has ALREADY been sent to the customer. "
        "Do NOT send another order summary or repeat the order number/total — a short thank-you "
        "is enough.",
        runtime,
        cart=[],
        confirmed=False,
        awaiting_confirm=False,
        confirm_summary=None,
        order_placed_summary=_format_placed(order_no, total, ful, cur, name, address),
        step="placed",
        **prefill,
    )


@tool(parse_docstring=True)
async def reorder(order_no: int | None = None, runtime: ToolRuntime = None) -> Command:  # type: ignore[assignment]
    """Repeat one of THIS customer's past orders — add its items to the cart again.

    Use this when the customer wants the "same as last time", to "reorder", "the usual", or taps
    a Reorder button. Omit `order_no` for their most recent order, or pass a specific past order
    number. Every line is re-checked and re-priced against TODAY'S menu (prices and availability
    change): anything now sold out, removed, or whose options changed is skipped and reported back
    to you so you can tell the customer plainly. The items are ADDED to whatever is already in the
    cart. Reorder does NOT set delivery/pickup — continue the normal flow afterwards (ask delivery
    or pickup, confirm a delivery address, then place_order).

    Args:
        order_no: A specific past order number to repeat. Omit for the most recent order.
    """
    async with SessionLocal() as s:
        b = await catalog.load_business_for_agent(s, _bid(runtime))
        if b is None:
            return _msg("This business isn't available.", runtime)
        stmt = (
            select(Order)
            .join(Customer, Order.customer_id == Customer.id)
            .where(Order.business_id == b.id, Customer.wa_phone == _phone(runtime))
            .order_by(Order.created_at.desc())
            .options(selectinload(Order.items))
            .limit(1)
        )
        if order_no is not None:
            stmt = stmt.where(Order.order_no == order_no)
        order = (await s.execute(stmt)).scalars().first()
        if order is None:
            which = f" #{order_no}" if order_no is not None else ""
            return _msg(
                f"I couldn't find a past order{which} to repeat. Want to see the menu?", runtime
            )

        past_no = order.order_no
        # Re-validate + re-price every line against today's menu — never reuse the frozen
        # snapshot price (golden rule: pricing is server-authoritative).
        product_ids = {it.product_id for it in order.items if it.product_id is not None}
        products = await _load_products(s, b.id, product_ids) if product_ids else {}

        new_lines: list = []
        added: list[str] = []
        skipped: list[str] = []
        for it in order.items:
            if it.product_id is None:
                skipped.append(f"{it.name_snapshot} (no longer on the menu)")
                continue
            try:
                opt_ids = [
                    uuid.UUID(o["id"])
                    for o in (it.options_json or [])
                    if isinstance(o, dict) and o.get("id")
                ]
            except (ValueError, TypeError):
                opt_ids = []
            try:
                pl = _validate_and_price_line(
                    products.get(it.product_id), it.product_id, it.quantity, opt_ids,
                    enforce_required=False,
                )
            except AppError as e:
                skipped.append(f"{it.name_snapshot} ({e.message})")
                continue
            label = ", ".join(o["name"] for o in pl.options_snapshot)
            new_lines.append(
                new_line(str(it.product_id), pl.name, it.quantity, [str(o) for o in opt_ids], label)
            )
            suffix = f" ({label})" if label else ""
            added.append(f"{it.quantity} x {pl.name}{suffix}")

    if not new_lines:
        detail = (" " + "; ".join(skipped) + ".") if skipped else ""
        return _msg(
            f"I couldn't re-add anything from order #{past_no} - those items aren't available "
            f"right now.{detail}",
            runtime,
        )

    cart = list(runtime.state.get("cart") or []) + new_lines
    msg = f"Re-added from order #{past_no}: {'; '.join(added)}. Cart now has {len(cart)} line(s)."
    if skipped:
        msg += f" Couldn't re-add: {'; '.join(skipped)}."
    return _msg(
        msg,
        runtime,
        cart=cart,
        step="building",
        selected_product_id=new_lines[-1]["product_id"],
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
        handoff_at=datetime.now(timezone.utc).isoformat(),
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
    reorder,
    request_human,
]
