"""End-to-end smoke test against the real app + Postgres. Run: uv run python smoke.py"""
from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app


def main() -> None:
    with TestClient(app) as c:
        spec = c.get("/openapi.json").json()
        api_paths = [p for p in spec["paths"] if p.startswith("/api")]
        print(f"openapi /api paths: {len(api_paths)}")
        assert api_paths, "No /api routes registered!"

        email = f"smoke-{uuid.uuid4().hex[:8]}@example.com"
        r = c.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "password123", "full_name": "Smoke User"},
        )
        assert r.status_code == 201, r.text
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        print("register:", r.status_code, "| me:", c.get("/api/v1/auth/me", headers=h).status_code)

        r = c.post(
            "/api/v1/businesses",
            json={"name": "Smoke Bistro", "type": "restaurant", "currency": "PKR"},
            headers=h,
        )
        assert r.status_code == 201, r.text
        bid = r.json()["id"]
        print("business:", r.json()["name"], "| slug:", r.json()["slug"])

        cat = c.post(
            f"/api/v1/businesses/{bid}/categories", json={"name": "Mains"}, headers=h
        ).json()

        r = c.post(
            f"/api/v1/businesses/{bid}/products",
            json={
                "name": "Beef Burger",
                "price": "850",
                "category_id": cat["id"],
                "option_groups": [
                    {
                        "name": "Size",
                        "select_type": "single",
                        "is_required": True,
                        "items": [
                            {"name": "Regular", "price_delta": "0", "is_default": True},
                            {"name": "Large", "price_delta": "250"},
                        ],
                    }
                ],
            },
            headers=h,
        )
        assert r.status_code == 201, r.text
        prod = r.json()
        large = next(i for g in prod["option_groups"] for i in g["items"] if i["name"] == "Large")
        print("product:", prod["name"], "| option groups:", len(prod["option_groups"]))

        r = c.post(
            f"/api/v1/businesses/{bid}/orders",
            json={
                "customer_phone": "+923001234567",
                "customer_name": "Ayesha",
                "fulfillment": "pickup",
                "payment_method": "cod",
                "items": [{"product_id": prod["id"], "quantity": 2, "option_item_ids": [large["id"]]}],
            },
            headers=h,
        )
        assert r.status_code == 201, r.text
        order = r.json()
        expected = Decimal("850") + Decimal("250")  # unit price with Large
        expected_total = expected * 2  # qty 2, pickup → no delivery/packaging
        got_total = Decimal(str(order["total"]))
        print(f"order {order['order_code']} total={got_total} expected={expected_total}")
        assert got_total == expected_total, f"PRICING WRONG: {got_total} != {expected_total}"

        r = c.patch(
            f"/api/v1/businesses/{bid}/orders/{order['id']}/status",
            json={"status": "accepted", "changed_by": "owner"},
            headers=h,
        )
        assert r.status_code == 200, r.text
        print("status ->", r.json()["status"], "| history:", len(r.json()["status_history"]))

        # tenant isolation: a second user must NOT see business 1
        email2 = f"smoke2-{uuid.uuid4().hex[:8]}@example.com"
        h2 = {
            "Authorization": "Bearer "
            + c.post(
                "/api/v1/auth/register",
                json={"email": email2, "password": "password123"},
            ).json()["access_token"]
        }
        forbidden = c.get(f"/api/v1/businesses/{bid}", headers=h2)
        print("cross-tenant access blocked:", forbidden.status_code == 403)
        assert forbidden.status_code == 403, "TENANT LEAK!"

        print("\n[OK] ALL SMOKE CHECKS PASSED")


if __name__ == "__main__":
    main()
