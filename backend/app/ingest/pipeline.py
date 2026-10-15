"""Приём файлов пациента в хранилище (М2).

Повторная загрузка того же файла ничего не меняет. Изменённый файл даёт новые
версии только тех документов, текст или сведения которых поменялись; прежние
версии остаются в истории.
"""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, true
from sqlalchemy.orm import Session

from ..content import Content, get_content
from ..models import Document, Fact, FactSource, Fragment, IngestionRun, Patient, SourceFile
from . import readers
from .drafts import DocumentDraft, FileDraft, MeasurementDraft, build_file_draft


class IngestError(ValueError):
    pass


@dataclass
class IncomingFile:
    name: str
    data: bytes


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_or_create_patient(
    session: Session, code: str, data_class: str, aliases: list[str], content: Content
) -> Patient:
    if data_class not in content.codes("data_class"):
        raise IngestError(f"класс данных '{data_class}' нет в справочнике")
    patient = session.scalar(select(Patient).where(Patient.code == code))
    if patient is None:
        patient = Patient(code=code, data_class=data_class, aliases=sorted(set(aliases)))
        session.add(patient)
        session.flush()
        return patient
    if patient.data_class != data_class:
        raise IngestError(
            f"пациент {code} уже хранится с классом данных '{patient.data_class}', "
            f"а файлы пришли как '{data_class}'"
        )
    merged = sorted(set(patient.aliases) | set(aliases))
    if merged != patient.aliases:
        patient.aliases = merged
    return patient


def _same_document(doc: Document, draft: DocumentDraft) -> bool:
    return (
        doc.text == draft.text
        and doc.doc_type == draft.doc_type
        and doc.author_specialty == draft.specialty
        and doc.doc_date == draft.doc_date
        and doc.title == draft.title
    )


def _save_document(
    session: Session, patient: Patient, source: SourceFile, run: IngestionRun, draft: DocumentDraft
) -> tuple[Document, str]:
    prev = session.scalar(
        select(Document).where(
            Document.patient_id == patient.id,
            Document.logical_key == draft.logical_key,
            Document.is_current.is_(True),
        )
    )
    if prev is not None and _same_document(prev, draft):
        return prev, "unchanged"

    doc = Document(
        id=uuid.uuid4(),
        patient_id=patient.id,
        source_file_id=source.id,
        ingestion_run_id=run.id,
        logical_key=draft.logical_key,
        version=prev.version + 1 if prev else 1,
        is_current=True,
        supersedes_id=prev.id if prev else None,
        doc_type=draft.doc_type,
        author_specialty=draft.specialty,
        title=draft.title,
        doc_date=draft.doc_date,
        doc_date_precision=draft.doc_date_precision,
        date_source=draft.date_source,
        needs_review=bool(draft.notes),
        review_notes=draft.notes,
        text=draft.text,
        source_start=draft.source_start,
        source_end=draft.source_end,
        data_class=patient.data_class,
    )
    for ordinal, f in enumerate(draft.fragments):
        doc.fragments.append(
            Fragment(
                id=uuid.uuid4(),
                ordinal=ordinal,
                kind=f.kind,
                text=draft.text[f.start : f.end],
                start_offset=f.start,
                end_offset=f.end,
                attributes=f.attributes,
            )
        )
    if prev is not None:
        prev.is_current = False
        session.flush()
    session.add(doc)
    session.flush()
    return doc, "new_version" if prev else "created"


def _measurement_value(m: MeasurementDraft, content: Content) -> dict:
    inst = content.instruments[m.result.code]
    return {
        "instrument": inst.code,
        "instrument_name": inst.name,
        "answer_scale": inst.answer_scale,
        "items": [
            {"no": a.item_no, "text": a.header, "answer": a.answer, "score": a.score}
            for a in m.result.answers
        ],
        "total": m.result.total,
        "stated_total": m.result.stated_total,
        "complete": m.result.complete,
        "issues": m.result.issues,
        "timestamp": m.timestamp.isoformat() if m.timestamp else None,
    }


