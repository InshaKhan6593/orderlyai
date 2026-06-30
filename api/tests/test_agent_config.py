"""AI assistant configuration API."""
from __future__ import annotations

import uuid


def _other_owner(client) -> dict[str, str]:
    email = f"agent-outsider-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/v1/auth/register", json={"email": email, "password": "password123"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_agent_config_defaults_are_english_and_minimal(client, business):
    headers, business_id = business

    r = client.get(f"/api/v1/businesses/{business_id}/agent-config", headers=headers)

    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["business_id"] == business_id
    assert payload["language"] == "en"
    assert payload["upsell_enabled"] is True
    assert "tone" not in payload
    assert "auto_confirm_orders" not in payload
    assert "approval_mode" not in payload


def test_agent_config_can_be_saved_and_read_back(client, business):
    headers, business_id = business

    data = {
        "greeting_message": "Hi! Welcome to Test Bistro. What would you like today?",
        "upsell_enabled": False,
        "human_handoff_phone": "+92 300 1234567",
        "extra_instructions": "Parking is available. Cash and card accepted.",
    }
    saved = client.put(
        f"/api/v1/businesses/{business_id}/agent-config",
        json=data,
        headers=headers,
    )

    assert saved.status_code == 200, saved.text
    payload = saved.json()
    assert payload["greeting_message"] == data["greeting_message"]
    assert payload["language"] == "en"
    assert payload["upsell_enabled"] is False
    assert payload["human_handoff_phone"] == data["human_handoff_phone"]
    assert payload["extra_instructions"] == data["extra_instructions"]

    loaded = client.get(f"/api/v1/businesses/{business_id}/agent-config", headers=headers)
    assert loaded.status_code == 200, loaded.text
    assert loaded.json()["id"] == payload["id"]
    assert loaded.json()["greeting_message"] == data["greeting_message"]


def test_agent_config_is_tenant_scoped(client, business):
    headers, business_id = business
    outsider = _other_owner(client)

    read = client.get(f"/api/v1/businesses/{business_id}/agent-config", headers=outsider)
    write = client.put(
        f"/api/v1/businesses/{business_id}/agent-config",
        json={"greeting_message": "Bad"},
        headers=outsider,
    )

    assert read.status_code == 403
    assert write.status_code == 403

    owner_read = client.get(f"/api/v1/businesses/{business_id}/agent-config", headers=headers)
    assert owner_read.status_code == 200
