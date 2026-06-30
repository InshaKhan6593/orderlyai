"""Checkout contact details: validation, deterministic capture, the placed message.

These are pure unit tests (no DB / no LLM) covering the pieces that make place_order
production-grade: the validated ContactDetails schema, the deterministic code-side capture of a
typed contact reply, and the server-authoritative "order placed" confirmation text.
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.agent.runtime import _capture_contact, _ensure_confirm_buttons
from app.agent.schemas import AgentReply, BTN_CONFIRM, ImageMessage, TextMessage
import uuid

from app.agent.tools import (
    TOOLS,
    _format_confirm,
    _format_placed,
    _format_quote,
    _reuse_saved_location,
)
from app.schemas.customer import ContactDetails
from app.schemas.order import OrderCreate


# --------------------------------------------------------------------------- #
# Confirm step renders ONE summary (regression: model summary + deterministic = double)
# --------------------------------------------------------------------------- #
def test_confirm_step_drops_model_text_so_summary_is_not_doubled():
    # The model often writes its own order summary; at the confirm step we render the
    # authoritative server-priced summary in the button body, so the model's text must be
    # dropped — otherwise the customer sees the summary twice.
    model_reply = AgentReply(
        messages=[TextMessage(kind="text", body="Here's your order: 2 x Burger - 500 PKR. Total 500 PKR.")]
    )
    out = _ensure_confirm_buttons(model_reply, "OFFICIAL SUMMARY: Total 500 PKR")
    # Exactly one message: the buttons, carrying the deterministic summary; model text gone.
    assert len(out.messages) == 1
    btns = out.messages[0]
    assert any(b.id == BTN_CONFIRM for b in btns.buttons)
    assert "OFFICIAL SUMMARY" in btns.body
    assert "Here's your order" not in btns.body


def test_confirm_step_keeps_a_model_image_alongside_the_summary():
    # An image of the dish is fine to keep; only the duplicate text summary is dropped.
    model_reply = AgentReply(
        messages=[
            ImageMessage(kind="image", image_url="http://x/y.jpg", caption="Veg Burger"),
            TextMessage(kind="text", body="Your order total is 500 PKR."),
        ]
    )
    out = _ensure_confirm_buttons(model_reply, "OFFICIAL SUMMARY: Total 500 PKR")
    kinds = [m.kind for m in out.messages]
    assert kinds == ["image", "buttons"]  # image kept, text dropped, buttons added


# --------------------------------------------------------------------------- #
# ContactDetails — the validated Pydantic the agent collects at checkout
# --------------------------------------------------------------------------- #
def test_contact_details_normalizes_and_validates():
    d = ContactDetails(name="  John   Doe ", email="john@example.com", alternate_phone="+1 650 555 1234")
    assert d.name == "John Doe"  # collapsed whitespace, trimmed
    assert str(d.email) == "john@example.com"
    assert d.alternate_phone == "+1 650 555 1234"


def test_contact_details_blank_becomes_none():
    d = ContactDetails(name="   ", email=None, alternate_phone="")
    assert d.name is None
    assert d.alternate_phone is None


def test_contact_details_rejects_bad_email():
    with pytest.raises(ValidationError):
        ContactDetails(email="not-an-email")


def test_contact_details_rejects_implausible_phone():
    with pytest.raises(ValidationError):
        ContactDetails(alternate_phone="12")  # too few digits to be a real number


# --------------------------------------------------------------------------- #
# Deterministic "order placed" confirmation
# --------------------------------------------------------------------------- #
def test_format_confirm_shows_dash_for_missing_optional_fields():
    # Name is required; email + alternate phone are optional and rendered as "-" when absent,
    # so the customer always sees the full detail list before confirming.
    from types import SimpleNamespace

    quote = SimpleNamespace(
        lines=[SimpleNamespace(quantity=1, name="Burger", line_total=Decimal("500"))],
        subtotal=Decimal("500"), delivery_fee=Decimal("0"),
        packaging_fee=Decimal("0"), total=Decimal("500"),
    )
    cart = [{"options_label": "", "quantity": 1}]
    out = _format_confirm(cart, quote, "PKR", "pickup", None, "Ada", None, None)
    assert "Name: Ada" in out
    assert "Alt. phone: -" in out   # optional, not provided
    assert "Email: -" in out        # optional, not provided


def test_format_placed_pickup_has_order_code_total_and_name():
    msg = _format_placed("K7Q2X9", Decimal("850.00"), "pickup", "PKR", "Ada", None)
    assert "K7Q2X9" in msg
    assert "850.00 PKR" in msg
    assert "Ada" in msg
    assert "pickup" in msg


def test_format_placed_delivery_includes_address():
    msg = _format_placed("R4M8TP", Decimal("560.00"), "delivery", "PKR", "Ada", "12 Park Lane")
    assert "R4M8TP" in msg
    assert "12 Park Lane" in msg
    assert "delivery" in msg


def test_format_placed_without_name_still_valid():
    msg = _format_placed("H9XW2K", Decimal("100"), "pickup", "PKR", None, None)
    assert "H9XW2K" in msg and "100 PKR" in msg  # no crash, still confirms the order


def test_format_placed_uses_whatsapp_bold():
    # The placed confirmation uses WhatsApp single-asterisk *bold* for the headline, order code,
    # and total — plain text reads flat in the chat.
    msg = _format_placed("K7Q2X9", Decimal("850.00"), "pickup", "PKR", "Ada", None)
    assert "*Order confirmed!*" in msg
    assert "*Order K7Q2X9*" in msg
    assert "*850.00 PKR*" in msg


# --------------------------------------------------------------------------- #
# Cart / confirm summaries — WhatsApp formatting + spacing (the customer-facing screen)
# --------------------------------------------------------------------------- #
def _fake_quote():
    """A priced-cart stand-in (no DB) shaped like what order_service.quote_cart returns."""
    lines = [
        SimpleNamespace(quantity=2, name="Veg Burger", line_total=Decimal("500.00")),
        SimpleNamespace(quantity=1, name="Fries", line_total=Decimal("120.00")),
    ]
    return SimpleNamespace(
        lines=lines,
        subtotal=Decimal("620.00"),
        delivery_fee=Decimal("50.00"),
        packaging_fee=Decimal("20.00"),
        total=Decimal("690.00"),
    )


def _fake_cart():
    return [{"options_label": "Large"}, {"options_label": ""}]


def test_format_quote_uses_bold_heading_total_and_clean_spacing():
    out = _format_quote(_fake_cart(), _fake_quote(), "PKR")
    assert "*Your order*" in out  # bold heading
    assert "*Total: 690.00 PKR*" in out  # bold grand total
    # one item per line, the chosen option shown, and NO leading-space indent (renders raggedly)
    assert "1. 2 x Veg Burger (Large) - 500.00 PKR" in out
    assert "  " not in out  # no double-space indentation anywhere
    assert "\n\nSubtotal" in out  # a blank line sets the totals block apart from the items


def test_format_confirm_embeds_priced_cart_with_bold_fulfillment():
    out = _format_confirm(
        _fake_cart(), _fake_quote(), "PKR", "delivery", "12 Park Lane", "Ada", None, None
    )
    assert "*Your order*" in out  # the priced cart is embedded
    assert "*Total: 690.00 PKR*" in out
    assert "*Delivery to:* 12 Park Lane" in out  # fulfillment label bold, address plain
    assert "Name: Ada" in out


def test_format_confirm_pickup_has_no_address_line():
    out = _format_confirm(_fake_cart(), _fake_quote(), "PKR", "pickup", None, "Ada", None, None)
    assert "*Pickup*" in out
    assert "Delivery to" not in out


# --------------------------------------------------------------------------- #
# Tool wiring + order schema threading
# --------------------------------------------------------------------------- #
def test_set_contact_details_tool_not_exposed():
    # Contact details are captured deterministically in code (run_turn), never set by the model,
    # so there must be NO LLM-callable set_contact_details tool.
    assert "set_contact_details" not in {t.name for t in TOOLS}


# --------------------------------------------------------------------------- #
# Returning-customer reuse of the saved delivery area + address (gap-fill, validated)
# --------------------------------------------------------------------------- #
def test_reuse_saved_location_prefills_area_and_address():
    zid = uuid.uuid4()
    saved = SimpleNamespace(default_zone_id=zid, default_address="House 5, Defence")
    out = _reuse_saved_location(saved, [SimpleNamespace(id=zid)], {})
    assert out["zone_id"] == str(zid)
    assert out["zone_serviceable"] is True
    assert out["address"] == "House 5, Defence"


def test_reuse_saved_location_skips_zone_no_longer_active():
    # The saved zone was deleted/deactivated → don't reuse it (it would be unserviceable); the saved
    # street address is still reused.
    saved = SimpleNamespace(default_zone_id=uuid.uuid4(), default_address="House 5")
    out = _reuse_saved_location(saved, [SimpleNamespace(id=uuid.uuid4())], {})
    assert "zone_id" not in out
    assert out["address"] == "House 5"


def test_reuse_saved_location_is_gap_fill_only():
    # Whatever the customer already chose this session wins — saved values never override it.
    zid = uuid.uuid4()
    saved = SimpleNamespace(default_zone_id=zid, default_address="House 5")
    state = {"zone_id": "z9", "zone_serviceable": True, "address": "Elsewhere"}
    assert _reuse_saved_location(saved, [SimpleNamespace(id=zid)], state) == {}


def test_reuse_saved_location_none_customer():
    assert _reuse_saved_location(None, [], {}) == {}


# --------------------------------------------------------------------------- #
# Deterministic capture of a typed contact reply (code, not the model)
# --------------------------------------------------------------------------- #
def test_capture_contact_valid_name():
    value, error = _capture_contact("name", "  Ada   Khan ")
    assert value == "Ada Khan" and error is None  # whitespace collapsed, accepted


def test_capture_contact_valid_email():
    value, error = _capture_contact("email", "ada@example.com")
    assert value == "ada@example.com" and error is None


def test_capture_contact_invalid_email_reasks():
    value, error = _capture_contact("email", "not-an-email")
    assert value is None and "valid email" in error  # no value stored; a re-ask is returned


def test_capture_contact_blank_reasks():
    value, error = _capture_contact("name", "   ")
    assert value is None and error  # a question is returned, nothing stored


def test_order_create_accepts_contact_fields():
    data = OrderCreate(
        customer_phone="16500009999",
        customer_name="Ada",
        customer_email="ada@example.com",
        customer_alt_phone="+1 650 555 1234",
        fulfillment="pickup",
        items=[{"product_id": "453aa17e-8f07-4751-9784-c5982f440ba5", "quantity": 1}],
    )
    assert str(data.customer_email) == "ada@example.com"
    assert data.customer_alt_phone == "+1 650 555 1234"


def test_order_create_rejects_bad_contact_email():
    with pytest.raises(ValidationError):
        OrderCreate(
            customer_phone="16500009999",
            customer_email="nope",
            fulfillment="pickup",
            items=[{"product_id": "453aa17e-8f07-4751-9784-c5982f440ba5", "quantity": 1}],
        )