def _save_measurements(
    session: Session, patient: Patient, run: IngestionRun, doc: Document, draft: DocumentDraft, content: Content
) -> int:
    """Измерения шкал записываются фактами со статусом «измерено» и ссылкой на строку таблицы."""
    saved = 0
    for m in draft.measurements:
        fragment = doc.fragments[m.fragment_ordinal]
        prev = session.scalar(
            select(Fact).where(
                Fact.patient_id == patient.id,
                Fact.logical_key == m.logical_key,
                Fact.is_current.is_(True),
            )
        )
        inst = content.instruments[m.result.code]
        day = m.timestamp.date() if m.timestamp else None
        fact = Fact(
            id=uuid.uuid4(),
            patient_id=patient.id,
            ingestion_run_id=run.id,
            logical_key=m.logical_key,
            version=prev.version + 1 if prev else 1,
            supersedes_id=prev.id if prev else None,
            fact_type="measurement",
            code=inst.loinc_total or inst.code,
            value=_measurement_value(m, content),
            occurred_start=day,
            occurred_end=day,
            occurred_precision="day" if day else "unknown",
            known_at=day,
            epistemic_status="measured",
            confirmation_status="unconfirmed",
            data_class=patient.data_class,
            created_by=run.agent,
        )
        fact.sources.append(
            FactSource(
                id=uuid.uuid4(),
                fragment_id=fragment.id,
                quote_start=fragment.start_offset,
                quote_end=fragment.end_offset,
                quote=fragment.text,
            )
        )
        if prev is not None:
            prev.is_current = False
            session.flush()
        session.add(fact)
        saved += 1
    session.flush()
    return saved


def _retire_missing(
    session: Session, patient: Patient, file_name: str, keep: set[str]
) -> list[str]:
    """Документы, которых нет в новой версии файла, перестают быть текущими."""
    stale = session.scalars(
        select(Document)
        .join(SourceFile, Document.source_file_id == SourceFile.id)
        .where(
            Document.patient_id == patient.id,
            Document.is_current.is_(True),
            SourceFile.file_name == file_name,
            Document.logical_key.not_in(keep) if keep else true(),
        )
    ).all()
    for doc in stale:
        doc.is_current = False
    return [d.logical_key for d in stale]


def _known_names(session: Session, patient_id) -> set[str]:
    return set(session.scalars(select(SourceFile.file_name).where(SourceFile.patient_id == patient_id)))


def _unique_name(session: Session, patient: Patient, name: str) -> str:
    """«беседа.txt» -> «беседа (2).txt», если имя уже занято."""
    known = _known_names(session, patient.id)
    if name not in known:
        return name
    stem, suffix = Path(name).stem, Path(name).suffix
    n = 2
    while f"{stem} ({n}){suffix}" in known:
        n += 1
    return f"{stem} ({n}){suffix}"


def find_name_conflicts(session: Session, patient_code: str, files: list[tuple[str, str]]) -> list[dict]:
    """Файлы, чьё имя уже есть у пациента, а содержимое другое. files: [(имя, sha256)]."""
    patient = session.scalar(select(Patient).where(Patient.code == patient_code))
    if patient is None:
        return []
    rows = session.execute(
        select(SourceFile.file_name, SourceFile.sha256, SourceFile.received_at).where(
            SourceFile.patient_id == patient.id
        )
    ).all()
    by_name: dict[str, list] = {}
    for r in rows:
        by_name.setdefault(r.file_name, []).append(r)
    conflicts = []
    for name, sha in files:
        same_name = by_name.get(name, [])
        if same_name and all(r.sha256 != sha for r in same_name) and not any(r.sha256 == sha for r in rows):
            latest = max(r.received_at for r in same_name)
            conflicts.append({"file": name, "existing_received_at": latest.isoformat()})
    return conflicts


def _file_report(draft: FileDraft) -> dict:
    return {
        "file": draft.file_name,
        "splitter": draft.splitter,
        "status": "processed",
        "documents": [],
        "issues": list(draft.issues),
        "unmapped_columns": draft.unmapped_columns,
        "skipped_rows": draft.skipped_rows,
        "retired": [],
    }


