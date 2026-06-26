"""Assemble the per-tenant system prompt from the readable sections in ``sections.py``.

Pure function of primitives (no ORM / LangChain import) so it's trivially testable.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.agent.prompts import sections as S


@dataclass
class BusinessBrief:
    name: str
    business_type: str
    currency: str
    hours_summary: str
    is_open: bool
    accepting_orders: bool
    offers_delivery: bool
    offers_pickup: bool
    min_order_amount: str
    packaging_fee: str
    upsell_enabled: bool
    greeting: str
    categories_summary: str = ""
    extra_instructions: str | None = None
    handoff_phone: str | None = None
    # The pre-rendered menu index (name/price/tags/id), inlined into the prompt when it fits
    # the preload budget. None → the menu is fetched on demand via the get_menu tool instead.
    menu_index: str | None = None


def _fulfillment_line(b: BusinessBrief) -> str:
    if b.offers_delivery and b.offers_pickup:
        return "You offer both delivery and pickup."
    if b.offers_delivery:
        return "You offer delivery only (no pickup)."
    if b.offers_pickup:
        return "You offer pickup only (no delivery)."
    return "You are not currently offering delivery or pickup."


def _menu_block(b: BusinessBrief) -> str:
    """The menu section: the live menu inlined when available, else a pointer to get_menu.

    Inlining lets the agent answer menu questions straight from context instead of
    round-tripping the get_menu tool every time (the runtime also drops get_menu from the
    tool set on those turns — see ``TenantMiddleware``)."""
    if b.menu_index:
        return (
            "CURRENT MENU (already loaded — use these exact items, prices, and ids; "
            f"do NOT call get_menu):\n{b.menu_index}"
        )
    return (
        "MENU ACCESS: the menu is not inlined here — call get_menu (optionally with a "
        "category) to see the current items, prices, and ids before using them."
    )


# The full system-prompt template (with f-string `{placeholders}`), assembled from the
# ordered sections. This single body is what we render locally AND push to LangSmith — so
# the template in the Hub is exactly what the agent runs.
SYSTEM_SCAFFOLD = "\n\n".join(S.ORDER)


def prompt_variables(b: BusinessBrief) -> dict[str, str]:
    """The per-tenant values that fill the template placeholders. Pure (no I/O), so it's
    the same whether the template is the in-code default or pulled from LangSmith."""
    if not b.accepting_orders:
        status_note = S.STATUS_NOT_ACCEPTING
    elif not b.is_open:
        status_note = S.STATUS_CLOSED
    else:
        status_note = ""

    return {
        "name": b.name,
        "business_type": b.business_type,
        "currency": b.currency,
        "hours_summary": b.hours_summary,
        "fulfillment_line": _fulfillment_line(b),
        "packaging_fee": b.packaging_fee,
        "min_order_amount": b.min_order_amount,
        "status_note": status_note,
        "menu_block": _menu_block(b),
        "greeting": b.greeting,
        "categories_summary": b.categories_summary or "(none set up yet)",
        "upsell_line": S.UPSELL_ON if b.upsell_enabled else S.UPSELL_OFF,
        "handoff": (
            f" If you hand off, the human contact is {b.handoff_phone}."
            if b.handoff_phone
            else ""
        ),
        "extra": (
            f"\n\nBusiness-specific instructions:\n{b.extra_instructions}"
            if b.extra_instructions
            else ""
        ),
    }


def build_system_prompt(b: BusinessBrief) -> str:
    """Render the per-tenant system prompt from the in-code template — the canonical source
    of truth. ``hub.render_system_prompt`` wraps this with an optional LangSmith
    pull-override; this function itself stays dependency-free and trivially testable."""
    return SYSTEM_SCAFFOLD.format(**prompt_variables(b))
