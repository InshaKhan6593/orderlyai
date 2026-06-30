"""Agent runtime behavior that is independent of the real LLM."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agent.runtime import _capture_checkout, _render_zone_list, run_turn
from app.agent.state import merge_pending_updates
from app.agent.schemas import (
    BTN_CANCEL,
    BTN_CONFIRM,
    BTN_EDIT,
    BTN_FUL_DELIVERY,
    BTN_UPDATE_CONFIRM,
    BTN_UPDATE_KEEP,
    ROW_ZONE_PREFIX,
    AgentReply,
    ButtonsMessage,
    ListMessage,
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
    # The deterministic summary in the button body is the single source of truth, so the model's
    # own text is DROPPED (it otherwise re-summarized the order -> the customer saw it twice).
    assert all(not isinstance(m, TextMessage) for m in result.messages)
    assert "Please confirm your order." not in buttons[0].body


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
def test_capture_checkout_update_confirm_applies_new_value():
    # The customer tapped Update on a proposed name change → the new value is applied to state
    # and the pending queue cleared; place_order is re-triggered.
    overrides, early, new_text = _capture_checkout(
        {"pending_updates": [{"field": "name", "value": "Ahmer Khan"}],
         "customer_name": "Insha Khan"},
        text="Update", reply_id=BTN_UPDATE_CONFIRM, confirmed=False,
    )
    assert early is None
    assert overrides["customer_name"] == "Ahmer Khan"
    assert overrides["pending_updates"] is None  # cleared (the reducer resets it to [])
    assert new_text is not None  # re-triggers checkout


def test_capture_checkout_applies_multiple_updates_on_one_tap():
    # The customer asked to change email AND alternate phone in one message → both proposals were
    # queued (update_detail appends), and a single Update tap applies them together.
    overrides, early, new_text = _capture_checkout(
        {"pending_updates": [
            {"field": "email", "value": "a@b.com"},
            {"field": "alternate_phone", "value": "03001234567"},
        ]},
        text="Update", reply_id=BTN_UPDATE_CONFIRM, confirmed=False,
    )
    assert early is None
    assert overrides["customer_email"] == "a@b.com"
    assert overrides["customer_alt_phone"] == "03001234567"
    assert overrides["pending_updates"] is None
    assert new_text is not None


def test_capture_checkout_update_keep_discards_change():
    overrides, early, new_text = _capture_checkout(
        {"pending_updates": [{"field": "name", "value": "Ahmer Khan"}],
         "customer_name": "Insha Khan"},
        text="Keep current", reply_id=BTN_UPDATE_KEEP, confirmed=False,
    )
    assert early is None
    assert "customer_name" not in overrides       # saved name untouched
    assert overrides["pending_updates"] is None


def test_capture_checkout_update_street_address_keeps_the_area():
    # Changing the STREET address stays within the same area, so it must NOT clear the zone.
    overrides, _early, _new = _capture_checkout(
        {"pending_updates": [{"field": "address", "value": "House 7, Street 10"}],
         "address": "House 5", "zone_id": "z1", "zone_serviceable": True},
        text="Update", reply_id=BTN_UPDATE_CONFIRM, confirmed=False,
    )
    assert overrides["address"] == "House 7, Street 10"
    assert "zone_id" not in overrides            # area untouched
    assert "zone_serviceable" not in overrides


def test_capture_checkout_update_area_reresolves_zone_and_reasks_street():
    # Changing the AREA queues the new area for matching (zone_query), clears the old zone, and
    # clears the street address so it's re-asked within the new area.
    overrides, _early, new_text = _capture_checkout(
        {"pending_updates": [{"field": "area", "value": "Defence"}],
         "address": "House 5", "zone_id": "z1", "zone_serviceable": True},
        text="Update", reply_id=BTN_UPDATE_CONFIRM, confirmed=False,
    )
    assert overrides["zone_query"] == "Defence"  # place_order matches it against the real zones
    assert overrides["zone_id"] is None
    assert overrides["zone_serviceable"] is None
    assert overrides["address"] is None          # street re-asked for the new area
    assert new_text is not None                  # re-triggers checkout


def test_capture_checkout_update_area_and_address_keeps_the_given_street():
    # If the customer gives BOTH a new area and a new street in one message, keep their street
    # (don't clear it) — only the area triggers the zone re-check.
    overrides, _early, _new = _capture_checkout(
        {"pending_updates": [
            {"field": "area", "value": "Defence"},
            {"field": "address", "value": "House 9, Street 2"},
        ]},
        text="Update", reply_id=BTN_UPDATE_CONFIRM, confirmed=False,
    )
    assert overrides["zone_query"] == "Defence"
    assert overrides["address"] == "House 9, Street 2"  # the street they gave is kept
    assert overrides["zone_id"] is None


def test_merge_pending_updates_appends_dedupes_and_resets():
    # The state reducer: appends across calls, a later same-field proposal supersedes the earlier
    # one, and a None update clears the queue.
    first = merge_pending_updates([], [{"field": "email", "value": "a@b.com"}])
    second = merge_pending_updates(first, [{"field": "alternate_phone", "value": "0300"}])
    assert second == [
        {"field": "email", "value": "a@b.com"},
        {"field": "alternate_phone", "value": "0300"},
    ]
    deduped = merge_pending_updates(second, [{"field": "email", "value": "c@d.com"}])
    assert deduped == [
        {"field": "email", "value": "c@d.com"},
        {"field": "alternate_phone", "value": "0300"},
    ]
    assert merge_pending_updates(second, None) == []


def test_capture_checkout_nothing_pending_is_noop():
    assert _capture_checkout({}, text="hi", reply_id=None, confirmed=False) == (None, None, None)


@pytest.mark.asyncio
async def test_run_turn_captures_pending_checkout_name_in_code():
    # While we're collecting the name, a typed reply is validated + stored by run_turn (not the
    # model): the captured value is injected into state and the pending flag cleared before the
    # LLM turn runs.
    reply = AgentReply(messages=[TextMessage(kind="text", body="ok")])
    agent = _FakeAgent(_answered(reply), state_values={"pending_checkout_field": "name"})

    await run_turn(agent, business_id=_BID, customer_phone=_PHONE, thread_id=_THREAD, text="Ada Khan")

    assert agent.invoked is not None  # the LLM turn proceeded
    assert agent.invoked["customer_name"] == "Ada Khan"  # code stored it
    assert agent.invoked["pending_checkout_field"] is None  # and cleared the prompt


@pytest.mark.asyncio
async def test_run_turn_captures_fulfillment_from_button_tap():
    # The Delivery/Pickup choice is captured deterministically from the tap; the value lands in
    # state and the slot is cleared before the model re-runs place_order.
    reply = AgentReply(messages=[TextMessage(kind="text", body="ok")])
    agent = _FakeAgent(_answered(reply), state_values={"pending_checkout_field": "fulfillment"})

    await run_turn(
        agent, business_id=_BID, customer_phone=_PHONE, thread_id=_THREAD,
        text="Delivery", reply_id="ful_delivery",
    )

    assert agent.invoked is not None
    assert agent.invoked["fulfillment"] == "delivery"
    assert agent.invoked["pending_checkout_field"] is None


@pytest.mark.asyncio
async def test_run_turn_captures_street_address_without_touching_the_chosen_area():
    # The delivery AREA is chosen first (zone slot); capturing the street address must NOT clear it
    # — the address is within the already-confirmed area, so there's no re-check to force.
    reply = AgentReply(messages=[TextMessage(kind="text", body="ok")])
    agent = _FakeAgent(_answered(reply), state_values={"pending_checkout_field": "address"})

    await run_turn(
        agent, business_id=_BID, customer_phone=_PHONE, thread_id=_THREAD, text="House 5, Garden East"
    )

    assert agent.invoked is not None
    assert agent.invoked["address"] == "House 5, Garden East"
    assert "zone_serviceable" not in agent.invoked  # the chosen area is left intact
    assert agent.invoked["pending_checkout_field"] is None


@pytest.mark.asyncio
async def test_run_turn_renders_contact_question_when_place_order_asks():
    # place_order set pending_checkout_field → run_turn asks a fixed, code-rendered question
    # (replacing whatever the model wrote).
    reply = AgentReply(messages=[TextMessage(kind="text", body="(model text)")])
    agent = _FakeAgent(_answered(reply, pending_checkout_field="name"))

    result = await run_turn(
        agent, business_id=_BID, customer_phone=_PHONE, thread_id=_THREAD, text="place my order"
    )

    assert len(result.messages) == 1
    assert "name" in result.messages[0].body.lower()


@pytest.mark.asyncio
async def test_run_turn_renders_fulfillment_buttons_when_place_order_asks():
    # place_order set pending_checkout_field="fulfillment" → run_turn shows deterministic
    # Delivery/Pickup buttons (not the model's text).
    reply = AgentReply(messages=[TextMessage(kind="text", body="(model text)")])
    agent = _FakeAgent(_answered(reply, pending_checkout_field="fulfillment"))

    result = await run_turn(
        agent, business_id=_BID, customer_phone=_PHONE, thread_id=_THREAD, text="order"
    )

    btns = [m for m in result.messages if isinstance(m, ButtonsMessage)]
    assert len(btns) == 1
    assert {b.id for b in btns[0].buttons} == {BTN_FUL_DELIVERY, "ful_pickup"}


@pytest.mark.asyncio
async def test_run_turn_renders_update_confirm_when_detail_change_proposed():
    # The model relayed a name change via update_detail → run_turn asks the customer to confirm
    # with deterministic Update / Keep buttons (the value is applied only on the tap).
    reply = AgentReply(messages=[TextMessage(kind="text", body="(model text)")])
    agent = _FakeAgent(
        _answered(reply, pending_updates=[{"field": "name", "value": "Ahmer Khan"}],
                  customer_name="Insha Khan")
    )

    result = await run_turn(
        agent, business_id=_BID, customer_phone=_PHONE, thread_id=_THREAD, text="change my name"
    )

    btns = [m for m in result.messages if isinstance(m, ButtonsMessage)]
    assert len(btns) == 1
    assert {b.id for b in btns[0].buttons} == {BTN_UPDATE_CONFIRM, BTN_UPDATE_KEEP}
    assert "Ahmer Khan" in btns[0].body


@pytest.mark.asyncio
async def test_run_turn_renders_one_combined_confirm_for_multiple_updates():
    # The customer asked to change email AND alternate phone in one message → both were queued and
    # run_turn shows a SINGLE confirm listing both, with one Update tap to apply them together.
    reply = AgentReply(messages=[TextMessage(kind="text", body="(model text)")])
    agent = _FakeAgent(
        _answered(reply, pending_updates=[
            {"field": "email", "value": "a@b.com"},
            {"field": "alternate_phone", "value": "03001234567"},
        ])
    )

    result = await run_turn(
        agent, business_id=_BID, customer_phone=_PHONE, thread_id=_THREAD,
        text="change my email and my alternate number",
    )

    btns = [m for m in result.messages if isinstance(m, ButtonsMessage)]
    assert len(btns) == 1
    assert "a@b.com" in btns[0].body
    assert "03001234567" in btns[0].body
    assert {b.id for b in btns[0].buttons} == {BTN_UPDATE_CONFIRM, BTN_UPDATE_KEEP}


@pytest.mark.asyncio
async def test_run_turn_confirm_for_area_update_says_delivery_area():
    # "change my zone to Defence" → the confirm must talk about the delivery AREA, not the address.
    reply = AgentReply(messages=[TextMessage(kind="text", body="(model text)")])
    agent = _FakeAgent(_answered(reply, pending_updates=[{"field": "area", "value": "Defence"}]))

    result = await run_turn(
        agent, business_id=_BID, customer_phone=_PHONE, thread_id=_THREAD,
        text="change my area to Defence",
    )

    btns = [m for m in result.messages if isinstance(m, ButtonsMessage)]
    assert len(btns) == 1
    assert "delivery area" in btns[0].body.lower()
    assert "Defence" in btns[0].body
    assert {b.id for b in btns[0].buttons} == {BTN_UPDATE_CONFIRM, BTN_UPDATE_KEEP}


@pytest.mark.asyncio
async def test_run_turn_does_not_capture_a_button_tap_as_a_contact_value():
    # A list/button tap (reply_id set) must never be mistaken for a typed field answer.
    reply = AgentReply(messages=[TextMessage(kind="text", body="ok")])
    agent = _FakeAgent(_answered(reply), state_values={"pending_checkout_field": "name"})

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
    agent = _FakeAgent(_answered(reply), state_values={"pending_checkout_field": "name"})

    await run_turn(agent, business_id=_BID, customer_phone=_PHONE, thread_id=_THREAD, text="cancel")

    assert agent.invoked is not None
    assert agent.invoked["pending_checkout_field"] is None  # prompt dropped
    assert "customer_name" not in agent.invoked  # nothing stored as the name


# --------------------------------------------------------------------------- #
# Deterministic delivery-AREA (zone) selection — fail-fast, exact pick, no guessing
# --------------------------------------------------------------------------- #
_ZONE_CHOICES = [
    {"id": f"{ROW_ZONE_PREFIX}11111111-1111-1111-1111-111111111111", "title": "Gulberg",
     "description": "Delivery 80 PKR · ~30 min"},
    {"id": f"{ROW_ZONE_PREFIX}22222222-2222-2222-2222-222222222222", "title": "DHA",
     "description": "Delivery 120 PKR · ~40 min"},
]


def test_render_zone_list_builds_a_tappable_area_list():
    reply = _render_zone_list(_ZONE_CHOICES, "Which area should we deliver to? Tap your area below.")
    assert len(reply.messages) == 1
    msg = reply.messages[0]
    assert isinstance(msg, ListMessage)
    rows = [r for s in msg.sections for r in s.rows]
    assert [r.title for r in rows] == ["Gulberg", "DHA"]
    assert all(r.id.startswith(ROW_ZONE_PREFIX) for r in rows)  # each row is a real zone id
    assert "Which area" in msg.body


def test_capture_checkout_zone_tap_selects_exact_zone():
    # A tapped area is captured exactly (its id), serviceability confirmed, slot cleared.
    overrides, early, new_text = _capture_checkout(
        {"pending_checkout_field": "zone", "zone_choices": _ZONE_CHOICES},
        text="", reply_id=_ZONE_CHOICES[0]["id"], confirmed=False,
    )
    assert early is None
    assert overrides["zone_id"] == "11111111-1111-1111-1111-111111111111"
    assert overrides["zone_serviceable"] is True
    assert overrides["pending_checkout_field"] is None
    assert new_text is not None  # re-triggers checkout


def test_capture_checkout_zone_typed_area_is_queued_for_matching():
    # A typed area is queued (zone_query); place_order matches it against the zones, not the model.
    overrides, early, _new = _capture_checkout(
        {"pending_checkout_field": "zone", "zone_choices": _ZONE_CHOICES},
        text="Gulberg block 5", reply_id=None, confirmed=False,
    )
    assert early is None
    assert overrides["zone_query"] == "Gulberg block 5"
    assert overrides["pending_checkout_field"] is None


def test_capture_checkout_zone_pickup_bails_to_pickup():
    # While picking an area the customer can switch to pickup; the zone state is cleared.
    overrides, early, _new = _capture_checkout(
        {"pending_checkout_field": "zone", "zone_choices": _ZONE_CHOICES},
        text="pickup", reply_id=None, confirmed=False,
    )
    assert early is None
    assert overrides["fulfillment"] == "pickup"
    assert overrides["zone_id"] is None
    assert overrides["pending_checkout_field"] is None


def test_capture_checkout_zone_empty_reply_reshows_the_list():
    overrides, early, _new = _capture_checkout(
        {"pending_checkout_field": "zone", "zone_choices": _ZONE_CHOICES,
         "zone_prompt": "Which area should we deliver to?"},
        text="", reply_id=None, confirmed=False,
    )
    assert overrides is None
    assert isinstance(early.messages[0], ListMessage)  # re-asks with the same area list


@pytest.mark.asyncio
async def test_run_turn_renders_zone_list_when_place_order_asks():
    # place_order set pending_checkout_field="zone" with the area rows → run_turn shows the list.
    reply = AgentReply(messages=[TextMessage(kind="text", body="(model text)")])
    agent = _FakeAgent(
        _answered(reply, pending_checkout_field="zone", zone_choices=_ZONE_CHOICES,
                  zone_prompt="Which area should we deliver to? Tap your area below.")
    )

    result = await run_turn(
        agent, business_id=_BID, customer_phone=_PHONE, thread_id=_THREAD, text="I want delivery"
    )

    assert isinstance(result.messages[0], ListMessage)
    titles = [r.title for s in result.messages[0].sections for r in s.rows]
    assert "Gulberg" in titles


@pytest.mark.asyncio
async def test_run_turn_asks_area_as_text_when_too_many_zones_for_a_list():
    # With more zones than a WhatsApp list can hold, place_order leaves zone_choices None and passes
    # a text prompt; run_turn asks for the area as plain text instead of an (unsendable) list.
    reply = AgentReply(messages=[TextMessage(kind="text", body="(model text)")])
    agent = _FakeAgent(
        _answered(reply, pending_checkout_field="zone", zone_choices=None,
                  zone_prompt="What area or neighbourhood should we deliver to?")
    )

    result = await run_turn(
        agent, business_id=_BID, customer_phone=_PHONE, thread_id=_THREAD, text="deliver please"
    )

    assert len(result.messages) == 1
    assert result.messages[0].kind == "text"
    assert "area" in result.messages[0].body.lower()
