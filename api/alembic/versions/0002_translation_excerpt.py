"""add translation excerpt

Revision ID: 0002_translation_excerpt
Revises: 0001_init
Create Date: 2026-02-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_translation_excerpt"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("items", sa.Column("translation_excerpt", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("items", "translation_excerpt")
