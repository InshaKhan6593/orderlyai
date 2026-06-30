"""Durable inbound worker: dedup, coalescing, ordering, retries, notifications, parsing.

These exercise the production-hardening pipeline directly against the test DB (the webhook
end-to-end path is covered in test_whatsapp_connection.py). Worker calls are async; we drive
them with ``asyncio.run`` and point the worker/notification sessions at the test DB.
"""
from __future__ import annotations

import asyncio
import uuid

from conftest import _TestSession
from app.agent.schemas import AgentReply, TextMessage
from app.core.config import settings
from app.services import notification_service, whatsapp_service, whatsapp_worker


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _save_connection(client, headers, business_id, pnid):
    r = client.put(
        f"/api/v1/businesses/{business_id}/whatsapp-connection",
        json={
            "mode": "test",
            "waba_id": "123456789012345",
            "phone_number_id": pnid,
            "access_token": "EAAG-inbound-token",
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text


def _text_payload(pnid, sender, body, msg_id, name="Ada"):
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": pnid},
                            "contacts": [{"wa_id": sender, "profile": {"name": name}}],
                            "messages": [
                                {"from": sender, "id": msg_id, "type": "text", "text": {"body": body}}
                            ],
                        },
                    }
                ]
            }
        ],
    }


def _confirm_payload(pnid, sender, msg_id):
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": pnid},
                            "messages": [
                                {
                                    "from": sender,
                                    "id": msg_id,
                                    "type": "interactive",
                                    "interactive": {
                                        "type": "button_reply",
                                        "button_reply": {"id": "confirm_order", "title": "Confirm"},
                                    },
                                }
                            ],
                        },
                    }
                ]
            }
        ],
    }


def _parsed(payload):
    return whatsapp_service.parse_incoming_messages(payload)[0]


def _stub_pipeline(monkeypatch, *, run_turn, send_payloads):
    monkeypatch.setattr(whatsapp_worker, "SessionLocal", _TestSession)
    monkeypatch.setattr("app.agent.runtime.get_whatsapp_agent", lambda: object())
    monkeypatch.setattr("app.agent.runtime.run_turn", run_turn)
    monkeypatch.setattr(whatsapp_service, "send_payloads", send_payloads)

    async def _noop_mark_read(**kwargs):
        return True

    monkeypatch.setattr(whatsapp_service, "mark_read", _noop_mark_read)


# --------------------------------------------------------------------------- #
# agent_input mapping (pure)
# --------------------------------------------------------------------------- #
def test_agent_input_location_and_media():
    ai = whatsapp_worker.agent_input
    assert ai({"type": "location", "text": "12 Main St", "reply_id": ""}) == (
        "My delivery address: 12 Main St",
        False,
    )
    pin = ai({"type": "location", "text": "", "reply_id": "", "latitude": 1.0, "longitude": 2.0})
    assert pin[1] is False and "1.0" in pin[0] and "delivery area" in pin[0]
    # Unsupported media → a note asking for text (so the agent replies gracefully).
    note, confirmed = ai({"type": "image", "text": "", "reply_id": ""})
    assert confirmed is False and "can't open" in note
    # Confirm button is the only thing that flips confirmed=True.
    assert ai({"type": "interactive", "reply_id": "confirm_order", "text": "Confirm"}) == (
        "Confirm the order.",
        True,
    )
    # A category-dropdown tap (id "category:<name>", title = the category) routes as a plain
    # browse for that category — the row title is what the agent acts on.
    assert ai(
        {"type": "interactive", "reply_id": "category:Burgers", "text": "Burgers"}
    ) == ("Burgers", False)
    # A product-row tap carries its title text through for the agent to describe the item.
    assert ai(
        {"type": "interactive", "reply_id": "product:abc-123", "text": "Veg Burger"}
    ) == ("Veg Burger", False)


