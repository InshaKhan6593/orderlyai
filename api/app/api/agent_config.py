"""AI assistant configuration (tenant-scoped)."""
from __future__ import annotations

from sqlalchemy import select

from fastapi import APIRouter

from app.core.deps import BusinessDep, DbSession
from app.models.agent import AgentConfig
from app.schemas.agent import AgentConfigIn, AgentConfigOut

router = APIRouter(prefix="/businesses/{business_id}/agent-config", tags=["agent"])


def default_greeting(business_name: str) -> str:
    return (
        f"Hi! Welcome to {business_name}. I can show you our menu and take your order. "
        "What would you like today?"
    )


def _out(config: AgentConfig | None, business) -> AgentConfigOut:
    if config is not None:
        return AgentConfigOut.model_validate(
            {
                "id": config.id,
                "business_id": config.business_id,
                "greeting_message": config.greeting_message,
                "language": config.language,
                "upsell_enabled": config.upsell_enabled,
                "human_handoff_phone": config.human_handoff_phone,
                "extra_instructions": config.extra_instructions,
            }
        )
    return AgentConfigOut(
        id=None,
        business_id=business.id,
        greeting_message=default_greeting(business.name),
        language="en",
        upsell_enabled=True,
        human_handoff_phone=business.helpline_phone,
        extra_instructions=None,
    )


async def _get_config(db: DbSession, business_id) -> AgentConfig | None:
    row = await db.execute(
        select(AgentConfig).where(AgentConfig.business_id == business_id)
    )
    return row.scalar_one_or_none()


@router.get("", response_model=AgentConfigOut)
async def get_agent_config(business: BusinessDep, db: DbSession) -> AgentConfigOut:
    return _out(await _get_config(db, business.id), business)


@router.put("", response_model=AgentConfigOut)
async def save_agent_config(
    data: AgentConfigIn, business: BusinessDep, db: DbSession
) -> AgentConfig:
    config = await _get_config(db, business.id)
    if config is None:
        config = AgentConfig(
            business_id=business.id,
            greeting_message=default_greeting(business.name),
            language="en",
            upsell_enabled=True,
            human_handoff_phone=business.helpline_phone,
        )
        db.add(config)

    patch = data.model_dump(exclude_unset=True)
    for field, value in patch.items():
        if isinstance(value, str):
            value = value.strip() or None
        setattr(config, field, value)

    if not config.greeting_message:
        config.greeting_message = default_greeting(business.name)
    config.language = "en"
    await db.commit()
    await db.refresh(config)
    return config
