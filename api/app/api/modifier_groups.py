"""Tenant-scoped reusable modifier-group library."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.deps import BusinessDep, DbSession
from app.core.errors import BadRequestError, NotFoundError
from app.models.menu import ModifierGroup, ModifierOption, ProductModifierGroup
from app.schemas.menu import (
    ModifierGroupCreate,
    ModifierGroupOut,
    ModifierGroupUpdate,
    ModifierOptionIn,
)

router = APIRouter(
    prefix="/businesses/{business_id}/modifier-groups", tags=["menu"]
)


def _with_items():
    return selectinload(ModifierGroup.items)


def _sync_options(
    group: ModifierGroup,
    business_id: uuid.UUID,
    items: list[ModifierOptionIn],
) -> None:
    existing = {item.id: item for item in group.items}
    incoming_ids = {item.id for item in items if item.id is not None}
    if not incoming_ids.issubset(existing):
        raise BadRequestError("modifier option does not belong to this group")

    synced: list[ModifierOption] = []
    for position, item in enumerate(items):
        option = existing.get(item.id) if item.id is not None else None
        if option is None:
            option = ModifierOption(business_id=business_id)
        option.name = item.name
        option.description = item.description
        option.price_delta = item.price_delta
        option.is_default = item.is_default
        option.sort_order = item.sort_order if item.sort_order else position
        synced.append(option)
    group.items = synced


async def _get(
    db: DbSession, business_id: uuid.UUID, group_id: uuid.UUID
) -> ModifierGroup:
    group = await db.scalar(
        select(ModifierGroup)
        .where(
            ModifierGroup.id == group_id,
            ModifierGroup.business_id == business_id,
        )
        .options(_with_items())
        .execution_options(populate_existing=True)
    )
    if group is None:
        raise NotFoundError("Modifier group not found")
    return group


@router.get("", response_model=list[ModifierGroupOut])
async def list_modifier_groups(
    business: BusinessDep, db: DbSession
) -> list[ModifierGroup]:
    rows = await db.execute(
        select(ModifierGroup)
        .where(
            ModifierGroup.business_id == business.id,
            ModifierGroup.is_template.is_(True),
        )
        .options(_with_items())
        .order_by(ModifierGroup.name)
    )
    return list(rows.scalars().all())


@router.post("", response_model=ModifierGroupOut, status_code=status.HTTP_201_CREATED)
async def create_modifier_group(
    data: ModifierGroupCreate, business: BusinessDep, db: DbSession
) -> ModifierGroup:
    group = ModifierGroup(
        business_id=business.id,
        name=data.name,
        display_name=data.display_name or data.name,
        select_type=data.select_type,
        is_template=data.is_template,
    )
    _sync_options(group, business.id, data.items)
    db.add(group)
    await db.commit()
    return await _get(db, business.id, group.id)


@router.get("/{group_id}", response_model=ModifierGroupOut)
async def get_modifier_group(
    group_id: uuid.UUID, business: BusinessDep, db: DbSession
) -> ModifierGroup:
    return await _get(db, business.id, group_id)


@router.patch("/{group_id}", response_model=ModifierGroupOut)
async def update_modifier_group(
    group_id: uuid.UUID,
    data: ModifierGroupUpdate,
    business: BusinessDep,
    db: DbSession,
) -> ModifierGroup:
    group = await _get(db, business.id, group_id)
    payload = data.model_dump(exclude_unset=True)
    items = payload.pop("items", None)
    if payload.get("display_name") is None:
        payload.pop("display_name", None)

    if payload.get("select_type") == "single":
        incompatible = await db.scalar(
            select(ProductModifierGroup.id).where(
                ProductModifierGroup.business_id == business.id,
                ProductModifierGroup.modifier_group_id == group.id,
                (
                    (ProductModifierGroup.min_select > 1)
                    | (ProductModifierGroup.max_select > 1)
                ),
            )
        )
        if incompatible is not None:
            raise BadRequestError(
                "Single-select groups cannot use assignment limits above 1"
            )

    for field, value in payload.items():
        setattr(group, field, value)
    if items is not None:
        _sync_options(group, business.id, [ModifierOptionIn(**item) for item in items])
    await db.commit()
    return await _get(db, business.id, group.id)


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_modifier_group(
    group_id: uuid.UUID, business: BusinessDep, db: DbSession
) -> None:
    group = await _get(db, business.id, group_id)
    attached = await db.scalar(
        select(ProductModifierGroup.id).where(
            ProductModifierGroup.business_id == business.id,
            ProductModifierGroup.modifier_group_id == group.id,
        )
    )
    if attached is not None:
        raise BadRequestError(
            "This modifier template is attached to a dish. Detach it before deleting."
        )
    await db.delete(group)
    await db.commit()
