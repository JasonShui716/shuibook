"""add ai world fields and runs

Revision ID: 0007_ai_world
Revises: 0006_item_disliked
Create Date: 2026-02-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_ai_world"
down_revision = "0006_item_disliked"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "items",
        sa.Column("world", sa.String(length=20), nullable=False, server_default="real"),
    )
    op.add_column("items", sa.Column("ai_topic", sa.String(length=255), nullable=True))
    op.add_column("items", sa.Column("ai_prompt", sa.Text(), nullable=True))
    op.add_column("items", sa.Column("ai_model", sa.String(length=100), nullable=True))
    op.add_column("items", sa.Column("ai_generated_at", sa.DateTime(timezone=True), nullable=True))
    op.alter_column("items", "world", server_default=None)

    op.create_table(
        "ai_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="running"),
        sa.Column("celery_task_id", sa.String(length=100), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("topic", sa.String(length=255), nullable=True),
        sa.Column("requested_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.alter_column("ai_runs", "status", server_default=None)
    op.alter_column("ai_runs", "requested_count", server_default=None)
    op.alter_column("ai_runs", "new_items", server_default=None)


def downgrade() -> None:
    op.drop_table("ai_runs")
    op.drop_column("items", "ai_generated_at")
    op.drop_column("items", "ai_model")
    op.drop_column("items", "ai_prompt")
    op.drop_column("items", "ai_topic")
    op.drop_column("items", "world")
