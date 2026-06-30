"""Product CRUD with reusable modifier-group assignments."""
from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace

from fastapi import APIRouter, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.deps import BusinessDep, DbSession
from app.core.errors import BadRequestError, NotFoundError
from app.models.menu import (
    Category,
    ModifierGroup,
    ModifierOption,
    Product,
    ProductModifierGroup,
    ProductModifierOptionPrice,
)
from app.schemas.menu import (
    ModifierGroupCreate,
    ModifierOptionIn,
    ProductCreate,
    ProductImageUploadOut,
    ProductModifierAssignmentIn,
    ProductOut,
    ProductUpdate,
)

router = APIRouter(prefix="/businesses/{business_id}/products", tags=["menu"])

IMAGE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


async def _validate_category(db, business_id: uuid.UUID, category_id: uuid.UUID | None) -> None:
    """Reject a category that belongs to another tenant (or doesn't exist)."""
    if category_id is None:
        return
    owned = await db.scalar(
        select(Category.id).where(
            Category.id == category_id, Category.business_id == business_id
        )
    )
    if owned is None:
        raise BadRequestError("category_id does not belong to this business")


def _with_modifiers():
    return (
        selectinload(Product.modifier_groups)
        .selectinload(ProductModifierGroup.group)
        .selectinload(ModifierGroup.items),
        selectinload(Product.modifier_groups).selectinload(
            ProductModifierGroup.option_prices
        ),
    )


