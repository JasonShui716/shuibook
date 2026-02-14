"""add disliked flag to items

Revision ID: 0006_item_disliked
Revises: 0005_ingest_run_cancel
Create Date: 2026-02-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_item_disliked"
down_revision = "0005_ingest_run_cancel"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("items", sa.Column("is_disliked", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("items", sa.Column("disliked_at", sa.DateTime(timezone=True), nullable=True))
    op.alter_column("items", "is_disliked", server_default=None)


def downgrade() -> None:
    op.drop_column("items", "disliked_at")
    op.drop_column("items", "is_disliked")
