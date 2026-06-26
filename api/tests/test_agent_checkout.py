"""Checkout contact details: validation, deterministic capture, the placed message.

These are pure unit tests (no DB / no LLM) covering the pieces that make place_order
production-grade: the validated ContactDetails schema, the deterministic code-side capture of a
typed contact reply, and the server-authoritative "order placed" confirmation text.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.agent.runtime import _capture_contact
from app.agent.tools import TOOLS, _format_placed
from app.schemas.customer import ContactDetails
from app.schemas.order import OrderCreate


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
def test_format_placed_pickup_has_order_number_total_and_name():
    msg = _format_placed(42, Decimal("850.00"), "pickup", "PKR", "Ada", None)
    assert "#42" in msg
    assert "850.00 PKR" in msg
    assert "Ada" in msg
    assert "pickup" in msg


def test_format_placed_delivery_includes_address():
    msg = _format_placed(7, Decimal("560.00"), "delivery", "PKR", "Ada", "12 Park Lane")
    assert "#7" in msg
    assert "12 Park Lane" in msg
    assert "delivery" in msg


def test_format_placed_without_name_still_valid():
    msg = _format_placed(1, Decimal("100"), "pickup", "PKR", None, None)
    assert "#1" in msg and "100 PKR" in msg  # no crash, still confirms the order


# --------------------------------------------------------------------------- #
# Tool wiring + order schema threading
# --------------------------------------------------------------------------- #
def test_set_contact_details_tool_not_exposed():
    # Contact details are captured deterministically in code (run_turn), never set by the model,
    # so there must be NO LLM-callable set_contact_details tool.
    assert "set_contact_details" not in {t.name for t in TOOLS}


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
