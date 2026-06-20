"""Business creation (with owner membership and a unique slug)."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import slugify
from app.models.business import Business, Membership
from app.models.user import User
from app.schemas.business import BusinessCreate


async def _unique_slug(db: AsyncSession, name: str) -> str:
    base = slugify(name)
    slug = base
    while await db.scalar(select(Business.id).where(Business.slug == slug)):
        slug = f"{base}-{uuid.uuid4().hex[:6]}"
    return slug


async def create_business(db: AsyncSession, user: User, data: BusinessCreate) -> Business:
    business = Business(
        name=data.name,
        slug=await _unique_slug(db, data.name),
        type=data.type,
        timezone=data.timezone,
        currency=data.currency,
    )
    db.add(business)
    await db.flush()
    db.add(Membership(user_id=user.id, business_id=business.id, role="owner"))
    await db.commit()
    await db.refresh(business)
    return business
