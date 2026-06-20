"""Reusable FastAPI dependencies: DB session, current user, tenant access.

SECURITY: this service connects with a privileged DB role (no Postgres RLS in the
local/MVP setup), so EVERY tenant query must be scoped by the authenticated
business_id. `get_business` is the gate that authorizes the caller and loads the
tenant; handlers then scope all queries with `business.id`.
"""
from __future__ import annotations

import uuid
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import ForbiddenError, NotFoundError, UnauthorizedError
from app.core.security import decode_token
from app.models.business import Business, Membership
from app.models.user import User

DbSession = Annotated[AsyncSession, Depends(get_db)]

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: DbSession,
) -> User:
    if creds is None:
        raise UnauthorizedError("Missing authentication token")
    try:
        payload = decode_token(creds.credentials)
    except jwt.PyJWTError:
        raise UnauthorizedError("Invalid or expired token")
    if payload.get("type") != "access":
        raise UnauthorizedError("Invalid token type")
    sub = payload.get("sub")
    if not sub:
        raise UnauthorizedError("Invalid token")
    user = await db.get(User, uuid.UUID(sub))
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_business(business_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Business:
    """Authorize the current user for `business_id` (path param) and load the tenant."""
    membership = await db.get(Membership, {"user_id": user.id, "business_id": business_id})
    if membership is None:
        raise ForbiddenError("You don't have access to this business")
    business = await db.get(Business, business_id)
    if business is None:
        raise NotFoundError("Business not found")
    return business


BusinessDep = Annotated[Business, Depends(get_business)]


async def get_user_business_ids(user: User, db: AsyncSession) -> list[uuid.UUID]:
    rows = await db.execute(
        select(Membership.business_id).where(Membership.user_id == user.id)
    )
    return list(rows.scalars().all())
