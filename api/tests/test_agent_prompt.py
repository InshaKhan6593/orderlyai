"""Per-tenant system prompt: the upsell toggle and open/accepting state shape the prompt."""
from __future__ import annotations

from app.agent.prompts import BusinessBrief, build_system_prompt


def _brief(**over) -> BusinessBrief:
    base = dict(
        name="Mario's Pizza",
        business_type="restaurant",
        currency="PKR",
        hours_summary="Mon: 10:00–22:00",
        is_open=True,
        accepting_orders=True,
        offers_delivery=True,
        offers_pickup=True,
        min_order_amount="500",
        packaging_fee="20",
        upsell_enabled=True,
        greeting="Welcome to Mario's!",
        extra_instructions=None,
        handoff_phone=None,
    )
    base.update(over)
    return BusinessBrief(**base)


def test_prompt_includes_identity_and_currency():
    p = build_system_prompt(_brief())
    assert "Mario's Pizza" in p
    assert "PKR" in p
    assert "English only" in p  # Meta en-only rule


def test_upsell_on_vs_off():
    on = build_system_prompt(_brief(upsell_enabled=True))
    off = build_system_prompt(_brief(upsell_enabled=False))
    assert "suggest ONE relevant add-on" in on
    assert "Do NOT upsell" in off


def test_not_accepting_orders_warns_model():
    p = build_system_prompt(_brief(accepting_orders=False))
    assert "NOT accepting orders" in p


def test_closed_state_noted():
    p = build_system_prompt(_brief(is_open=False, accepting_orders=True))
    assert "CLOSED" in p


def test_read_before_write_rule_present():
    p = build_system_prompt(_brief())
    # The prompt must state the order can't be placed before pricing + confirm.
    assert "place_order" in p
    assert "Confirm" in p


def test_tags_vs_facts_rule_present():
    p = build_system_prompt(_brief())
    # Owner tags must be framed as labels; real popularity comes from order history.
    assert "get_popular_items" in p
    assert "bestseller" in p
    assert "never guess" in p.lower()
