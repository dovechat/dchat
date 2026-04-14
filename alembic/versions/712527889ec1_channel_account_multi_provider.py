"""channel_account_multi_provider

Revision ID: 712527889ec1
Revises: 498b368c56ba
Create Date: 2026-04-08 13:43:27.178852

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '712527889ec1'
down_revision = '498b368c56ba'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Добавляем как nullable
    op.add_column('channel_accounts', sa.Column('channel_type', sa.Enum('telegram_user', 'telegram_bot', 'whatsapp_green', 'waba', name='channeltype', native_enum=False), nullable=True))
    op.add_column('channel_accounts', sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True))

    # Заполняем из lines
    op.execute("""
        UPDATE channel_accounts ca
        SET channel_type = l.channel_type
        FROM lines l
        WHERE ca.line_id = l.id
    """)

    op.execute("""
        UPDATE channel_accounts ca
        SET expires_at = l.expires_at
        FROM lines l
        WHERE ca.line_id = l.id
    """)

    # Теперь ставим NOT NULL
    op.alter_column('channel_accounts', 'channel_type', nullable=False)

    op.drop_index(op.f('ix_channel_accounts_line_id'), table_name='channel_accounts')
    op.create_index(op.f('ix_channel_accounts_line_id'), 'channel_accounts', ['line_id'], unique=False)
    op.create_index(op.f('ix_channel_accounts_channel_type'), 'channel_accounts', ['channel_type'], unique=False)
    op.create_index(op.f('ix_channel_accounts_expires_at'), 'channel_accounts', ['expires_at'], unique=False)
    op.create_unique_constraint('uq_channel_account_line_channel', 'channel_accounts', ['line_id', 'channel_type'])
    op.drop_index(op.f('ix_lines_channel_type'), table_name='lines')
    op.drop_index(op.f('ix_lines_expires_at'), table_name='lines')
    op.drop_column('lines', 'expires_at')
    op.drop_column('lines', 'channel_type')