"""add full translation column

Revision ID: 0004_translation_full
Revises: 0003_item_favorite_stats
Create Date: 2026-02-01 07:10:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_translation_full"
down_revision = "0003_item_favorite_stats"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("items", sa.Column("translation_full_zh", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("items", "translation_full_zh")
