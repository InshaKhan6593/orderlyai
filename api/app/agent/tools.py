"""Tenant-scoped agent tools (context-mode).

Every tool reads ``business_id`` / ``customer_phone`` from ``runtime.context`` — never
from an LLM-supplied argument — and opens its own DB session. So one compiled graph
serves every tenant (Studio / worker / CLI) and the model can't cross tenants. All
writes go through ``order_service`` so pricing stays server-authoritative. Read tools
return model-friendly text; cart/flow tools return ``Command`` to update graph state.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated

from langchain.messages import ToolMessage  # type: ignore[import-not-found]
from langchain.tools import ToolRuntime, tool  # type: ignore[import-not-found]
from langgraph.types import Command  # type: ignore[import-not-found]
from pydantic import BeforeValidator
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.agent import catalog
from app.agent.context import ctx_dict
from app.agent.schemas import ROW_ZONE_PREFIX
from app.agent.state import new_line
from app.core.db import SessionLocal
from app.core.errors import AppError
from app.models.customer import Customer
from app.models.order import Order
from app.schemas.customer import ContactDetails
from app.schemas.order import OrderCreate, OrderLineIn
from app.services import order_service
from app.services.order_service import (
    CartLineInput,
    _load_products,
    _validate_and_price_line,
)

# Tools that only make sense once the cart has something in it (gated in middleware).
CART_ONLY_TOOLS = {"update_cart_quantity", "view_cart", "place_order"}


def _bid(runtime: ToolRuntime) -> uuid.UUID:
    return uuid.UUID(ctx_dict(runtime)["business_id"])


def _phone(runtime: ToolRuntime) -> str:
    return ctx_dict(runtime)["customer_phone"]


def _uuids(values: list[str]) -> list[uuid.UUID]:
    return [uuid.UUID(v) for v in values]


def _coerce_id_list(value: object) -> object:
    """Normalize a model-supplied id list before validation (belt-and-suspenders).

    Weaker models sometimes send a list-typed tool argument as a *string* instead of a real
    JSON array — e.g. '["a","b"]' (the whole array quoted), 'a,b' (comma-joined), or a single
    bare id 'a'. The strict ``list[str]`` schema would reject those, the model would retry the
    identical bad call (temperature 0), and the turn could loop. We salvage the recoverable
    shapes here so the call succeeds; anything still invalid is caught by the UUID parse in the
    tool body, which returns a friendly "call get_menu first" message rather than looping.
    A real list (the correct shape) and ``None`` pass straight through untouched.
    """
    if value is None or isinstance(value, list):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return []
        if s.startswith("["):  # a stringified JSON array → parse it back to a list
            try:
                parsed = json.loads(s)
            except ValueError:
                parsed = None
            if isinstance(parsed, list):
                return parsed
        # a single bare id, or a comma-joined string of ids
        return [part.strip() for part in s.split(",") if part.strip()]
    return value


# A list-of-id-strings argument that tolerates the common ways a model mis-encodes a list
# (see ``_coerce_id_list``). Used for model-facing id arguments only.
IdList = Annotated[list[str] | None, BeforeValidator(_coerce_id_list)]


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

    Call shape:
        get_menu(category="Burgers")   # just one section
        get_menu()                     # the whole menu

    Args:
        category: A category name to show only that section, a string (case-insensitive),
            for example "Burgers". Omit it for the full menu.
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

    Call shape:
        get_item_details(product_id="453aa17e-9664-4dfd-a466-00d827638469")

    Args:
        product_id: The item's id, a UUID string exactly as shown by get_menu, for example
            "453aa17e-9664-4dfd-a466-00d827638469".
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

    Call shape: check_hours()  — takes no arguments.
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
    head = f"*Order {order.order_code}*: {order.status} · {order.fulfillment} · {order.total} {cur}"
    return "\n".join([head, *_order_item_lines(order)])


@tool(parse_docstring=True)
async def get_order_status(order_code: str | None = None, runtime: ToolRuntime = None) -> str:  # type: ignore[assignment]
    """Look up this customer's recent orders, each with its items and quantities.

    Returns up to the five most recent orders for this WhatsApp number — each with its order code,
    status, fulfillment type, total, and the items ordered (name and quantity). Use it for "where's
    my order / what's the status", "what did I order", or to show a past order before reordering it.

    Call shape:
        get_order_status()                     # list this customer's recent orders
        get_order_status(order_code="K7Q2X9")  # one specific order

    Args:
        order_code: A specific order code to look up, a short string like "K7Q2X9". Omit it to
            list the recent orders.
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
        if order_code is not None:
            stmt = stmt.where(Order.order_code == order_code)
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
    option_item_ids: IdList = None,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> Command:
    """Add one menu item, with any chosen options, to the cart.

    Resolve the item with get_menu / get_item_details first so the ids are real. Required
    option groups don't have to be set here, but they must be chosen before place_order.
    The line price is computed server-side, never by you.

    Call shape:
        # item with chosen options (option_item_ids is a real JSON array of id strings):
        add_to_cart(product_id="453aa17e-9664-4dfd-a466-00d827638469", quantity=1,
                    option_item_ids=["692c124c-c478-4a75-bae4-d01c59c65428"])
        # plain item with no options (omit option_item_ids entirely):
        add_to_cart(product_id="453aa17e-9664-4dfd-a466-00d827638469", quantity=2)

    Args:
        product_id: The item's id from get_menu, a UUID string, for example
            "453aa17e-9664-4dfd-a466-00d827638469".
        quantity: How many to add, an integer from 1 to 999 (send 2, not "2").
        option_item_ids: The chosen option ids (sizes/add-ons) from get_item_details. Send a
            JSON ARRAY of id strings, e.g. ["692c124c-c478-4a75-bae4-d01c59c65428"] (two ids
            would be ["id-a", "id-b"]). Do NOT send the array as a quoted string such as
            "[\"692c...\"]" and do NOT send a comma-joined string like "id-a,id-b". Omit this
            argument, or send [], when the item has no chosen options.
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
    """Change the quantity of one cart line - or REMOVE it by setting quantity to 0.

    This is the only cart-edit tool: to take an item out of the cart ("remove the fries"),
    call it with quantity 0.

    Call shape:
        update_cart_quantity(line_index=1, quantity=3)   # set the first line to 3
        update_cart_quantity(line_index=2, quantity=0)   # remove the second line

    Args:
        line_index: Which cart line to change, a 1-based integer (line 1 is the first item).
            See view_cart for the line numbers.
        quantity: The new quantity, an integer from 1 to 999. Use 0 to remove the line entirely.
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


