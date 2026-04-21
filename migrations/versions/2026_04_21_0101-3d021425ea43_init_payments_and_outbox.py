"""init payments and outbox

Revision ID: 3d021425ea43
Revises:
Create Date: 2026-04-21 01:01:42.749974

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '3d021425ea43'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'outbox_messages',
        sa.Column(
            'id',
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column('event_type', sa.String(length=128), nullable=False),
        sa.Column(
            'payload',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            'status',
            sa.String(length=16),
            server_default='pending',
            nullable=False,
        ),
        sa.Column(
            'attempts',
            sa.BigInteger(),
            server_default='0',
            nullable=False,
        ),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_outbox_messages_pending',
        'outbox_messages',
        ['created_at'],
        unique=False,
        postgresql_where="status = 'pending'",
    )
    op.create_table(
        'payments',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('idempotency_key', sa.String(length=255), nullable=False),
        sa.Column(
            'amount',
            sa.Numeric(precision=18, scale=2),
            nullable=False,
        ),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('description', sa.String(length=1024), nullable=True),
        sa.Column(
            'metadata',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default='{}',
            nullable=False,
        ),
        sa.Column(
            'status',
            sa.String(length=16),
            server_default='pending',
            nullable=False,
        ),
        sa.Column('webhook_url', sa.String(length=2083), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key')
    )


def downgrade() -> None:
    op.drop_table('payments')
    op.drop_index(
        'ix_outbox_messages_pending',
        table_name='outbox_messages',
        postgresql_where="status = 'pending'",
    )
    op.drop_table('outbox_messages')
