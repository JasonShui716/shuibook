"""add favorite and view stats to items

Revision ID: 0003_item_favorite_stats
Revises: 0002_translation_excerpt
Create Date: 2026-02-01 06:30:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0003_item_favorite_stats"
down_revision = "0002_translation_excerpt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "items",
        sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("items", sa.Column("favorited_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "items",
        sa.Column("view_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column("items", sa.Column("last_viewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "items",
        sa.Column(
            "total_read_seconds", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
    )
    op.add_column(
        "items",
        sa.Column(
            "long_read_count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
    )


def downgrade() -> None:
    op.drop_column("items", "long_read_count")
    op.drop_column("items", "total_read_seconds")
    op.drop_column("items", "last_viewed_at")
    op.drop_column("items", "view_count")
    op.drop_column("items", "favorited_at")
    op.drop_column("items", "is_favorite")
