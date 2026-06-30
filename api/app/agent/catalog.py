"""Read helpers the agent tools format for the model: menu, item detail, hours, zones.

DB-backed (tenant-scoped) but no LangChain import. Everything returns compact,
model-friendly text that includes the ids the model must pass back to write tools
(product ids, option ids) - the model can't invent ids it never saw.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.business import Business
from app.models.menu import Category, Product
from app.models.ops import BusinessHours, DeliveryZone
from app.services.order_service import _load_products  # shared loader


async def load_business_for_agent(db: AsyncSession, business_id: uuid.UUID) -> Business | None:
    """Eager-load everything the agent reads off the Business (hours, agent_config, categories)."""
    return await db.scalar(
        select(Business)
        .where(Business.id == business_id)
        .options(
            selectinload(Business.hours),
            selectinload(Business.agent_config),
            selectinload(Business.categories),
        )
    )


def category_names(business: Business) -> list[str]:
    """Active category names (sorted), off the eager-loaded relationship - used to tell the
    agent, in its prompt, which categories this business actually has so it maps requests to
    real categories instead of guessing."""
    cats = sorted(
        (c for c in business.categories if c.is_active),
        key=lambda c: (c.sort_order, c.name),
    )
    return [c.name for c in cats]

_DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


# --------------------------------------------------------------------------- #
# Hours
# --------------------------------------------------------------------------- #
def _tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return ZoneInfo("UTC")


def _their_dow(now: datetime) -> int:
    """Map Python weekday (Mon=0..Sun=6) to the schema's day_of_week (Sun=0..Sat=6)."""
    return (now.weekday() + 1) % 7


def format_hours(hours: list[BusinessHours]) -> str:
    by_day = {h.day_of_week: h for h in hours}
    parts: list[str] = []
    for dow in range(7):
        h = by_day.get(dow)
        if h is None or h.is_closed or h.open_time is None or h.close_time is None:
            parts.append(f"{_DAYS[dow]}: closed")
        else:
            parts.append(
                f"{_DAYS[dow]}: {h.open_time.strftime('%H:%M')}-{h.close_time.strftime('%H:%M')}"
            )
    return ", ".join(parts)


def is_open_now(hours: list[BusinessHours], timezone: str, now: datetime | None = None) -> bool:
    now = now or datetime.now(_tz(timezone))
    h = next((x for x in hours if x.day_of_week == _their_dow(now)), None)
    if h is None or h.is_closed or h.open_time is None or h.close_time is None:
        return False
    t = now.timetz().replace(tzinfo=None)
    if h.close_time >= h.open_time:
        return h.open_time <= t <= h.close_time
    # Overnight window (e.g. 18:00-02:00): open if after open OR before close.
    return t >= h.open_time or t <= h.close_time


# --------------------------------------------------------------------------- #
# Menu / item
# --------------------------------------------------------------------------- #
async def menu_overview(
    db: AsyncSession, business: Business, *, category: str | None = None
) -> str:
    """The menu as model-friendly text. Pass ``category`` to show only one section.

    The match is case-insensitive on the owner's category names. If ``category`` is given but
    matches nothing, we return the list of real categories so the agent can map the request or
    ask - never an empty/confusing result.
    """
    cats = (
        (
            await db.execute(
                select(Category)
                .where(Category.business_id == business.id, Category.is_active.is_(True))
                .order_by(Category.sort_order, Category.name)
            )
        )
        .scalars()
        .all()
    )

    matched: Category | None = None
    if category:
        wanted = category.strip().lower()
        matched = next((c for c in cats if c.name.lower() == wanted), None)
        if matched is None:
            names = ", ".join(c.name for c in cats) or "(none yet)"
            return (
                f'There is no "{category}" category. Available categories: {names}. '
                "Pick one of these, or call get_menu with no category to see the whole menu."
            )

    stmt = select(Product).where(
        Product.business_id == business.id,
        Product.is_available.is_(True),
        Product.is_archived.is_(False),
    )
    if matched is not None:
        stmt = stmt.where(Product.category_id == matched.id)
    prods = (await db.execute(stmt.order_by(Product.sort_order, Product.name))).scalars().all()

    if not prods:
        if matched is not None:
            return f'Nothing is available in "{matched.name}" right now.'
        return "The menu is empty right now - no items available."

    cur = business.currency
    by_cat: dict[uuid.UUID | None, list[Product]] = {}
    for p in prods:
        by_cat.setdefault(p.category_id, []).append(p)

    lines: list[str] = []

    def render(title: str, items: list[Product]) -> None:
        lines.append(f"\n{title}:")
        for p in items:
            tags = f" [tags: {', '.join(p.tags)}]" if p.tags else ""
            lines.append(f"  - {p.name} - {p.price} {cur}{tags} [id: {p.id}]")

    for c in cats:
        items = by_cat.pop(c.id, [])
        if items:
            render(c.name, items)
    leftovers = [p for items in by_cat.values() for p in items]
    if leftovers:
        render("Other", leftovers)
    header = f"Menu ({matched.name}):" if matched is not None else "Available menu:"
    return header + "".join(lines)