# --------------------------------------------------------------------------- #
# Dedup + parsing
# --------------------------------------------------------------------------- #
def test_persist_dedup(client, business):
    headers, business_id = business
    pnid = str(uuid.uuid4().int)[:15]
    _save_connection(client, headers, business_id, pnid)
    sender = "16500000001"
    parsed = _parsed(_text_payload(pnid, sender, "hi", "wamid.A"))

    async def _run():
        async with _TestSession() as db:
            first = await whatsapp_worker.persist_inbound(db, parsed)
            dup = await whatsapp_worker.persist_inbound(db, parsed)  # same message_id
            return first, dup

    first, dup = asyncio.run(_run())
    assert first == f"{business_id}:{sender}"
    assert dup is None  # Meta retry deduped at the DB


def test_parse_collects_all_messages():
    payload = {
        "entry": [
            {"changes": [{"value": {"metadata": {"phone_number_id": "p"},
                "messages": [{"from": "u", "id": "m1", "type": "text", "text": {"body": "one"}}]}}]},
            {"changes": [{"value": {"metadata": {"phone_number_id": "p"},
                "messages": [{"from": "u", "id": "m2", "type": "text", "text": {"body": "two"}}]}}]},
        ]
    }
    msgs = whatsapp_service.parse_incoming_messages(payload)
    assert [m["message_id"] for m in msgs] == ["m1", "m2"]


# --------------------------------------------------------------------------- #
# Coalescing + ordering
# --------------------------------------------------------------------------- #
def test_back_to_back_texts_are_coalesced(client, business, monkeypatch):
    headers, business_id = business
    pnid = str(uuid.uuid4().int)[:15]
    _save_connection(client, headers, business_id, pnid)
    sender = "16500000002"

    seen_texts: list[str] = []
    sends: list = []

    async def fake_run_turn(agent, *, business_id, customer_phone, thread_id, text, confirmed=False, reply_id=None):
        seen_texts.append(text)
        return AgentReply(messages=[TextMessage(kind="text", body="ok")])

    async def fake_send(*, phone_number_id, access_token, payloads):
        sends.append(payloads)
        return whatsapp_service.SendResult(ok=True)

    _stub_pipeline(monkeypatch, run_turn=fake_run_turn, send_payloads=fake_send)

    async def _run():
        async with _TestSession() as db:
            await whatsapp_worker.persist_inbound(db, _parsed(_text_payload(pnid, sender, "I want", "wamid.1")))
            await whatsapp_worker.persist_inbound(db, _parsed(_text_payload(pnid, sender, "a burger", "wamid.2")))
        await whatsapp_worker.drain_conversation(f"{business_id}:{sender}")

    asyncio.run(_run())
    # Two quick texts → ONE agent turn with the combined text → one reply (not two fragments).
    assert seen_texts == ["I want\na burger"]
    assert len(sends) == 1


def test_confirm_tap_is_its_own_turn(client, business, monkeypatch):
    headers, business_id = business
    pnid = str(uuid.uuid4().int)[:15]
    _save_connection(client, headers, business_id, pnid)
    sender = "16500000003"

    calls: list[tuple[str, bool]] = []

    async def fake_run_turn(agent, *, business_id, customer_phone, thread_id, text, confirmed=False, reply_id=None):
        calls.append((text, confirmed))
        return AgentReply(messages=[TextMessage(kind="text", body="ok")])

    async def fake_send(*, phone_number_id, access_token, payloads):
        return whatsapp_service.SendResult(ok=True)

    _stub_pipeline(monkeypatch, run_turn=fake_run_turn, send_payloads=fake_send)

    async def _run():
        async with _TestSession() as db:
            await whatsapp_worker.persist_inbound(db, _parsed(_text_payload(pnid, sender, "burger pls", "wamid.t")))
            await whatsapp_worker.persist_inbound(db, _parsed(_confirm_payload(pnid, sender, "wamid.c")))
        await whatsapp_worker.drain_conversation(f"{business_id}:{sender}")

    asyncio.run(_run())
    # Text turn first (confirmed False), then the confirm tap as a separate turn (confirmed True).
    assert calls == [("burger pls", False), ("Confirm the order.", True)]


