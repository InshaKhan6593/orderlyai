"""Aggregate API router."""
from __future__ import annotations

from fastapi import APIRouter

from app.api import (
    auth,
    businesses,
    categories,
    customers,
    hours,
    orders,
    products,
    zones,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(businesses.router)
api_router.include_router(categories.router)
api_router.include_router(products.router)
api_router.include_router(hours.router)
api_router.include_router(zones.router)
api_router.include_router(customers.router)
api_router.include_router(orders.router)
