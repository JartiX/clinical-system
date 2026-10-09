"""Статус исходного файла: отзыв и возврат

Revision ID: 0003
Revises: 0002
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("source_file", sa.Column("status", sa.String(32), nullable=False, server_default="active"))
    op.add_column("source_file", sa.Column("status_reason", sa.Text(), nullable=True))
    op.add_column("source_file", sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("source_file", "status_changed_at")
    op.drop_column("source_file", "status_reason")
    op.drop_column("source_file", "status")