# --------------------------------------------------------------------------- #
# Retry safety: a failed send re-delivers the SAME reply without re-running the agent
# --------------------------------------------------------------------------- #
def test_failed_send_resends_without_rerunning_agent(client, business, monkeypatch):
    headers, business_id = business
    pnid = str(uuid.uuid4().int)[:15]
    _save_connection(client, headers, business_id, pnid)
    sender = "16500000004"

    run_calls = {"n": 0}
    send_calls = {"n": 0}

    async def fake_run_turn(agent, *, business_id, customer_phone, thread_id, text, confirmed=False, reply_id=None):
        run_calls["n"] += 1
        return AgentReply(messages=[TextMessage(kind="text", body="reply")])

    async def fake_send(*, phone_number_id, access_token, payloads):
        send_calls["n"] += 1
        if send_calls["n"] == 1:
            return whatsapp_service.SendResult(ok=False, retryable=True, status_code=503)
        return whatsapp_service.SendResult(ok=True)

    _stub_pipeline(monkeypatch, run_turn=fake_run_turn, send_payloads=fake_send)
    thread = f"{business_id}:{sender}"

    async def _run():
        async with _TestSession() as db:
            await whatsapp_worker.persist_inbound(db, _parsed(_text_payload(pnid, sender, "hi", "wamid.r")))
        await whatsapp_worker.drain_conversation(thread)  # agent runs, send fails → 'answered'
        await whatsapp_worker.drain_conversation(thread)  # re-send only → 'done'
        async with _TestSession() as db:
            from app.models.whatsapp import WhatsAppInbox
            from sqlalchemy import select
            row = (await db.execute(select(WhatsAppInbox).where(WhatsAppInbox.message_id == "wamid.r"))).scalar_one()
            return row.status

    status = asyncio.run(_run())
    assert run_calls["n"] == 1  # agent ran ONCE (cart never mutated twice)
    assert send_calls["n"] == 2  # but we retried the send
    assert status == "done"


# --------------------------------------------------------------------------- #
# Rate limiting
# --------------------------------------------------------------------------- #
def test_rate_limit_skips_excess(client, business, monkeypatch):
    headers, business_id = business
    pnid = str(uuid.uuid4().int)[:15]
    _save_connection(client, headers, business_id, pnid)
    sender = "16500000005"
    monkeypatch.setattr(settings, "whatsapp_rate_limit_per_min", 2)

    async def _run():
        async with _TestSession() as db:
            t1 = await whatsapp_worker.persist_inbound(db, _parsed(_text_payload(pnid, sender, "1", "wamid.x1")))
            t2 = await whatsapp_worker.persist_inbound(db, _parsed(_text_payload(pnid, sender, "2", "wamid.x2")))
            t3 = await whatsapp_worker.persist_inbound(db, _parsed(_text_payload(pnid, sender, "3", "wamid.x3")))
            from app.models.whatsapp import WhatsAppInbox
            from sqlalchemy import func, select
            skipped = await db.scalar(
                select(func.count()).select_from(WhatsAppInbox).where(
                    WhatsAppInbox.wa_phone == sender, WhatsAppInbox.status == "skipped"
                )
            )
            return t1, t2, t3, skipped

    t1, t2, t3, skipped = asyncio.run(_run())
    assert t1 and t2  # first two accepted
    assert t3 is None  # third over the limit → not drained
    assert skipped == 1


# --------------------------------------------------------------------------- #
# Outbound resilience
# --------------------------------------------------------------------------- #
class _FakeResp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body
        self.text = str(body)

    def json(self):
        return self._body


class _FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    async def post(self, url, json=None, headers=None):
        resp = self._responses[self.calls]
        self.calls += 1
        return resp