def ingest_files(
    session: Session,
    patient_code: str,
    files: list[IncomingFile],
    *,
    data_class: str,
    aliases: list[str] | None = None,
    agent: str = "ingest",
    content: Content | None = None,
    separate: set[str] | None = None,
) -> IngestionRun:
    """separate — имена файлов, которые при совпадении имени сохраняются отдельным
    документом, а не новой версией прежнего."""
    content = content or get_content()
    separate = separate or set()
    aliases = aliases or []
    patient = get_or_create_patient(session, patient_code, data_class, aliases, content)

    run = IngestionRun(id=uuid.uuid4(), patient_id=patient.id, agent=agent, status="running")
    session.add(run)
    session.flush()

    reports = []
    for f in sorted(files, key=lambda x: x.name):
        sha = hashlib.sha256(f.data).hexdigest()
        known = session.scalar(
            select(SourceFile).where(SourceFile.patient_id == patient.id, SourceFile.sha256 == sha)
        )
        if known is not None:
            issues = []
            if known.status == "retracted":
                issues.append(f"этот файл был отозван («{known.file_name}»): верните его во вкладке «Файлы»")
            reports.append({"file": f.name, "status": "unchanged", "documents": [], "issues": issues})
            continue

        name = _unique_name(session, patient, f.name) if f.name in separate else f.name
        draft = build_file_draft(name, f.data, content, patient.aliases)
        report = _file_report(draft)
        if not draft.documents:
            report["status"] = "skipped"
            reports.append(report)
            continue

        source = SourceFile(
            id=uuid.uuid4(),
            patient_id=patient.id,
            ingestion_run_id=run.id,
            file_name=name,
            media_type=readers.media_type(name),
            sha256=sha,
            size=len(f.data),
            content=f.data,
            text=draft.text if draft.splitter != "table" else None,
            data_class=patient.data_class,
        )
        session.add(source)
        session.flush()

        for doc_draft in draft.documents:
            doc, action = _save_document(session, patient, source, run, doc_draft)
            measurements = 0
            if action != "unchanged":
                measurements = _save_measurements(session, patient, run, doc, doc_draft, content)
            report["documents"].append(
                {
                    "id": str(doc.id),
                    "title": doc.title,
                    "doc_type": doc.doc_type,
                    "date": doc.doc_date.isoformat() if doc.doc_date else None,
                    "action": action,
                    "version": doc.version,
                    "fragments": len(doc_draft.fragments),
                    "measurements": measurements,
                    "notes": doc_draft.notes,
                }
            )
        report["retired"] = _retire_missing(
            session, patient, name, {d.logical_key for d in draft.documents}
        )
        if name != f.name:
            report["renamed_from"] = f.name
        reports.append(report)

    actions = [d["action"] for r in reports for d in r["documents"]]
    run.report = {
        "patient": patient.code,
        "files": reports,
        "totals": {
            "files": len(reports),
            "files_unchanged": sum(r["status"] == "unchanged" for r in reports),
            "files_skipped": sum(r["status"] == "skipped" for r in reports),
            "documents_created": actions.count("created"),
            "documents_new_version": actions.count("new_version"),
            "documents_unchanged": actions.count("unchanged"),
            "measurements": sum(d["measurements"] for r in reports for d in r["documents"]),
            "needs_review": sum(bool(d["notes"]) for r in reports for d in r["documents"]),
        },
    }
    run.status = "done"
    run.finished_at = _now()
    session.flush()
    return run


def ingest_folder(
    session: Session,
    folder: Path,
    patient_code: str | None = None,
    *,
    data_class: str,
    aliases: list[str] | None = None,
    agent: str = "cli",
    content: Content | None = None,
) -> IngestionRun:
    files = [
        IncomingFile(p.name, p.read_bytes())
        for p in sorted(folder.iterdir())
        if p.is_file() and not p.name.startswith((".", "~$"))
    ]
    return ingest_files(
        session,
        patient_code or folder.name,
        files,
        data_class=data_class,
        aliases=aliases,
        agent=agent,
        content=content,
    )
