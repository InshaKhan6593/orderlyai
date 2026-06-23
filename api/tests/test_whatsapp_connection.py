"""WhatsApp Cloud API connection setup."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core import crypto
from app.core.config import settings
from app.models.whatsapp import WhatsAppConnection

_TEST_DB_URL = "postgresql+asyncpg://orderlyai:orderlyai@localhost:55432/orderlyai_test"


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _read_stored_token(business_id: str) -> str | None:
    """Read the raw access_token column straight from the DB (bypassing the API)."""

    async def _query() -> str | None:
        engine = create_async_engine(_TEST_DB_URL, poolclass=NullPool)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                result = await session.execute(
                    select(WhatsAppConnection.access_token).where(
                        WhatsAppConnection.business_id == uuid.UUID(business_id)
                    )
                )
                return result.scalar_one_or_none()
        finally:
            await engine.dispose()

    return asyncio.run(_query())


def _other_owner(client) -> dict[str, str]:
    email = f"wa-outsider-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/v1/auth/register", json={"email": email, "password": "password123"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_whatsapp_connection_defaults_to_not_configured(client, business):
    headers, business_id = business

    r = client.get(f"/api/v1/businesses/{business_id}/whatsapp-connection", headers=headers)

    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["id"] is None
    assert payload["business_id"] == business_id
    assert payload["mode"] == "test"
    assert payload["status"] == "not_configured"
    assert payload["has_access_token"] is False
    assert "access_token" not in payload


def test_whatsapp_connection_saves_meta_fields_without_echoing_token(client, business):
    headers, business_id = business

    data = {
        "mode": "test",
        "waba_id": "123456789012345",
        "phone_number_id": "987654321098765",
        "display_phone_number": "+1 555 010 1234",
        "display_name": "OrderlyAI Test Bot",
        "access_token": "EAAG-test-token",
    }
    saved = client.put(
        f"/api/v1/businesses/{business_id}/whatsapp-connection",
        json=data,
        headers=headers,
    )

    assert saved.status_code == 200, saved.text
    payload = saved.json()
    assert payload["business_id"] == business_id
    assert payload["mode"] == "test"
    assert payload["waba_id"] == data["waba_id"]
    assert payload["phone_number_id"] == data["phone_number_id"]
    assert payload["display_phone_number"] == data["display_phone_number"]
    assert payload["display_name"] == data["display_name"]
    assert payload["status"] == "configured"
    assert payload["has_access_token"] is True
    assert "access_token" not in payload

    loaded = client.get(
        f"/api/v1/businesses/{business_id}/whatsapp-connection",
        headers=headers,
    )
    assert loaded.status_code == 200, loaded.text
    assert loaded.json()["id"] == payload["id"]
    assert loaded.json()["has_access_token"] is True


def test_whatsapp_connection_requires_token_on_first_save(client, business):
    headers, business_id = business

    r = client.put(
        f"/api/v1/businesses/{business_id}/whatsapp-connection",
        json={
            "mode": "test",
            "waba_id": "123456789012345",
            "phone_number_id": "987654321098765",
        },
        headers=headers,
    )

    assert r.status_code == 400
    assert r.json()["error"]["code"] == "bad_request"


def test_whatsapp_connection_preserves_existing_token_on_update(client, business):
    headers, business_id = business
    url = f"/api/v1/businesses/{business_id}/whatsapp-connection"

    created = client.put(
        url,
        json={
            "mode": "test",
            "waba_id": "123456789012345",
            "phone_number_id": "987654321098765",
            "display_name": "Old Name",
            "access_token": "EAAG-test-token",
        },
        headers=headers,
    )
    assert created.status_code == 200, created.text

    updated = client.put(
        url,
        json={
            "mode": "test",
            "waba_id": "123456789012345",
            "phone_number_id": "987654321098765",
            "display_name": "New Name",
        },
        headers=headers,
    )

    assert updated.status_code == 200, updated.text
    payload = updated.json()
    assert payload["display_name"] == "New Name"
    assert payload["has_access_token"] is True


def test_whatsapp_connection_is_tenant_scoped(client, business):
    headers, business_id = business
    outsider = _other_owner(client)

    read = client.get(
        f"/api/v1/businesses/{business_id}/whatsapp-connection",
        headers=outsider,
    )
    write = client.put(
        f"/api/v1/businesses/{business_id}/whatsapp-connection",
        json={
            "mode": "test",
            "waba_id": "123456789012345",
            "phone_number_id": "987654321098765",
            "access_token": "EAAG-bad-token",
        },
        headers=outsider,
    )

    assert read.status_code == 403
    assert write.status_code == 403

    owner_read = client.get(
        f"/api/v1/businesses/{business_id}/whatsapp-connection",
        headers=headers,
    )
    assert owner_read.status_code == 200


def test_whatsapp_webhook_verification_uses_configured_verify_token(client, monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_verify_token", "verify-test")

    ok = client.get(
        "/api/v1/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.challenge": "1158201444",
            "hub.verify_token": "verify-test",
        },
    )
    bad = client.get(
        "/api/v1/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.challenge": "1158201444",
            "hub.verify_token": "wrong",
        },
    )

    assert ok.status_code == 200
    assert ok.text == "1158201444"
    assert bad.status_code == 403


def test_secret_encryption_roundtrips_and_is_non_deterministic():
    plaintext = "EAAG-super-secret-token"
    ciphertext = crypto.encrypt_secret(plaintext)

    assert ciphertext != plaintext
    assert crypto.decrypt_secret(ciphertext) == plaintext
    # Fernet embeds a timestamp + IV, so the same input encrypts differently each time.
    assert crypto.encrypt_secret(plaintext) != ciphertext


def test_access_token_is_encrypted_at_rest(client, business):
    headers, business_id = business
    token = "EAAG-plaintext-token-value-do-not-store-raw"

    saved = client.put(
        f"/api/v1/businesses/{business_id}/whatsapp-connection",
        json={
            "mode": "test",
            "waba_id": "123456789012345",
            "phone_number_id": "987654321098765",
            "access_token": token,
        },
        headers=headers,
    )
    assert saved.status_code == 200, saved.text

    stored = _read_stored_token(business_id)
    assert stored is not None
    assert token not in stored  # the raw token must never hit the column
    assert crypto.decrypt_secret(stored) == token


def test_webhook_rejects_post_when_app_secret_unset(client, monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_app_secret", None)

    r = client.post(
        "/api/v1/whatsapp/webhook",
        content=b'{"object":"whatsapp_business_account"}',
        headers={"Content-Type": "application/json"},
    )

    assert r.status_code == 503


def test_webhook_accepts_valid_signature(client, monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_app_secret", "app-secret-xyz")
    body = json.dumps({"object": "whatsapp_business_account", "entry": []}).encode()

    r = client.post(
        "/api/v1/whatsapp/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": _sign("app-secret-xyz", body),
        },
    )

    assert r.status_code == 200, r.text
    assert r.json() == {"status": "received"}


def test_webhook_rejects_invalid_signature(client, monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_app_secret", "app-secret-xyz")
    body = json.dumps({"object": "whatsapp_business_account"}).encode()

    r = client.post(
        "/api/v1/whatsapp/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": _sign("wrong-secret", body),
        },
    )

    assert r.status_code == 403


def test_webhook_rejects_missing_signature(client, monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_app_secret", "app-secret-xyz")

    r = client.post(
        "/api/v1/whatsapp/webhook",
        content=b'{"object":"whatsapp_business_account"}',
        headers={"Content-Type": "application/json"},
    )

    assert r.status_code == 403


def _save_connection(client, headers, business_id, phone_number_id):
    r = client.put(
        f"/api/v1/businesses/{business_id}/whatsapp-connection",
        json={
            "mode": "test",
            "waba_id": "123456789012345",
            "phone_number_id": phone_number_id,
            "access_token": "EAAG-inbound-token",
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text


def _post_signed(client, payload: dict) -> object:
    body = json.dumps(payload).encode()
    return client.post(
        "/api/v1/whatsapp/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": _sign("app-secret-xyz", body),
        },
    )


def _inbound_text_payload(phone_number_id: str, sender: str) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_ID",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "+1 555 010 1234",
                                "phone_number_id": phone_number_id,
                            },
                            "contacts": [
                                {"profile": {"name": "Sheena"}, "wa_id": sender}
                            ],
                            "messages": [
                                {
                                    "from": sender,
                                    "id": "wamid.TEST",
                                    "timestamp": "1700000000",
                                    "type": "text",
                                    "text": {"body": "Hi"},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def test_inbound_message_triggers_placeholder_reply(client, business, monkeypatch):
    from app.api import whatsapp as whatsapp_api
    from app.services import whatsapp_service

    headers, business_id = business
    pnid = str(uuid.uuid4().int)[:15]  # unique per test → unambiguous routing
    _save_connection(client, headers, business_id, pnid)

    calls: list[dict] = []

    async def fake_send_text(*, phone_number_id, access_token, to, body):
        calls.append(
            {"phone_number_id": phone_number_id, "access_token": access_token,
             "to": to, "body": body}
        )
        return True

    monkeypatch.setattr(settings, "whatsapp_app_secret", "app-secret-xyz")
    monkeypatch.setattr(whatsapp_service, "send_text", fake_send_text)

    r = _post_signed(client, _inbound_text_payload(pnid, "16505551234"))

    assert r.status_code == 200, r.text
    assert len(calls) == 1
    assert calls[0]["to"] == "16505551234"
    assert calls[0]["phone_number_id"] == pnid
    # token was decrypted on the way out
    assert calls[0]["access_token"] == "EAAG-inbound-token"
    assert calls[0]["body"] == whatsapp_api._PLACEHOLDER_REPLY


def test_status_notification_does_not_reply(client, business, monkeypatch):
    from app.services import whatsapp_service

    headers, business_id = business
    pnid = str(uuid.uuid4().int)[:15]
    _save_connection(client, headers, business_id, pnid)

    calls: list[dict] = []

    async def fake_send_text(**kwargs):
        calls.append(kwargs)
        return True

    monkeypatch.setattr(settings, "whatsapp_app_secret", "app-secret-xyz")
    monkeypatch.setattr(whatsapp_service, "send_text", fake_send_text)

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": pnid},
                            "statuses": [
                                {
                                    "id": "wamid.X",
                                    "status": "delivered",
                                    "recipient_id": "16505551234",
                                }
                            ],
                        },
                    }
                ]
            }
        ],
    }
    r = _post_signed(client, payload)

    assert r.status_code == 200, r.text
    assert calls == []