def test_post_message_retries_then_succeeds(monkeypatch):
    async def _no_sleep(*a, **k):
        return None

    monkeypatch.setattr(whatsapp_service.asyncio, "sleep", _no_sleep)
    client = _FakeClient([
        _FakeResp(429, {"error": {"code": 130429, "message": "rate"}}),  # retryable
        _FakeResp(200, {"messages": [{"id": "wamid.OK"}]}),
    ])

    async def _run():
        return await whatsapp_service._post_message(
            phone_number_id="p", access_token="t", payload={"to": "x"}, client=client
        )

    result = asyncio.run(_run())
    assert result.ok and result.message_id == "wamid.OK"
    assert client.calls == 2


def test_post_message_hard_error_not_retried(monkeypatch):
    client = _FakeClient([_FakeResp(400, {"error": {"code": whatsapp_service.ERROR_REENGAGEMENT}})])

    async def _run():
        return await whatsapp_service._post_message(
            phone_number_id="p", access_token="t", payload={"to": "x"}, client=client
        )

    result = asyncio.run(_run())
    assert not result.ok and result.retryable is False
    assert result.error_code == whatsapp_service.ERROR_REENGAGEMENT
    assert client.calls == 1  # gave up immediately on a non-retryable error


def test_post_message_non_ascii_token_fails_clean_without_crashing():
    # A token mangled by copy-paste (here an em-dash) can't be ASCII-encoded into an HTTP header.
    # The send must return a clear, non-retryable result instead of raising UnicodeEncodeError up
    # the worker and crashing the drain.
    client = _FakeClient([])  # never reached — the credential is rejected before any HTTP call

    async def _run():
        return await whatsapp_service._post_message(
            phone_number_id="p",
            access_token="EAAB" + chr(0x2014) + "badtoken",  # em-dash slipped in via copy-paste
            payload={"to": "x"},
            client=client,
        )

    result = asyncio.run(_run())
    assert not result.ok and result.retryable is False
    assert result.error_code == whatsapp_service.ERROR_INVALID_CREDENTIALS
    assert client.calls == 0  # short-circuited before touching the network


