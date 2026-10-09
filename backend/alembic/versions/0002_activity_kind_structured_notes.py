"""Вид действия и замечания к документам в виде {code, text}

Revision ID: 0002
Revises: 0001
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ingestion_run", sa.Column("kind", sa.String(32), nullable=False, server_default="ingest"))
    # старые замечания были строками; код восстанавливается по началу текста
    op.execute(
        """
        UPDATE document SET review_notes = (
            SELECT coalesce(jsonb_agg(jsonb_build_object(
                'code', CASE
                    WHEN e LIKE 'дата документа не указана%' THEN 'missing_date'
                    WHEN e LIKE 'дата взята из заголовка%' THEN 'date_from_header'
                    WHEN e LIKE 'вид документа не%' THEN 'unknown_doc_type'
                    WHEN e LIKE 'неверная дата%' THEN 'invalid_header_date'
                    ELSE 'other' END,
                'text', CASE
                    WHEN e LIKE 'дата документа не указана%' THEN 'дата документа не указана'
                    ELSE e END)), '[]'::jsonb)
            FROM jsonb_array_elements_text(review_notes) AS e)
        WHERE jsonb_typeof(review_notes -> 0) = 'string'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE document SET review_notes = (
            SELECT coalesce(jsonb_agg(n ->> 'text'), '[]'::jsonb) FROM jsonb_array_elements(review_notes) AS n)
        WHERE jsonb_typeof(review_notes -> 0) = 'object'
        """
    )
    op.drop_column("ingestion_run", "kind")
