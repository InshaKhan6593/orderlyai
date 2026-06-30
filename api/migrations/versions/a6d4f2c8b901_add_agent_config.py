"""add agent config

Revision ID: a6d4f2c8b901
Revises: f3b21c9d8a77
Create Date: 2026-06-22 23:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a6d4f2c8b901"
down_revision: Union[str, None] = "f3b21c9d8a77"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_configs",
        sa.Column("business_id", sa.UUID(), nullable=False),
        sa.Column("greeting_message", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=8), server_default="en", nullable=False),
        sa.Column("upsell_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("human_handoff_phone", sa.String(length=32), nullable=True),
        sa.Column("extra_instructions", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("language = 'en'", name=op.f("ck_agent_configs_agent_config_language_en_only")),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            name=op.f("fk_agent_configs_business_id_businesses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_configs")),
    )
    op.create_index(op.f("ix_agent_configs_business_id"), "agent_configs", ["business_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_configs_business_id"), table_name="agent_configs")
    op.drop_table("agent_configs")