# --------------------------------------------------------------------------- #
# Order-status notifications (24h window)
# --------------------------------------------------------------------------- #
def _place_order(client, menu):
    owner, biz = menu["owner"], menu["biz"]
    r = client.post(
        f"/api/v1/businesses/{biz}/orders",
        json={
            "customer_phone": "16500009999",
            "fulfillment": "pickup",
            "payment_method": "cod",
            "items": [{"product_id": menu["product"]["id"], "quantity": 1,
                       "option_item_ids": [menu["regular"]]}],
        },
        headers=owner,
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_status_notification_sends_within_window(client, menu, monkeypatch):
    from datetime import datetime, timezone
    from sqlalchemy import update
    from app.models.customer import Customer

    owner, biz = menu["owner"], menu["biz"]
    _save_connection(client, owner, biz, str(uuid.uuid4().int)[:15])
    order = _place_order(client, menu)

    sent: list[dict] = []

    async def fake_send_text(*, phone_number_id, access_token, to, body):
        sent.append({"to": to, "body": body})
        return whatsapp_service.SendResult(ok=True)

    monkeypatch.setattr(notification_service, "SessionLocal", _TestSession)
    monkeypatch.setattr(whatsapp_service, "send_text", fake_send_text)

    async def _mark_recent_then_notify(within: bool):
        from app.models.order import Order

        async with _TestSession() as db:
            ts = datetime.now(timezone.utc) if within else datetime(2000, 1, 1, tzinfo=timezone.utc)
            await db.execute(
                update(Customer).where(Customer.wa_phone == "16500009999").values(last_inbound_at=ts)
            )
            # Put the order in a state that has a customer-facing message.
            await db.execute(
                update(Order).where(Order.id == uuid.UUID(order["id"])).values(status="accepted")
            )
            await db.commit()
        return await notification_service.notify_order_status(uuid.UUID(biz), uuid.UUID(order["id"]))

    # Within the 24h window → free-form text is sent.
    sent_ok = asyncio.run(_mark_recent_then_notify(within=True))
    assert sent_ok is True
    assert len(sent) == 1
    assert sent[0]["to"] == "16500009999"
    assert order["order_code"] in sent[0]["body"]  # customer-facing code, not "#2"

    # Outside the window with no template configured → nothing sent.
    monkeypatch.setattr(settings, "whatsapp_order_status_template", None)
    sent.clear()
    sent_out = asyncio.run(_mark_recent_then_notify(within=False))
    assert sent_out is False
    assert sent == []


def test_status_notification_recorded_in_agent_memory(client, business):
    # A sent status ping is written into the customer's agent thread so a follow-up reply has it
    # in context (otherwise these out-of-band pings are invisible to the agent).
    from app.agent.runtime import get_whatsapp_agent, thread_id_for

    _, biz = business
    phone = "16500003333"
    text = "Your order K7Q2X9 is out for delivery."
    asyncio.run(notification_service.record_status_in_agent_memory(biz, phone, text))

    agent = get_whatsapp_agent()
    config = {"configurable": {"thread_id": thread_id_for(biz, phone)}}
    state = asyncio.run(agent.aget_state(config))
    contents = [getattr(m, "content", "") for m in (state.values.get("messages") or [])]
    assert any(text in c for c in contents)


# --------------------------------------------------------------------------- #
# Partial multi-message send: a retry resumes, never re-delivering what arrived
# --------------------------------------------------------------------------- #
def test_partial_multi_send_resumes_without_duplicating(client, business, monkeypatch):
    from sqlalchemy import select
    from app.models.whatsapp import WhatsAppInbox

    headers, business_id = business
    pnid = str(uuid.uuid4().int)[:15]
    _save_connection(client, headers, business_id, pnid)
    sender = "16500000007"

    async def fake_run_turn(agent, *, business_id, customer_phone, thread_id, text, confirmed=False, reply_id=None):
        # Two-message reply → two payloads.
        return AgentReply(
            messages=[TextMessage(kind="text", body="one"), TextMessage(kind="text", body="two")]
        )

    batches: list[int] = []

    async def fake_send(*, phone_number_id, access_token, payloads):
        batches.append(len(payloads))
        if len(batches) == 1:
            # Delivered the FIRST of two, then failed → must resume from the second.
            return whatsapp_service.SendResult(
                ok=False, retryable=True, status_code=503, sent=1, sent_ids=["w1"]
            )
        return whatsapp_service.SendResult(ok=True, sent=len(payloads), sent_ids=["w2"])

    _stub_pipeline(monkeypatch, run_turn=fake_run_turn, send_payloads=fake_send)
    thread = f"{business_id}:{sender}"

    async def _run():
        async with _TestSession() as db:
            await whatsapp_worker.persist_inbound(db, _parsed(_text_payload(pnid, sender, "hi", "wamid.m")))
        await whatsapp_worker.drain_conversation(thread)  # sends 1/2, fails → answered, sent_count=1
        await whatsapp_worker.drain_conversation(thread)  # resumes the 2nd only → done
        async with _TestSession() as db:
            row = (
                await db.execute(select(WhatsAppInbox).where(WhatsAppInbox.message_id == "wamid.m"))
            ).scalar_one()
            return row.status, row.sent_count, row.sent_message_ids

    status, sent_count, sent_ids = asyncio.run(_run())
    assert batches == [2, 1]  # first attempt both; retry only the undelivered one (no duplicate)
    assert status == "done"
    assert sent_count == 2
    assert sent_ids == ["w1", "w2"]


# --------------------------------------------------------------------------- #
# Delivery-status webhooks: a post-accept FAILED is recorded against the reply
# --------------------------------------------------------------------------- #
def test_failed_delivery_status_is_recorded(client, business, monkeypatch):
    import json

    from sqlalchemy import select
    from app.models.whatsapp import WhatsAppInbox

    headers, business_id = business
    pnid = str(uuid.uuid4().int)[:15]
    _save_connection(client, headers, business_id, pnid)
    sender = "16500000008"
    monkeypatch.setattr(whatsapp_worker, "SessionLocal", _TestSession)

    status_body = json.dumps(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": pnid},
                                "statuses": [
                                    {
                                        "id": "wamid.OUT1",
                                        "status": "failed",
                                        "recipient_id": sender,
                                        "errors": [{"code": 131026, "title": "Undeliverable"}],
                                    }
                                ],
                            }
                        }
                    ]
                }
            ]
        }
    ).encode()

    async def _run():
        async with _TestSession() as db:
            await whatsapp_worker.persist_inbound(db, _parsed(_text_payload(pnid, sender, "hi", "wamid.s")))
            row = (
                await db.execute(select(WhatsAppInbox).where(WhatsAppInbox.message_id == "wamid.s"))
            ).scalar_one()
            row.sent_message_ids = ["wamid.OUT1"]  # the wamid Meta later reports failed
            await db.commit()
        touched = await whatsapp_worker.record_statuses_from_body(status_body)
        async with _TestSession() as db:
            row = (
                await db.execute(select(WhatsAppInbox).where(WhatsAppInbox.message_id == "wamid.s"))
            ).scalar_one()
            return touched, row.delivery_state, row.error

    touched, state, error = asyncio.run(_run())
    assert touched == 1
    assert state == "failed"
    assert "131026" in (error or "")