# A WhatsApp list holds 10 rows; with more active zones than this the customer types their area
# (free text) and we match it, instead of an unsendable list.
_ZONE_LIST_MAX = 10


def _zone_desc(z, cur: str) -> str:
    """One delivery-zone row's description: the fee, ETA, and any per-zone minimum (<= 72 chars)."""
    parts = [f"Delivery {z.fee} {cur}" if z.fee and z.fee > 0 else "Free delivery"]
    if z.eta_minutes:
        parts.append(f"~{z.eta_minutes} min")
    if z.min_order and z.min_order > 0:
        parts.append(f"min {z.min_order} {cur}")
    return " · ".join(parts)


def _ask_zone(runtime, b, zones, cur, carry, *, out_of_area: str | None = None) -> Command:
    """Deterministically ask the customer for their delivery AREA (code-only, never a model tool).

    With a list-sized set of zones the customer TAPS their area — an exact pick, no address-text
    guessing; with more zones than a WhatsApp list can hold they TYPE it and place_order matches it.
    ``out_of_area`` names a typed area we couldn't match, so the re-ask leads with a plain
    "we don't deliver there". This is asked EARLY (before the cart is required) so an out-of-area
    customer is told up front, and pickup is offered when the business supports it.
    """
    pickup_hint = ' Or reply "pickup" to collect instead.' if b.offers_pickup else ""
    prefix = f"Sorry, we don't deliver to {out_of_area}. " if out_of_area else ""
    if len(zones) <= _ZONE_LIST_MAX:
        prompt = f"{prefix}Which area should we deliver to? Tap your area below.{pickup_hint}"
        choices: list[dict] | None = [
            {"id": f"{ROW_ZONE_PREFIX}{z.id}", "title": z.name, "description": _zone_desc(z, cur)}
            for z in zones
        ]
    else:
        prompt = f"{prefix}What area or neighbourhood should we deliver to?{pickup_hint}"
        choices = None
    return _msg(
        "Need the customer's delivery area; the system will ask for it and check serviceability.",
        runtime,
        pending_checkout_field="zone",
        zone_choices=choices,
        zone_prompt=prompt,
        zone_query=None,
        **carry,
    )


