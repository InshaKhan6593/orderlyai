"""add whatsapp connections

Revision ID: e8a4d1c2b903
Revises: a6d4f2c8b901
Create Date: 2026-06-22 23:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e8a4d1c2b903"
down_revision: Union[str, None] = "a6d4f2c8b901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "whatsapp_connections",
        sa.Column("business_id", sa.UUID(), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="test"),
        sa.Column("waba_id", sa.String(length=64), nullable=False),
        sa.Column("phone_number_id", sa.String(length=64), nullable=False),
        sa.Column("display_phone_number", sa.String(length=32), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="configured"),
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
        sa.CheckConstraint(
            "mode in ('test','live')",
            name=op.f("ck_whatsapp_connections_whatsapp_connection_mode"),
        ),
        sa.CheckConstraint(
            "status in ('configured','verified','error')",
            name=op.f("ck_whatsapp_connections_whatsapp_connection_status"),
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            name=op.f("fk_whatsapp_connections_business_id_businesses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_whatsapp_connections")),
    )
    op.create_index(
        op.f("ix_whatsapp_connections_business_id"),
        "whatsapp_connections",
        ["business_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_whatsapp_connections_business_id"), table_name="whatsapp_connections")
    op.drop_table("whatsapp_connections")
