"""Auth flow tests."""
from __future__ import annotations

import uuid


def _email() -> str:
    return f"u-{uuid.uuid4().hex[:8]}@example.com"


def test_register_login_me(client):
    email = _email()
    r = client.post("/api/v1/auth/register", json={"email": email, "password": "password123"})
    assert r.status_code == 201
    assert {"access_token", "refresh_token"} <= r.json().keys()

    r = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    assert r.status_code == 200
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == email


def test_duplicate_email_conflicts(client):
    email = _email()
    client.post("/api/v1/auth/register", json={"email": email, "password": "password123"})
    r = client.post("/api/v1/auth/register", json={"email": email, "password": "password123"})
    assert r.status_code == 409


def test_wrong_password_unauthorized(client):
    email = _email()
    client.post("/api/v1/auth/register", json={"email": email, "password": "password123"})
    r = client.post("/api/v1/auth/login", json={"email": email, "password": "nope"})
    assert r.status_code == 401


def test_me_requires_token(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_short_password_rejected(client):
    r = client.post("/api/v1/auth/register", json={"email": _email(), "password": "short"})
    assert r.status_code == 422
