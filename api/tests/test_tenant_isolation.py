"""Tenant isolation — the security-critical guarantee.

A user must never read or write another business's data. Guards against the
CVE-2024-10976 class of multi-tenant leaks (we enforce at the app layer).
"""
from __future__ import annotations

import uuid


def _other_owner(client) -> dict[str, str]:
    email = f"intruder-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/v1/auth/register", json={"email": email, "password": "password123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_outsider_cannot_read_business(client, business):
    _, biz_id = business
    outsider = _other_owner(client)
    assert client.get(f"/api/v1/businesses/{biz_id}", headers=outsider).status_code == 403


def test_outsider_cannot_list_products(client, business):
    _, biz_id = business
    outsider = _other_owner(client)
    assert client.get(f"/api/v1/businesses/{biz_id}/products", headers=outsider).status_code == 403


def test_outsider_cannot_create_category(client, business):
    _, biz_id = business
    outsider = _other_owner(client)
    r = client.post(
        f"/api/v1/businesses/{biz_id}/categories", json={"name": "Hack"}, headers=outsider
    )
    assert r.status_code == 403


def test_outsider_cannot_upload_product_image(client, business):
    _, biz_id = business
    outsider = _other_owner(client)
    r = client.post(
        f"/api/v1/businesses/{biz_id}/products/images",
        content=b"image-bytes",
        headers={**outsider, "content-type": "image/png"},
    )
    assert r.status_code == 403


def test_owner_only_lists_own_businesses(client, business):
    _, biz_id = business
    outsider = _other_owner(client)
    mine = client.get("/api/v1/businesses", headers=outsider).json()
    assert all(b["id"] != biz_id for b in mine)
