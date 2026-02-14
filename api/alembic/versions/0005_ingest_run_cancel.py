"""add cancel fields to ingest runs

Revision ID: 0005_ingest_run_cancel
Revises: 0004_translation_full
Create Date: 2026-02-01
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0005_ingest_run_cancel"
down_revision = "0004_translation_full"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ingest_runs", sa.Column("celery_task_id", sa.String(length=100), nullable=True))
    op.add_column("ingest_runs", sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ingest_runs", sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("ingest_runs", "canceled_at")
    op.drop_column("ingest_runs", "cancel_requested_at")
    op.drop_column("ingest_runs", "celery_task_id")
