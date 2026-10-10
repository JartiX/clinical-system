"""Синхронизация справочника в БД с content/vocabulary.csv."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from .content import Content
from .models import VocabularyEntry


def sync_vocabulary(session: Session, content: Content) -> dict:
    """Добавляет новые строки и обновляет подписи. Строки не удаляются: на них могут ссылаться данные."""
    existing = {(v.kind, v.code): v for v in session.scalars(select(VocabularyEntry))}
    added = updated = 0
    for row in content.vocabulary:
        entry = existing.get((row.kind, row.code))
        if entry is None:
            session.add(
                VocabularyEntry(kind=row.kind, code=row.code, label=row.label, description=row.description)
            )
            added += 1
        elif entry.label != row.label or entry.description != row.description:
            entry.label, entry.description = row.label, row.description
            updated += 1
    session.flush()
    stale = sorted(f"{k}/{c}" for k, c in existing if not any(r.kind == k and r.code == c for r in content.vocabulary))
    return {"added": added, "updated": updated, "not_in_csv": stale}
