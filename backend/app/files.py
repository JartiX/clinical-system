"""Исходные файлы пациента: список, отзыв, возврат и безвозвратное удаление.

Отзыв убирает из текущих всё, что получено из файла (документы и факты), но
ничего не стирает: отозванный файл можно вернуть. Удаление стирает файл и всё
полученное из него — для данных, которые вообще не должны были попасть в карту
(например, файл другого человека). В обоих случаях остаётся запись действия.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from .models import Document, Fact, FactSource, Fragment, IngestionRun, Patient, SourceFile


class FileActionError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _get(session: Session, file_id: uuid.UUID) -> SourceFile:
    sf = session.get(SourceFile, file_id)
    if sf is None:
        raise LookupError("файл не найден")
    return sf


def _activity(session: Session, sf: SourceFile, kind: str, agent: str, report: dict) -> IngestionRun:
    run = IngestionRun(
        id=uuid.uuid4(),
        patient_id=sf.patient_id,
        kind=kind,
        agent=agent,
        status="done",
        finished_at=_now(),
        report={"file_id": str(sf.id), "file": sf.file_name, **report},
    )
    session.add(run)
    session.flush()
    return run


def list_files(session: Session, patient_code: str) -> list[dict]:
    patient = session.scalar(select(Patient).where(Patient.code == patient_code))
    if patient is None:
        raise LookupError(f"пациент {patient_code} не найден")
    files = session.scalars(
        select(SourceFile).where(SourceFile.patient_id == patient.id).order_by(SourceFile.received_at.desc())
    ).all()
    docs = dict(
        session.execute(
            select(Document.source_file_id, func.count(func.distinct(Document.logical_key)))
            .where(Document.patient_id == patient.id)
            .group_by(Document.source_file_id)
        ).all()
    )
    current = dict(
        session.execute(
            select(Document.source_file_id, func.count())
            .where(Document.patient_id == patient.id, Document.is_current.is_(True))
            .group_by(Document.source_file_id)
        ).all()
    )
    facts = dict(
        session.execute(
            select(Document.source_file_id, func.count(func.distinct(Fact.id)))
            .join(Fragment, Fragment.document_id == Document.id)
            .join(FactSource, FactSource.fragment_id == Fragment.id)
            .join(Fact, Fact.id == FactSource.fact_id)
            .where(Document.patient_id == patient.id, Fact.is_current.is_(True))
            .group_by(Document.source_file_id)
        ).all()
    )
    return [
        {
            "id": str(f.id),
            "file_name": f.file_name,
            "media_type": f.media_type,
            "size": f.size,
            "received_at": f.received_at.isoformat(),
            "status": f.status,
            "status_reason": f.status_reason,
            "status_changed_at": f.status_changed_at.isoformat() if f.status_changed_at else None,
            "documents": docs.get(f.id, 0),
            "documents_current": current.get(f.id, 0),
            "facts_current": facts.get(f.id, 0),
        }
        for f in files
    ]


def retract_file(session: Session, file_id: uuid.UUID, reason: str, agent: str) -> SourceFile:
    sf = _get(session, file_id)
    if sf.status != "active":
        raise FileActionError("файл уже отозван")
    if not reason.strip():
        raise FileActionError("укажите причину отзыва")

    doc_ids = list(
        session.scalars(
            select(Document.id).where(Document.source_file_id == sf.id, Document.is_current.is_(True))
        )
    )
    fact_ids = list(
        session.scalars(
            select(Fact.id)
            .join(FactSource, FactSource.fact_id == Fact.id)
            .join(Fragment, Fragment.id == FactSource.fragment_id)
            .where(Fragment.document_id.in_(doc_ids), Fact.is_current.is_(True))
            .distinct()
        )
    ) if doc_ids else []

    if doc_ids:
        session.execute(update(Document).where(Document.id.in_(doc_ids)).values(is_current=False))
    if fact_ids:
        session.execute(update(Fact).where(Fact.id.in_(fact_ids)).values(is_current=False))
    sf.status, sf.status_reason, sf.status_changed_at = "retracted", reason.strip(), _now()
    _activity(
        session,
        sf,
        "retract",
        agent,
        {"reason": reason.strip(), "documents": [str(i) for i in doc_ids], "facts": [str(i) for i in fact_ids]},
    )
    session.flush()
    return sf


def restore_file(session: Session, file_id: uuid.UUID, agent: str) -> SourceFile:
    sf = _get(session, file_id)
    if sf.status != "retracted":
        raise FileActionError("файл не отозван")
    last = session.scalars(
        select(IngestionRun)
        .where(IngestionRun.kind == "retract", IngestionRun.report["file_id"].astext == str(sf.id))
        .order_by(IngestionRun.started_at.desc())
    ).first()
    report = last.report if last else {"documents": [], "facts": []}

    restored_docs, skipped = [], []
    for doc in session.scalars(select(Document).where(Document.id.in_([uuid.UUID(i) for i in report["documents"]]))):
        # если тем временем появилась другая текущая версия того же документа, её не трогаем
        taken = session.scalar(
            select(func.count()).where(
                Document.patient_id == doc.patient_id,
                Document.logical_key == doc.logical_key,
                Document.is_current.is_(True),
            )
        )
        if taken:
            skipped.append(doc.title)
            continue
        doc.is_current = True
        restored_docs.append(doc.id)
    for fact in session.scalars(select(Fact).where(Fact.id.in_([uuid.UUID(i) for i in report["facts"]]))):
        taken = session.scalar(
            select(func.count()).where(
                Fact.patient_id == fact.patient_id,
                Fact.logical_key == fact.logical_key,
                Fact.is_current.is_(True),
            )
        )
        if not taken:
            fact.is_current = True

    sf.status, sf.status_reason, sf.status_changed_at = "active", None, _now()
    _activity(session, sf, "restore", agent, {"documents": len(restored_docs), "skipped": skipped})
    session.flush()
    return sf


def delete_file(session: Session, file_id: uuid.UUID, reason: str, confirm_name: str, agent: str) -> dict:
    sf = _get(session, file_id)
    if confirm_name != sf.file_name:
        raise FileActionError("для подтверждения введите имя файла точно")
    if not reason.strip():
        raise FileActionError("укажите причину удаления")

    doc_ids = list(session.scalars(select(Document.id).where(Document.source_file_id == sf.id)))
    frag_ids = list(session.scalars(select(Fragment.id).where(Fragment.document_id.in_(doc_ids)))) if doc_ids else []
    touched_facts = (
        set(session.scalars(select(FactSource.fact_id).where(FactSource.fragment_id.in_(frag_ids))))
        if frag_ids
        else set()
    )

    if frag_ids:
        session.execute(delete(FactSource).where(FactSource.fragment_id.in_(frag_ids)))
    # факт удаляется, только если у него не осталось других источников
    orphan_facts = [
        fid
        for fid in touched_facts
        if not session.scalar(select(func.count()).where(FactSource.fact_id == fid))
    ]
    if orphan_facts:
        session.execute(update(Fact).where(Fact.supersedes_id.in_(orphan_facts)).values(supersedes_id=None))
        session.execute(delete(Fact).where(Fact.id.in_(orphan_facts)))
    if doc_ids:
        session.execute(update(Document).where(Document.supersedes_id.in_(doc_ids)).values(supersedes_id=None))
        session.execute(delete(Fragment).where(Fragment.document_id.in_(doc_ids)))
        session.execute(delete(Document).where(Document.id.in_(doc_ids)))

    result = {"reason": reason.strip(), "documents_deleted": len(doc_ids), "facts_deleted": len(orphan_facts)}
    _activity(session, sf, "delete", agent, result)
    session.delete(sf)
    session.flush()
    return {"file": sf.file_name, **result}