async def _saved_customer(s, business_id: uuid.UUID, phone: str) -> Customer | None:
    """The stored customer row (for prefilling saved contact details at checkout)."""
    return await s.scalar(
        select(Customer).where(
            Customer.business_id == business_id, Customer.wa_phone == phone
        )
    )


def _reuse_saved_location(saved: Customer | None, zones: list, state: dict) -> dict[str, object]:
    """Reuse a returning customer's saved delivery AREA + street address so they aren't re-asked.

    Gap-fill only (never overrides what the customer already set this session), and the saved zone
    is reused ONLY if it's still an active zone (it may have been deleted/deactivated since). Returns
    the state overrides to apply. The values are shown on the confirm screen, so reuse stays visible
    and editable — the customer can change either via the Edit button or update_detail.
    """
    out: dict[str, object] = {}
    if saved is None:
        return out
    if (
        saved.default_zone_id
        and not (state.get("zone_serviceable") and state.get("zone_id"))
        and any(z.id == saved.default_zone_id for z in zones)
    ):
        out["zone_id"] = str(saved.default_zone_id)
        out["zone_serviceable"] = True
    if saved.default_address and not state.get("address"):
        out["address"] = saved.default_address
    return out


def _format_quote(cart: list, quote, cur: str) -> str:
    """Itemized, server-priced cart summary — shown by view_cart and on the confirm prompt.

    Formatted for WhatsApp: a *bold* heading, one item per line (no leading-space indent, which
    renders raggedly in the chat), then the totals set off by a blank line with the grand total
    in *bold*. WhatsApp bold is a single asterisk; the renderer passes these through verbatim.
    """
    out = ["*Your order*", ""]
    for i, (c, pl) in enumerate(zip(cart, quote.lines), start=1):
        opt = f" ({c['options_label']})" if c["options_label"] else ""
        out.append(f"{i}. {pl.quantity} x {pl.name}{opt} - {pl.line_total} {cur}")
    out.append("")
    out.append(f"Subtotal: {quote.subtotal} {cur}")
    if quote.delivery_fee:
        out.append(f"Delivery: {quote.delivery_fee} {cur}")
    if quote.packaging_fee:
        out.append(f"Packaging: {quote.packaging_fee} {cur}")
    out.append(f"*Total: {quote.total} {cur}*")
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
    """The full confirm summary: priced cart + fulfillment + the customer's contact details.

    Name is required (always present). Email and alternate phone are OPTIONAL — shown with a
    dash when the customer hasn't provided them, so the summary always lists every detail.
    """
    lines = [_format_quote(cart, quote, cur), ""]
    lines.append(f"*Delivery to:* {address}" if fulfillment == "delivery" else "*Pickup*")
    lines.append(f"Name: {name or '-'}")
    lines.append(f"Alt. phone: {alt_phone or '-'}")
    lines.append(f"Email: {email or '-'}")
    return "\n".join(lines)


def _format_placed(
    order_code: str, total, ful: str, cur: str, name: str | None, address: str | None
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
        "*Order confirmed!*\n\n"
        f"*Order {order_code}*\n"
        f"Total: *{total} {cur}* (cash on {pay})\n"
        f"{where}\n\n"
        f"{greeting}We'll message you here with updates."
    )


