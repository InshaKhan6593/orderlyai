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
    extra_instructions: str | None = None
    handoff_phone: str | None = None


def _fulfillment_line(b: BusinessBrief) -> str:
    if b.offers_delivery and b.offers_pickup:
        return "You offer both delivery and pickup."
    if b.offers_delivery:
        return "You offer delivery only (no pickup)."
    if b.offers_pickup:
        return "You offer pickup only (no delivery)."
    return "You are not currently offering delivery or pickup."


def build_system_prompt(b: BusinessBrief) -> str:
    if not b.accepting_orders:
        status_note = S.STATUS_NOT_ACCEPTING
    elif not b.is_open:
        status_note = S.STATUS_CLOSED
    else:
        status_note = ""

    values = {
        "name": b.name,
        "business_type": b.business_type,
        "currency": b.currency,
        "hours_summary": b.hours_summary,
        "fulfillment_line": _fulfillment_line(b),
        "packaging_fee": b.packaging_fee,
        "min_order_amount": b.min_order_amount,
        "status_note": status_note,
        "greeting": b.greeting,
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
    return "\n\n".join(block.format(**values) for block in S.ORDER)
