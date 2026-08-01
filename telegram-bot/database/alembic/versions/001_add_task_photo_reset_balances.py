"""add description_photo_id to tasks and reset all balances

Revision ID: 001
Revises: 
Create Date: 2026-08-01

"""
from alembic import op
import sqlalchemy as sa

revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add description_photo_id column to tasks table
    op.add_column(
        'tasks',
        sa.Column('description_photo_id', sa.String(512), nullable=True)
    )

    # Reset all user balances to 0
    op.execute("UPDATE users SET balance = 0.0, total_earned = 0.0, total_withdrawn = 0.0")


def downgrade() -> None:
    op.drop_column('tasks', 'description_photo_id')