# --------------------------------------------------------------------------- #
# Retention: an inactive conversation's inbox rows are purged
# --------------------------------------------------------------------------- #
def test_purge_removes_inactive_conversations(client, business, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import func, select, update
    from app.models.whatsapp import WhatsAppInbox

    headers, business_id = business
    pnid = str(uuid.uuid4().int)[:15]
    _save_connection(client, headers, business_id, pnid)
    sender = "16500000010"
    monkeypatch.setattr(whatsapp_worker, "SessionLocal", _TestSession)
    monkeypatch.setattr(settings, "whatsapp_retention_days", 30)

    async def _run():
        async with _TestSession() as db:
            await whatsapp_worker.persist_inbound(db, _parsed(_text_payload(pnid, sender, "old", "wamid.old")))
            old_ts = datetime.now(timezone.utc) - timedelta(days=60)
            await db.execute(
                update(WhatsAppInbox)
                .where(WhatsAppInbox.message_id == "wamid.old")
                .values(created_at=old_ts)
            )
            await db.commit()
        purged = await whatsapp_worker.purge_once()
        async with _TestSession() as db:
            remaining = await db.scalar(
                select(func.count())
                .select_from(WhatsAppInbox)
                .where(WhatsAppInbox.message_id == "wamid.old")
            )
        return purged, remaining

    purged, remaining = asyncio.run(_run())
    assert purged >= 1
    assert remaining == 0


# --------------------------------------------------------------------------- #
# Handoff is time-boxed: the bot resumes after the mute window (no permanent mute)
# --------------------------------------------------------------------------- #
def test_handoff_mute_window_expires():
    from datetime import datetime, timedelta, timezone

    from app.agent.runtime import _handoff_active

    now = datetime.now(timezone.utc)
    settings.whatsapp_handoff_mute_hours = 24
    try:
        # Fresh handoff → still muted; old handoff → resume.
        assert _handoff_active({"step": "handed_off", "handoff_at": now.isoformat()}) is True
        old = (now - timedelta(hours=25)).isoformat()
        assert _handoff_active({"step": "handed_off", "handoff_at": old}) is False
        # Not handed off, or no timestamp (legacy) → resume / stay muted respectively.
        assert _handoff_active({"step": "browsing"}) is False
        assert _handoff_active({"step": "handed_off"}) is True
        # 0 hours → never auto-resume.
        settings.whatsapp_handoff_mute_hours = 0
        assert _handoff_active({"step": "handed_off", "handoff_at": old}) is True
    finally:
        settings.whatsapp_handoff_mute_hours = 24
