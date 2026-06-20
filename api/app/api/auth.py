"""Authentication endpoints."""
from __future__ import annotations

import uuid

import jwt
from fastapi import APIRouter, status

from app.core.deps import CurrentUser, DbSession
from app.core.errors import UnauthorizedError
from app.core.security import decode_token
from app.models.user import User
from app.schemas.auth import LoginIn, RefreshIn, RegisterIn, TokenOut, UserOut
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
async def register(data: RegisterIn, db: DbSession) -> TokenOut:
    user = await auth_service.register_user(db, data)
    return auth_service.issue_tokens(user)


@router.post("/login", response_model=TokenOut)
async def login(data: LoginIn, db: DbSession) -> TokenOut:
    user = await auth_service.authenticate(db, data.email, data.password)
    return auth_service.issue_tokens(user)


@router.post("/refresh", response_model=TokenOut)
async def refresh(data: RefreshIn, db: DbSession) -> TokenOut:
    try:
        payload = decode_token(data.refresh_token)
    except jwt.PyJWTError:
        raise UnauthorizedError("Invalid or expired refresh token")
    if payload.get("type") != "refresh":
        raise UnauthorizedError("Not a refresh token")
    user = await db.get(User, uuid.UUID(payload["sub"]))
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive")
    return auth_service.issue_tokens(user)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> User:
    return user
