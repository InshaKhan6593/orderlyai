"""Pytest fixtures: isolated test DB (created/dropped per session) + TestClient."""
from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.db import get_db
from app.main import app
from app.models import Base

TEST_DB_URL = "postgresql+asyncpg://orderlyai:orderlyai@localhost:55432/orderlyai_test"

_engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
_TestSession = async_sessionmaker(_engine, expire_on_commit=False)


async def _override_get_db():
    async with _TestSession() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def _create() -> None:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


async def _drop() -> None:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(scope="session", autouse=True)
def _database():
    asyncio.run(_create())
    yield
    asyncio.run(_drop())


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def owner(client) -> dict[str, str]:
    """A registered user; returns the auth header."""
    email = f"owner-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/api/v1/auth/register", json={"email": email, "password": "password123"}
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def business(client, owner) -> tuple[dict[str, str], str]:
    """An owner with a created business; returns (auth_header, business_id)."""
    r = client.post(
        "/api/v1/businesses",
        json={"name": "Test Bistro", "type": "restaurant", "currency": "PKR"},
        headers=owner,
    )
    assert r.status_code == 201, r.text
    return owner, r.json()["id"]


@pytest.fixture
def menu(client, business) -> dict:
    """Business + category + a product with a REQUIRED single-select Size group
    (Regular +0, Large +250). Returns ids for use in order tests."""
    owner, biz = business
    cat = client.post(
        f"/api/v1/businesses/{biz}/categories", json={"name": "Mains"}, headers=owner
    ).json()
    prod = client.post(
        f"/api/v1/businesses/{biz}/products",
        json={
            "name": "Burger",
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
        headers=owner,
    ).json()
    opts = {i["name"]: i["id"] for g in prod["option_groups"] for i in g["items"]}
    return {
        "owner": owner,
        "biz": biz,
        "product": prod,
        "regular": opts["Regular"],
        "large": opts["Large"],
    }