@tool
async def view_cart(runtime: ToolRuntime = None) -> str:  # type: ignore[assignment]
    """Show an itemized, server-priced summary of the current cart with the running total.

    Always call this to show the customer their order and total BEFORE asking them to
    confirm. Quantities, option prices, delivery, and packaging fees are all computed by the
    server here — show these numbers, never your own.

    Call shape: view_cart()  — takes no arguments.
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
    """Start (and finalize) checkout. Call this the moment the customer wants to order — you may
    call it even before the cart has items, to settle delivery up front.

    You do NOT collect delivery/pickup, the delivery area/address, or contact details yourself —
    the SYSTEM does, deterministically. Just call place_order; it figures out what's still needed
    and the system asks the customer for each missing piece, validating and saving every answer in
    code: delivery or pickup; for DELIVERY it shows the customer a list of the delivery AREAS to tap
    (or asks them to type it) and checks serviceability EARLY — telling them and offering pickup if
    their area isn't covered — then the street address; then the name. Email and alternate phone are
    OPTIONAL and never block the order. When everything is present it shows the customer the
    server-priced total + their details with the [Confirm][Edit][Cancel] buttons (the system renders
    these); the order is created only after they TAP Confirm.

    So: call place_order to begin checkout (even with an empty cart, to settle delivery early), and
    call it again after a Confirm tap to finalize. Never invent or pass an area, address, or contact
    value - the system owns that.

    Call shape: place_order()  — takes no arguments.
    """
    state = runtime.state
    cart = state.get("cart") or []

    async with SessionLocal() as s:
        b = await catalog.load_business_for_agent(s, _bid(runtime))
        if b is None:
            return _msg("This business isn't available.", runtime)
        cur = b.currency
        if not b.accepting_orders:
            return _msg("We're not accepting orders right now.", runtime)
        if not catalog.is_open_now(list(b.hours), b.timezone):
            return _msg("We're closed right now, so I can't place the order.", runtime)

        # A returning customer's saved profile, loaded once and reused below to prefill the area,
        # street address, and contact details so they aren't re-asked (shown on the confirm screen,
        # so reuse stays visible + editable).
        saved = await _saved_customer(s, b.id, _phone(runtime))

        # 1) Fulfillment (deterministic). Auto-set when only one method is offered; otherwise
        #    hand off to run_turn to ASK (Delivery/Pickup buttons) and capture the tap in code.
        fulfillment = state.get("fulfillment")
        if fulfillment not in ("delivery", "pickup"):
            if b.offers_delivery and b.offers_pickup:
                return _msg(
                    "Need to know delivery or pickup; the system will ask the customer.",
                    runtime, pending_checkout_field="fulfillment",
                )
            if b.offers_delivery:
                fulfillment = "delivery"
            elif b.offers_pickup:
                fulfillment = "pickup"
            else:
                return _msg("We're not taking delivery or pickup orders right now.", runtime)
        # Carry the (possibly auto-set) fulfillment into every later return so it persists.
        carry: dict[str, object] = {"fulfillment": fulfillment}

        # 2) Delivery AREA / zone (deterministic, EARLY — before a cart is even required, so an
        #    out-of-area customer is told up front, not after building an order). The customer
        #    PICKS their area from the active zones (an exact tap — no address-text guessing);
        #    with more zones than a WhatsApp list can hold they TYPE it and we match it here. The
        #    model never handles or invents the area.
        zone_id = state.get("zone_id")
        address = state.get("address")
        if fulfillment == "delivery":
            zones = await catalog.delivery_zones(s, b)
            # Reuse the returning customer's saved area + street (gap-fill only; the saved zone is
            # reused only if it's still an active zone). These are shown on the confirm screen.
            reuse = _reuse_saved_location(saved, zones, state)
            carry.update(reuse)
            zone_id = reuse.get("zone_id") or zone_id
            address = reuse.get("address") or address
            serviceable = reuse.get("zone_serviceable") or state.get("zone_serviceable")
            if zones and not (serviceable and zone_id):
                query = state.get("zone_query")
                zone = catalog.match_zone(zones, query) if query else None
                if zone is not None:
                    zone_id = str(zone.id)
                    carry["zone_id"] = zone_id
                    carry["zone_serviceable"] = True
                    carry["zone_query"] = None
                else:
                    # First ask, or a typed area we couldn't match → (re-)ask, naming the
                    # unmatched area so the re-ask plainly says we don't deliver there.
                    return _ask_zone(runtime, b, zones, cur, carry, out_of_area=query)
            elif zone_id:
                carry["zone_id"] = zone_id
                carry["zone_serviceable"] = True

        # 3) We have delivery/pickup (and, for delivery, a serviceable area). NOW we need items —
        #    but since the area is already confirmed, an empty cart just means "keep ordering".
        if not cart:
            return _msg(
                "Delivery or pickup and the delivery area are set, but the cart is still empty. "
                "Ask the customer what they'd like to order.",
                runtime, **carry,
            )

        # 4) Delivery STREET address (for the driver) — reused from the saved profile when present
        #    (set in step 2), otherwise asked. Collected after the area is confirmed.
        if fulfillment == "delivery" and not address:
            return _msg(
                "Need the delivery street address; the system will ask the customer.",
                runtime, pending_checkout_field="address", **carry,
            )

        # 5) Contact: NAME is required (asked in code if missing). Email + alternate phone are
        #    OPTIONAL — prefilled from the saved record if present, never asked for, never blocking.
        name = state.get("customer_name")
        email = state.get("customer_email")
        alt_phone = state.get("customer_alt_phone")
        prefill: dict[str, object] = {}
        if not (name and email and alt_phone):
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
            # No name on file and none captured yet → hand off to the deterministic collector:
            # run_turn asks for it and validates/saves the reply in code.
            return _msg(
                "The order needs a name; the system will ask the customer and record it.",
                runtime,
                pending_checkout_field="name",
                **carry,
                **prefill,
            )

        lines = [
            CartLineInput(
                product_id=uuid.UUID(c["product_id"]),
                quantity=c["quantity"],
                option_item_ids=_uuids(c["option_item_ids"]),
            )
            for c in cart
        ]
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
            return _msg(e.message, runtime, confirmed=False, step="building", **carry, **prefill)

        # Business-level minimum (distinct from per-zone minimum) — deferred guard, enforced here.
        if quote.subtotal < (b.min_order_amount or Decimal("0")):
            return _msg(
                f"The minimum order is {b.min_order_amount} {cur}; "
                f"your subtotal is {quote.subtotal} {cur}. Add a bit more?",
                runtime,
                confirmed=False,
                step="building",
                **carry,
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
                **carry,
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
            return _msg(e.message, runtime, confirmed=False, step="building", **carry, **prefill)
        order_code, total, ful = order.order_code, order.total, order.fulfillment

    # The order is committed. run_turn sends `order_placed_summary` to the customer verbatim and
    # ALONE (the deterministic, server-authoritative confirmation), so this tool message is for
    # the model only — tell it the customer has already been confirmed, so it does not compose a
    # second, possibly wrong, order summary of its own.
    return _msg(
        f"Order {order_code} created and the confirmation has ALREADY been sent to the customer. "
        "Do NOT send another order summary or repeat the order code/total — a short thank-you "
        "is enough.",
        runtime,
        cart=[],
        confirmed=False,
        awaiting_confirm=False,
        confirm_summary=None,
        order_placed_summary=_format_placed(order_code, total, ful, cur, name, address),
        step="placed",
        **prefill,
    )


@tool(parse_docstring=True)
async def reorder(order_code: str | None = None, runtime: ToolRuntime = None) -> Command:  # type: ignore[assignment]
    """Repeat one of THIS customer's past orders — add its items to the cart again.

    Use this when the customer wants the "same as last time", to "reorder", "the usual", or taps
    a Reorder button. Omit `order_code` for their most recent order, or pass a specific past order
    code. Every line is re-checked and re-priced against TODAY'S menu (prices and availability
    change): anything now sold out, removed, or whose options changed is skipped and reported back
    to you so you can tell the customer plainly. The items are ADDED to whatever is already in the
    cart. Reorder does NOT set delivery/pickup — continue the normal flow afterwards (ask delivery
    or pickup, confirm a delivery address, then place_order).

    Call shape:
        reorder()                     # repeat the most recent order
        reorder(order_code="K7Q2X9")  # repeat one specific past order

    Args:
        order_code: A specific past order code to repeat, a short string like "K7Q2X9". Omit it
            for the most recent order.
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
        if order_code is not None:
            stmt = stmt.where(Order.order_code == order_code)
        order = (await s.execute(stmt)).scalars().first()
        if order is None:
            which = f" {order_code}" if order_code is not None else ""
            return _msg(
                f"I couldn't find a past order{which} to repeat. Want to see the menu?", runtime
            )

        past_code = order.order_code
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
            f"I couldn't re-add anything from order {past_code} - those items aren't available "
            f"right now.{detail}",
            runtime,
        )

    cart = list(runtime.state.get("cart") or []) + new_lines
    msg = f"Re-added from order {past_code}: {'; '.join(added)}. Cart now has {len(cart)} line(s)."
    if skipped:
        msg += f" Couldn't re-add: {'; '.join(skipped)}."
    return _msg(
        msg,
        runtime,
        cart=cart,
        step="building",
        selected_product_id=new_lines[-1]["product_id"],
    )


