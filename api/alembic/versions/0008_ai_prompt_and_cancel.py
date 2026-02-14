"""add ai prompt settings and cancel fields

Revision ID: 0008_ai_prompt_and_cancel
Revises: 0007_ai_world
Create Date: 2026-02-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0008_ai_prompt_and_cancel"
down_revision = "0007_ai_world"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_runs", sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ai_runs", sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=100), primary_key=True),
        sa.Column("value", postgresql.JSONB(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
    op.drop_column("ai_runs", "canceled_at")
    op.drop_column("ai_runs", "cancel_requested_at")