def _sync_group_options(
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


def _apply_definition(
    group: ModifierGroup,
    business_id: uuid.UUID,
    definition: ModifierGroupCreate,
) -> None:
    group.name = definition.name
    group.display_name = definition.display_name or definition.name
    group.select_type = definition.select_type
    group.is_template = definition.is_template
    _sync_group_options(group, business_id, definition.items)


def _sync_option_configs(
    assignment: ProductModifierGroup,
    business_id: uuid.UUID,
    group: ModifierGroup,
    incoming,
) -> None:
    option_by_id = {item.id: item for item in group.items}
    configs = (
        incoming
        if incoming is not None
        else [
            SimpleNamespace(
                option_id=option.id,
                price_delta=None,
                is_default=option.is_default,
            )
            for option in group.items
        ]
    )
    if not configs:
        raise BadRequestError("Enable at least one modifier option")
    option_ids = [item.option_id for item in configs]
    if len(set(option_ids)) != len(option_ids):
        raise BadRequestError("A modifier option can only be enabled once")
    if not set(option_ids).issubset(option_by_id):
        raise BadRequestError("modifier option does not belong to this group")
    if group.select_type == "single" and sum(item.is_default for item in configs) > 1:
        raise BadRequestError("Single-select groups can only have one default option")

    existing = {item.modifier_option_id: item for item in assignment.option_prices}
    synced: list[ProductModifierOptionPrice] = []
    for item in configs:
        config = existing.get(item.option_id)
        if config is None:
            config = ProductModifierOptionPrice(
                business_id=business_id,
                modifier_option_id=item.option_id,
            )
        config.price_delta = item.price_delta
        config.is_default = item.is_default
        synced.append(config)
    assignment.option_prices = synced


async def _sync_assignments(
    db: DbSession,
    business_id: uuid.UUID,
    product: Product,
    assignments: list[ProductModifierAssignmentIn],
) -> None:
    group_ids = [
        assignment.modifier_group_id
        for assignment in assignments
        if assignment.modifier_group_id is not None
    ]
    if len(set(group_ids)) != len(group_ids):
        raise BadRequestError("A modifier group can only be assigned once per product")

    rows = await db.execute(
        select(ModifierGroup).where(
            ModifierGroup.id.in_(group_ids), ModifierGroup.business_id == business_id
        ).options(selectinload(ModifierGroup.items))
    )
    groups = {group.id: group for group in rows.scalars().all()}
    if len(groups) != len(group_ids):
        raise BadRequestError("modifier_group_id does not belong to this business")

    existing_assignments = {
        assignment.modifier_group_id: assignment
        for assignment in product.modifier_groups
    }
    synced_assignments: list[ProductModifierGroup] = []
    for assignment in assignments:
        if assignment.modifier_group_id is None:
            if assignment.definition is None:
                raise BadRequestError("A modifier group definition is required")
            group = ModifierGroup(business_id=business_id)
            _apply_definition(group, business_id, assignment.definition)
            db.add(group)
            await db.flush()
        else:
            group = groups[assignment.modifier_group_id]
            if not group.is_template and group.id not in existing_assignments:
                attached_elsewhere = await db.scalar(
                    select(ProductModifierGroup.id).where(
                        ProductModifierGroup.business_id == business_id,
                        ProductModifierGroup.modifier_group_id == group.id,
                    )
                )
                if attached_elsewhere is not None:
                    raise BadRequestError(
                        "Dish-specific modifier groups cannot be attached to another dish"
                    )
            if assignment.definition is not None:
                if group.is_template:
                    raise BadRequestError(
                        "Edit shared templates in the modifier template manager"
                    )
                _apply_definition(group, business_id, assignment.definition)
                await db.flush()

        if group.select_type == "single" and (
            assignment.min_select > 1
            or (assignment.max_select is not None and assignment.max_select > 1)
        ):
            raise BadRequestError("Single-select modifier limits cannot exceed 1")

        built_assignment = existing_assignments.get(group.id)
        if built_assignment is None:
            built_assignment = ProductModifierGroup(
                business_id=business_id,
                modifier_group_id=group.id,
            )
        built_assignment.group = group
        built_assignment.is_required = assignment.is_required
        built_assignment.min_select = assignment.min_select
        built_assignment.max_select = assignment.max_select
        built_assignment.sort_order = assignment.sort_order
        _sync_option_configs(
            built_assignment,
            business_id,
            group,
            assignment.items,
        )
        enabled_count = len(built_assignment.option_prices)
        required_minimum = max(assignment.min_select, 1) if assignment.is_required else assignment.min_select
        if required_minimum > enabled_count:
            raise BadRequestError("Modifier minimum exceeds the enabled option count")
        synced_assignments.append(built_assignment)

    removed_groups = [
        assignment.group
        for assignment in product.modifier_groups
        if assignment not in synced_assignments and not assignment.group.is_template
    ]
    product.modifier_groups = synced_assignments
    await db.flush()
    for group in removed_groups:
        still_attached = await db.scalar(
            select(ProductModifierGroup.id).where(
                ProductModifierGroup.business_id == business_id,
                ProductModifierGroup.modifier_group_id == group.id
            )
        )
        if still_attached is None:
            await db.delete(group)


async def _get(db, business_id: uuid.UUID, product_id: uuid.UUID) -> Product:
    product = await db.scalar(
        select(Product)
        .where(Product.id == product_id, Product.business_id == business_id)
        .options(*_with_modifiers())
    )
    if product is None:
        raise NotFoundError("Product not found")
    return product


@router.get("", response_model=list[ProductOut])
async def list_products(
    business: BusinessDep,
    db: DbSession,
    category_id: uuid.UUID | None = Query(default=None),
    include_archived: bool = Query(default=False),
) -> list[Product]:
    stmt = (
        select(Product)
        .where(Product.business_id == business.id)
        .options(*_with_modifiers())
        .order_by(Product.sort_order, Product.name)
    )
    if category_id is not None:
        stmt = stmt.where(Product.category_id == category_id)
    if not include_archived:
        stmt = stmt.where(Product.is_archived.is_(False))
    rows = await db.execute(stmt)
    return list(rows.scalars().all())


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(data: ProductCreate, business: BusinessDep, db: DbSession) -> Product:
    await _validate_category(db, business.id, data.category_id)
    product = Product(
        business_id=business.id,
        category_id=data.category_id,
        name=data.name,
        description=data.description,
        price=data.price,
        image_url=data.image_url,
        is_available=data.is_available,
        tags=data.tags,
        prep_minutes=data.prep_minutes,
        sort_order=data.sort_order,
        modifier_groups=[],
    )
    db.add(product)
    await _sync_assignments(db, business.id, product, data.modifier_groups)
    await db.commit()
    return await _get(db, business.id, product.id)


@router.post("/images", response_model=ProductImageUploadOut, status_code=status.HTTP_201_CREATED)
async def upload_product_image(request: Request, business: BusinessDep) -> ProductImageUploadOut:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    extension = IMAGE_EXTENSIONS.get(content_type)
    if extension is None:
        raise BadRequestError("Upload a PNG, JPG, or WebP image.")

    body = await request.body()
    if not body:
        raise BadRequestError("Upload an image file.")
    if len(body) > settings.max_product_image_bytes:
        raise BadRequestError("Image is too large.")

    filename = f"{uuid.uuid4().hex}{extension}"
    relative_path = Path("menu") / str(business.id) / filename
    target = Path(settings.upload_dir).resolve() / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body)

    return ProductImageUploadOut(
        image_url=str(request.url_for("uploads", path=relative_path.as_posix()))
    )


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(product_id: uuid.UUID, business: BusinessDep, db: DbSession) -> Product:
    return await _get(db, business.id, product_id)


@router.patch("/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: uuid.UUID, data: ProductUpdate, business: BusinessDep, db: DbSession
) -> Product:
    product = await _get(db, business.id, product_id)
    payload = data.model_dump(exclude_unset=True, exclude={"modifier_groups"})
    if payload.get("category_id") is not None:
        await _validate_category(db, business.id, payload["category_id"])
    assignments = data.modifier_groups if "modifier_groups" in data.model_fields_set else None
    for field, value in payload.items():
        setattr(product, field, value)
    if assignments is not None:
        await _sync_assignments(db, business.id, product, assignments)
    await db.commit()
    return await _get(db, business.id, product.id)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(product_id: uuid.UUID, business: BusinessDep, db: DbSession) -> None:
    product = await _get(db, business.id, product_id)
    local_groups = [
        assignment.group for assignment in product.modifier_groups if not assignment.group.is_template
    ]
    await db.delete(product)
    await db.flush()
    for group in local_groups:
        still_attached = await db.scalar(
            select(ProductModifierGroup.id).where(
                ProductModifierGroup.business_id == business.id,
                ProductModifierGroup.modifier_group_id == group.id,
            )
        )
        if still_attached is None:
            await db.delete(group)
    await db.commit()