_UPDATABLE_FIELDS = {"name", "email", "alternate_phone", "address", "area"}


@tool(parse_docstring=True)
async def update_detail(
    field: str, value: str, runtime: ToolRuntime = None  # type: ignore[assignment]
) -> Command:
    """Propose a change to a saved detail: name / email / alternate_phone / address / area.

    Use ONLY when the customer explicitly asks to change a detail:
    - "name" / "email" / "alternate_phone" - their contact details.
    - "area" - their delivery AREA/zone (e.g. "I'm in Defence now", "deliver to a different area",
      "change my zone to DHA"). The system re-checks the area against your real delivery zones and
      re-asks for the street address within it - so use "area", NOT "address", for an area/zone change.
    - "address" - their street address WITHIN the same area (house/flat, street, landmark), e.g.
      "it's House 7 not House 5". This does NOT change the area.
    If the customer is moving somewhere new, that is usually "area" (you may also send "address").

    Pass the field and the NEW value the customer actually gave. You do NOT apply or save it: the
    system validates it, asks the customer to confirm with a button, and only then updates this
    order AND their saved profile. Never invent a value, and don't use this to collect a first-time
    value - that happens automatically.

    Call shape (use the customer's real value):
        update_detail(field="area", value="Defence")

    Args:
        field: Which detail to change - one of "name", "email", "alternate_phone", "address", "area".
        value: The new value, exactly as the customer stated it.
    """
    field = (field or "").strip().lower()
    if field not in _UPDATABLE_FIELDS:
        return _msg(
            'I can update name, email, alternate_phone, address, or area only.', runtime
        )
    raw = " ".join((value or "").split())
    if not raw:
        return _msg("I need the new value to make that change.", runtime)
    # Validate contact fields exactly like the deterministic capture (EmailStr / phone digits);
    # address is free text. The model proposes the value, code validates it, the customer confirms.
    if field in ("name", "email", "alternate_phone"):
        try:
            ContactDetails(**{field: raw})
        except (ValueError, TypeError):
            label = field.replace("_", " ")
            return _msg(f"That doesn't look like a valid {label} - please send it again.", runtime)
    label = field.replace("_", " ")
    return _msg(
        f"Got it - the system will confirm updating the {label} with the customer before saving.",
        runtime,
        # APPEND (the reducer accumulates) so asking to change several details in one message
        # collects them all; the customer confirms them together with a single Update tap.
        pending_updates=[{"field": field, "value": raw}],
    )


@tool(parse_docstring=True)
async def request_human(reason: str, runtime: ToolRuntime = None) -> Command:  # type: ignore[assignment]
    """Hand the conversation to a human and stop auto-replying.

    Use for anything you can't do yourself: refunds, complaints, anger, or an explicit
    request to talk to a person. After this the agent goes silent for the thread.

    Call shape:
        request_human(reason="Customer wants a refund on order K7Q2X9")

    Args:
        reason: A short free-text string on why you're escalating, for the team that picks it up.
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
    view_cart,
    place_order,
    reorder,
    update_detail,
    request_human,
]
