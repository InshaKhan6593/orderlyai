"""whatsapp worker hardening: partial-send resume, delivery status, indexes

Adds:
  * whatsapp_inbox.sent_count / sent_message_ids / delivery_state (partial multi-message
    resume + matching Meta delivery-status webhooks),
  * a unique index on whatsapp_connections.phone_number_id (the inbound routing key),
  * a partial active-rows index + a GIN index on whatsapp_inbox,
  * drops the never-written 'processing' status from the inbox CHECK.

Revision ID: a1b2c3d4e5f6
Revises: 701c160aed9b
Create Date: 2026-06-26 17:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '701c160aed9b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # New inbox columns. sent_count gets a temporary server_default so existing rows backfill
    # to 0, then it's dropped to match the model (Python-side default only).
    op.add_column(
        'whatsapp_inbox',
        sa.Column('sent_count', sa.Integer(), nullable=False, server_default='0'),
    )
    op.alter_column('whatsapp_inbox', 'sent_count', server_default=None)
    op.add_column(
        'whatsapp_inbox',
        sa.Column('sent_message_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        'whatsapp_inbox', sa.Column('delivery_state', sa.String(length=16), nullable=True)
    )

    # Drop the unused 'processing' status — rows are never written with it (the advisory lock,
    # not a row-claim, serializes drains). op.f() pins the literal name (the env applies the
    # ck_<table>_ naming convention to bare names).
    op.drop_constraint(
        op.f('ck_whatsapp_inbox_whatsapp_inbox_status'), 'whatsapp_inbox', type_='check'
    )
    op.create_check_constraint(
        op.f('ck_whatsapp_inbox_whatsapp_inbox_status'),
        'whatsapp_inbox',
        "status in ('pending','answered','done','failed','skipped')",
    )

    # Replace the low-cardinality status index with a partial active-rows index for the
    # sweeper, and add the GIN index used to match delivery-status webhooks by wamid.
    op.drop_index('ix_whatsapp_inbox_status', table_name='whatsapp_inbox')
    op.create_index(
        'ix_whatsapp_inbox_active',
        'whatsapp_inbox',
        ['thread_id'],
        postgresql_where=sa.text("status in ('pending','answered')"),
    )
    op.create_index(
        'ix_whatsapp_inbox_sent_ids',
        'whatsapp_inbox',
        ['sent_message_ids'],
        postgresql_using='gin',
    )

    # Index (and enforce one-per-number) the inbound routing key.
    op.create_index(
        'ix_whatsapp_connections_phone_number_id',
        'whatsapp_connections',
        ['phone_number_id'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        'ix_whatsapp_connections_phone_number_id', table_name='whatsapp_connections'
    )
    op.drop_index('ix_whatsapp_inbox_sent_ids', table_name='whatsapp_inbox')
    op.drop_index('ix_whatsapp_inbox_active', table_name='whatsapp_inbox')
    op.create_index('ix_whatsapp_inbox_status', 'whatsapp_inbox', ['status'], unique=False)

    op.drop_constraint(
        op.f('ck_whatsapp_inbox_whatsapp_inbox_status'), 'whatsapp_inbox', type_='check'
    )
    op.create_check_constraint(
        op.f('ck_whatsapp_inbox_whatsapp_inbox_status'),
        'whatsapp_inbox',
        "status in ('pending','processing','answered','done','failed','skipped')",
    )

    op.drop_column('whatsapp_inbox', 'delivery_state')
    op.drop_column('whatsapp_inbox', 'sent_message_ids')
    op.drop_column('whatsapp_inbox', 'sent_count')
