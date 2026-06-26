"""Agent runtime behavior that is independent of the real LLM."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agent.runtime import run_turn
from app.agent.schemas import (
    BTN_CANCEL,
    BTN_CONFIRM,
    BTN_EDIT,
    AgentReply,
    ButtonsMessage,
    ReplyButton,
    TextMessage,
)

_BID = "a5bda699-9834-481e-ba99-b0d39161fac4"
_PHONE = "923241452724"
_THREAD = f"{_BID}:{_PHONE}"


def _answered(structured_response, **extra):
    """A fake agent result whose structured response is for the latest user turn."""
    return {
        "messages": [
            {"type": "human", "content": "place my order"},
            {"type": "tool", "name": "AgentReply",
             "content": "Returning structured response: ..."},
        ],
        "structured_response": structured_response,
        **extra,
    }


class _FakeAgent:
    def __init__(self, result: dict, state_values: dict | None = None):
        self.result = result
        self.state_values = state_values or {}
        self.invoked: dict | None = None  # the input payload of the last ainvoke (None if not called)

    async def aget_state(self, config):
        return SimpleNamespace(values=self.state_values)

    async def ainvoke(self, payload, *args, **kwargs):
        self.invoked = payload
        return self.result


@pytest.mark.asyncio
async def test_run_turn_rejects_stale_structured_response_after_latest_user_message():
    stale = AgentReply(messages=[TextMessage(kind="text", body="old greeting")])
    agent = _FakeAgent(
        {
            "messages": [
                {"type": "human", "content": "Hi"},
                {
                    "type": "tool",
                    "name": "AgentReply",
                    "content": "Returning structured response: old greeting",
                },
                {"type": "human", "content": "your menu?"},
                {
                    "type": "tool",
                    "name": "AgentReply",
                    "content": "Error: Failed to parse structured output for tool 'AgentReply'",
                },
            ],
            "structured_response": stale,
        }
    )

    with pytest.raises(RuntimeError, match="latest turn"):
        await run_turn(
            agent,
            business_id="a5bda699-9834-481e-ba99-b0d39161fac4",
            customer_phone="923241452724",
            thread_id="a5bda699-9834-481e-ba99-b0d39161fac4:923241452724",
            text="your menu?",
        )


@pytest.mark.asyncio
async def test_run_turn_returns_structured_response_from_latest_user_message():
    reply = AgentReply(messages=[TextMessage(kind="text", body="current menu")])
    agent = _FakeAgent(
        {
            "messages": [
                {"type": "human", "content": "your menu?"},
                {
                    "type": "tool",
                    "name": "AgentReply",
                    "content": "Returning structured response: current menu",
                },
            ],
            "structured_response": reply,
        }
    )

    result = await run_turn(
        agent,
        business_id="a5bda699-9834-481e-ba99-b0d39161fac4",
        customer_phone="923241452724",
        thread_id="a5bda699-9834-481e-ba99-b0d39161fac4:923241452724",
        text="your menu?",
    )

    assert result == reply


@pytest.mark.asyncio
async def test_run_turn_injects_confirm_buttons_when_awaiting_confirm():
    # place_order signalled awaiting_confirm but the model only sent text → run_turn must add
    # the real [Confirm][Edit][Cancel] buttons (with the priced total) so the customer has
    # something to tap. This is the fix for the dead-end where buttons never appeared.
    reply = AgentReply(messages=[TextMessage(kind="text", body="Please confirm your order.")])
    agent = _FakeAgent(
        _answered(reply, awaiting_confirm=True, confirm_summary="Total: 850 PKR")
    )

    result = await run_turn(
        agent, business_id=_BID, customer_phone=_PHONE, thread_id=_THREAD, text="place my order"
    )

    buttons = [m for m in result.messages if isinstance(m, ButtonsMessage)]
    assert len(buttons) == 1
    assert [b.id for b in buttons[0].buttons] == [BTN_CONFIRM, BTN_EDIT, BTN_CANCEL]
    assert "850 PKR" in buttons[0].body  # the server-priced total travels with the buttons
    # the model's own text is preserved alongside the injected buttons
    assert any(
        isinstance(m, TextMessage) and m.body == "Please confirm your order."
        for m in result.messages
    )


@pytest.mark.asyncio
async def test_run_turn_does_not_duplicate_model_confirm_buttons():
    # If the model already sent the canonical confirm buttons, run_turn leaves the reply alone.
    model_buttons = ButtonsMessage(
        kind="buttons",
        body="Total: 850 PKR. Confirm?",
        buttons=[
            ReplyButton(id=BTN_CONFIRM, title="Confirm"),
            ReplyButton(id=BTN_EDIT, title="Edit"),
            ReplyButton(id=BTN_CANCEL, title="Cancel"),
        ],
    )
    reply = AgentReply(messages=[model_buttons])
    agent = _FakeAgent(
        _answered(reply, awaiting_confirm=True, confirm_summary="Total: 850 PKR")
    )

    result = await run_turn(
        agent, business_id=_BID, customer_phone=_PHONE, thread_id=_THREAD, text="place my order"
    )

    assert result is reply  # untouched
    assert len([m for m in result.messages if isinstance(m, ButtonsMessage)]) == 1


@pytest.mark.asyncio
async def test_run_turn_leaves_reply_untouched_when_not_awaiting_confirm():
    # No awaiting_confirm signal (normal browsing turn) → no buttons are injected.
    reply = AgentReply(messages=[TextMessage(kind="text", body="Here's our menu.")])
    agent = _FakeAgent(_answered(reply))

    result = await run_turn(
        agent, business_id=_BID, customer_phone=_PHONE, thread_id=_THREAD, text="menu?"
    )

    assert result is reply
    assert not any(isinstance(m, ButtonsMessage) for m in result.messages)


@pytest.mark.asyncio
async def test_run_turn_sends_deterministic_placed_message_alone():
    # place_order committed the order and set order_placed_summary. Even though the model ALSO
    # composed its own summary, run_turn must send ONLY the deterministic confirmation — the
    # server-authoritative order number/total, never doubled (the no-double-summary fix).
    placed = "Your order is confirmed!\n\nOrder #42\nTotal: 850 PKR (cash on pickup)"
    model_reply = AgentReply(
        messages=[TextMessage(kind="text", body="Order #42 placed, total 850 PKR. Thank you!")]
    )
    agent = _FakeAgent(_answered(model_reply, order_placed_summary=placed))

    result = await run_turn(
        agent, business_id=_BID, customer_phone=_PHONE, thread_id=_THREAD, text="Confirm the order."
    )

    assert len(result.messages) == 1
    assert isinstance(result.messages[0], TextMessage)
    assert result.messages[0].body == placed  # the deterministic message verbatim
    # the model's own summary is dropped (no second summary of the same order)
    assert all("Thank you!" not in m.body for m in result.messages if isinstance(m, TextMessage))


@pytest.mark.asyncio
async def test_run_turn_sends_placed_message_even_if_model_output_stale():
    # The order is committed, so the customer MUST be told — even if the model failed to produce
    # a fresh structured reply for this turn. run_turn sends the placed summary and does not raise.
    placed = "Your order is confirmed!\n\nOrder #7\nTotal: 500 PKR (cash on delivery)"
    stale = AgentReply(messages=[TextMessage(kind="text", body="old")])
    agent = _FakeAgent(
        {
            "messages": [
                {"type": "human", "content": "Confirm the order."},
                {
                    "type": "tool",
                    "name": "AgentReply",
                    "content": "Error: Failed to parse structured output for tool 'AgentReply'",
                },
            ],
            "structured_response": stale,
            "order_placed_summary": placed,
        }
    )

    result = await run_turn(
        agent, business_id=_BID, customer_phone=_PHONE, thread_id=_THREAD, text="Confirm the order."
    )

    assert len(result.messages) == 1
    assert result.messages[0].body == placed


# --------------------------------------------------------------------------- #
# Deterministic contact collection (code captures the value; the model never sets it)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_run_turn_captures_pending_contact_field_in_code():
    # While we're collecting the name, a typed reply is validated + stored by run_turn (not the
    # model): the captured value is injected into state and the pending flag cleared before the
    # LLM turn runs.
    reply = AgentReply(messages=[TextMessage(kind="text", body="ok")])
    agent = _FakeAgent(_answered(reply), state_values={"pending_contact_field": "name"})

    await run_turn(agent, business_id=_BID, customer_phone=_PHONE, thread_id=_THREAD, text="Ada Khan")

    assert agent.invoked is not None  # the LLM turn proceeded
    assert agent.invoked["customer_name"] == "Ada Khan"  # code stored it
    assert agent.invoked["pending_contact_field"] is None  # and cleared the prompt


@pytest.mark.asyncio
async def test_run_turn_reasks_invalid_contact_without_calling_model():
    agent = _FakeAgent(
        _answered(AgentReply(messages=[TextMessage(kind="text", body="x")])),
        state_values={"pending_contact_field": "email"},
    )

    result = await run_turn(
        agent, business_id=_BID, customer_phone=_PHONE, thread_id=_THREAD, text="not-an-email"
    )

    assert agent.invoked is None  # model NOT called — deterministic re-ask
    assert len(result.messages) == 1
    assert "valid email" in result.messages[0].body


@pytest.mark.asyncio
async def test_run_turn_renders_contact_question_when_place_order_asks():
    # place_order set pending_contact_field → run_turn asks a fixed, code-rendered question
    # (replacing whatever the model wrote).
    reply = AgentReply(messages=[TextMessage(kind="text", body="(model text)")])
    agent = _FakeAgent(_answered(reply, pending_contact_field="name"))

    result = await run_turn(
        agent, business_id=_BID, customer_phone=_PHONE, thread_id=_THREAD, text="place my order"
    )

    assert len(result.messages) == 1
    assert "name" in result.messages[0].body.lower()


@pytest.mark.asyncio
async def test_run_turn_does_not_capture_a_button_tap_as_a_contact_value():
    # A list/button tap (reply_id set) must never be mistaken for a typed field answer.
    reply = AgentReply(messages=[TextMessage(kind="text", body="ok")])
    agent = _FakeAgent(_answered(reply), state_values={"pending_contact_field": "name"})

    await run_turn(
        agent, business_id=_BID, customer_phone=_PHONE, thread_id=_THREAD,
        text="Tell me about that item.", reply_id="product:abc",
    )

    assert agent.invoked is not None
    assert "customer_name" not in agent.invoked  # capture skipped — it was a tap


@pytest.mark.asyncio
async def test_run_turn_abort_word_drops_contact_prompt_without_storing_it():
    # If the customer backs out mid-collection, "cancel" is NOT stored as their name.
    reply = AgentReply(messages=[TextMessage(kind="text", body="ok")])
    agent = _FakeAgent(_answered(reply), state_values={"pending_contact_field": "name"})

    await run_turn(agent, business_id=_BID, customer_phone=_PHONE, thread_id=_THREAD, text="cancel")

    assert agent.invoked is not None
    assert agent.invoked["pending_contact_field"] is None  # prompt dropped
    assert "customer_name" not in agent.invoked  # nothing stored as the name
