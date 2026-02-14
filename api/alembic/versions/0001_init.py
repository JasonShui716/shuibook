"""init

Revision ID: 0001_init
Revises: 
Create Date: 2026-01-31
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("topics", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("fetch_interval_minutes", sa.Integer(), nullable=False),
        sa.Column("last_fetch_at", sa.DateTime(timezone=True)),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("url_canonical", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("title", sa.Text()),
        sa.Column("title_zh", sa.Text()),
        sa.Column("summary_zh", sa.Text()),
        sa.Column("summary_json", postgresql.JSONB()),
        sa.Column("excerpt", sa.Text()),
        sa.Column("image_url", sa.Text()),
        sa.Column("site_name", sa.String(length=255)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id")),
        sa.Column("hn_item_id", sa.Integer()),
        sa.Column("hn_points", sa.Integer()),
        sa.Column("hn_comments", sa.Integer()),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.UniqueConstraint("url_canonical"),
        sa.UniqueConstraint("content_hash"),
    )

    op.create_table(
        "item_topics",
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), primary_key=True),
        sa.Column("topic", sa.String(length=100), primary_key=True),
    )

    op.create_table(
        "ingest_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("total_candidates", sa.Integer(), server_default="0"),
        sa.Column("new_items", sa.Integer(), server_default="0"),
        sa.Column("error", sa.Text()),
    )

    op.create_table(
        "item_discussions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("thread_id", sa.String(length=100)),
        sa.Column("summary_zh", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("raw_json", postgresql.JSONB()),
    )


def downgrade() -> None:
    op.drop_table("item_discussions")
    op.drop_table("ingest_runs")
    op.drop_table("item_topics")
    op.drop_table("items")
    op.drop_table("sources")