async def item_detail(db: AsyncSession, business: Business, product_id: str) -> str:
    try:
        pid = uuid.UUID(product_id)
    except (ValueError, AttributeError):
        return f"'{product_id}' is not a valid item id. Call get_menu to see items and their ids."

    products = await _load_products(db, business.id, {pid})
    p = products.get(pid)
    if p is None or p.is_archived:
        return "That item isn't on the menu. Call get_menu to see what's available."

    cur = business.currency
    out = [f"{p.name} - {p.price} {cur} [id: {p.id}]"]
    if p.description:
        out.append(p.description)
    if p.tags:
        out.append(f"Tags (owner labels): {', '.join(p.tags)}")
    if not p.is_available:
        out.append("(currently unavailable)")
    if p.image_url:
        out.append(f"image_url: {p.image_url}")

    if p.modifier_groups:
        out.append("\nOptions:")
        for a in p.modifier_groups:
            req = "required" if a.is_required else "optional"
            kind = a.select_type  # single | multi
            bounds = f"min {a.min_select}" + (
                f", max {a.max_select}" if a.max_select is not None else ""
            )
            tmpl = "template" if a.is_template else "dish-specific"
            out.append(f"  {a.display_name} ({req}, {kind}-select, {bounds}, {tmpl}):")
            for opt in a.items:
                delta = opt.price_delta
                sign = "+" if delta >= 0 else ""
                default = " (default)" if opt.is_default else ""
                desc = f" - {opt.description}" if opt.description else ""
                out.append(
                    f"    - {opt.name}: {sign}{delta} {cur}{default}{desc} [option_id: {opt.id}]"
                )
    else:
        out.append("\nNo options to choose - order as-is.")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# Delivery zones
# --------------------------------------------------------------------------- #
async def delivery_zones(db: AsyncSession, business: Business) -> list[DeliveryZone]:
    return (
        (
            await db.execute(
                select(DeliveryZone)
                .where(
                    DeliveryZone.business_id == business.id,
                    DeliveryZone.is_active.is_(True),
                )
                .order_by(DeliveryZone.name)
            )
        )
        .scalars()
        .all()
    )


def match_zone(zones: list[DeliveryZone], area_or_address: str) -> DeliveryZone | None:
    """Best-effort match of a free-text area against active zone names."""
    text = (area_or_address or "").lower()
    if not text:
        return None
    for z in zones:
        if z.name.lower() in text or text in z.name.lower():
            return z
    # token overlap fallback
    tokens = set(text.replace(",", " ").split())
    best: tuple[int, DeliveryZone | None] = (0, None)
    for z in zones:
        overlap = len(tokens & set(z.name.lower().split()))
        if overlap > best[0]:
            best = (overlap, z)
    return best[1]


def zones_summary(zones: list[DeliveryZone], currency: str, *, max_listed: int = 20) -> str:
    """A compact, model-facing list of the delivery areas (name + fee) for the system prompt, so
    the agent can ANSWER "where do you deliver / do you cover my area / what's the fee" itself.

    Empty when there are no active zones (the builder turns that into a 'no set zones' hint). Capped
    so a tenant with very many zones can't bloat the prompt — the overflow is summarised as a count.
    """
    if not zones:
        return ""
    shown = zones[:max_listed]
    parts = [
        f"{z.name} ({z.fee} {currency})" if z.fee and z.fee > 0 else f"{z.name} (free)"
        for z in shown
    ]
    extra = len(zones) - len(shown)
    if extra > 0:
        parts.append(f"and {extra} more areas")
    return ", ".join(parts)
