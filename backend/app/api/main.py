"""HTTP API поверх хранилища: пациенты, документы, измерения, приём файлов, выгрузка."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..config import settings
from ..content import ContentError, get_content
from ..db import get_session
from ..documents import EditError, edit_document
from ..files import FileActionError, delete_file, list_files, restore_file, retract_file
from ..ingest.pipeline import IncomingFile, IngestError, find_name_conflicts, ingest_files
from ..models import Document, Fact, Fragment, IngestionRun, Patient, VocabularyEntry
from ..rdf.export import export_patient, validate_graph

app = FastAPI(title="Система поддержки клинического рассуждения", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SessionDep = Annotated[Session, Depends(get_session)]


def _patient(session: Session, code: str) -> Patient:
    patient = session.scalar(select(Patient).where(Patient.code == code))
    if patient is None:
        raise HTTPException(404, f"пациент {code} не найден")
    return patient


def _labels(session: Session) -> dict[tuple[str, str], str]:
    return {(v.kind, v.code): v.label for v in session.scalars(select(VocabularyEntry))}


def _doc_summary(doc: Document, labels: dict, fragments: int | None = None) -> dict:
    return {
        "id": str(doc.id),
        "title": doc.title,
        "doc_type": doc.doc_type,
        "doc_type_label": labels.get(("document_type", doc.doc_type), doc.doc_type),
        "specialty": doc.author_specialty,
        "specialty_label": labels.get(("specialty", doc.author_specialty or ""), doc.author_specialty),
        "doc_date": doc.doc_date.isoformat() if doc.doc_date else None,
        "doc_date_precision": doc.doc_date_precision,
        "date_source": doc.date_source,
        "needs_review": doc.needs_review,
        "review_notes": doc.review_notes,
        "version": doc.version,
        "is_current": doc.is_current,
        "data_class": doc.data_class,
        "file_name": doc.source_file.file_name,
        "source_file_id": str(doc.source_file_id),
        "source_file_status": doc.source_file.status,
        "fragments": fragments,
    }


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/vocabulary")
def vocabulary(session: SessionDep, kind: str | None = None) -> list[dict]:
    q = select(VocabularyEntry).order_by(VocabularyEntry.kind, VocabularyEntry.id)
    if kind:
        q = q.where(VocabularyEntry.kind == kind)
    return [
        {"kind": v.kind, "code": v.code, "label": v.label, "description": v.description}
        for v in session.scalars(q)
    ]


@app.get("/api/patients")
def patients(session: SessionDep) -> list[dict]:
    counts = dict(
        session.execute(
            select(Document.patient_id, func.count())
            .where(Document.is_current.is_(True))
            .group_by(Document.patient_id)
        ).all()
    )
    review = dict(
        session.execute(
            select(Document.patient_id, func.count())
            .where(Document.is_current.is_(True), Document.needs_review.is_(True))
            .group_by(Document.patient_id)
        ).all()
    )
    return [
        {
            "code": p.code,
            "data_class": p.data_class,
            "aliases": p.aliases,
            "documents": counts.get(p.id, 0),
            "needs_review": review.get(p.id, 0),
        }
        for p in session.scalars(select(Patient).order_by(Patient.code))
    ]


@app.get("/api/patients/{code}/documents")
def patient_documents(code: str, session: SessionDep) -> list[dict]:
    patient = _patient(session, code)
    labels = _labels(session)
    fragment_counts = dict(
        session.execute(
            select(Fragment.document_id, func.count())
            .join(Document, Document.id == Fragment.document_id)
            .where(Document.patient_id == patient.id, Document.is_current.is_(True))
            .group_by(Fragment.document_id)
        ).all()
    )
    docs = session.scalars(
        select(Document)
        .where(Document.patient_id == patient.id, Document.is_current.is_(True))
        .options(selectinload(Document.source_file))
        .order_by(Document.doc_date.asc().nulls_last(), Document.title)
    ).all()
    return [_doc_summary(d, labels, fragment_counts.get(d.id, 0)) for d in docs]


@app.get("/api/documents/{doc_id}")
def document(doc_id: uuid.UUID, session: SessionDep) -> dict:
    doc = session.scalar(
        select(Document)
        .where(Document.id == doc_id)
        .options(selectinload(Document.fragments), selectinload(Document.source_file))
    )
    if doc is None:
        raise HTTPException(404, "документ не найден")
    labels = _labels(session)
    versions = session.execute(
        select(Document.id, Document.version, Document.created_at, Document.is_current)
        .where(Document.patient_id == doc.patient_id, Document.logical_key == doc.logical_key)
        .order_by(Document.version)
    ).all()
    return {
        **_doc_summary(doc, labels, len(doc.fragments)),
        "text": doc.text,
        "source_start": doc.source_start,
        "source_end": doc.source_end,
        "fragments": [
            {
                "id": str(f.id),
                "ordinal": f.ordinal,
                "kind": f.kind,
                "start": f.start_offset,
                "end": f.end_offset,
                "attributes": f.attributes,
            }
            for f in doc.fragments
        ],
        "versions": [
            {"id": str(v.id), "version": v.version, "created_at": v.created_at.isoformat(), "is_current": v.is_current}
            for v in versions
        ],
    }


@app.get("/api/patients/{code}/measurements")
def patient_measurements(code: str, session: SessionDep) -> list[dict]:
    patient = _patient(session, code)
    facts = session.scalars(
        select(Fact)
        .where(
            Fact.patient_id == patient.id,
            Fact.is_current.is_(True),
            Fact.fact_type == "measurement",
        )
        .options(selectinload(Fact.sources))
        .order_by(Fact.occurred_start)
    ).all()
    fragment_docs = dict(
        session.execute(
            select(Fragment.id, Fragment.document_id).where(
                Fragment.id.in_([s.fragment_id for f in facts for s in f.sources])
            )
        ).all()
    )
    return [
        {
            "id": str(f.id),
            "code": f.code,
            "date": f.occurred_start.isoformat() if f.occurred_start else None,
            "epistemic_status": f.epistemic_status,
            "confirmation_status": f.confirmation_status,
            "value": f.value,
            "sources": [
                {
                    "fragment_id": str(s.fragment_id),
                    "document_id": str(fragment_docs.get(s.fragment_id)),
                    "quote_start": s.quote_start,
                    "quote_end": s.quote_end,
                }
                for s in f.sources
            ],
        }
        for f in facts
    ]


class FileFingerprint(BaseModel):
    name: str
    sha256: str


class FilesCheck(BaseModel):
    files: list[FileFingerprint]


@app.post("/api/patients/{code}/files/check")
def check_files(code: str, body: FilesCheck, session: SessionDep) -> dict:
    """Перед загрузкой: какие файлы совпадают по имени с уже загруженными, но отличаются содержимым."""
    return {"conflicts": find_name_conflicts(session, code, [(f.name, f.sha256) for f in body.files])}


@app.post("/api/patients/{code}/files")
async def upload_files(
    code: str,
    session: SessionDep,
    files: Annotated[list[UploadFile], File(description="файлы пациента")],
    data_class: Annotated[str, Form()] = settings.default_data_class,
    aliases: Annotated[str, Form(description="имена пациента в опросниках через запятую")] = "",
    separate: Annotated[list[str], Form(description="файлы, которые сохранить отдельно при совпадении имени")] = [],
) -> dict:
    incoming = [IncomingFile(f.filename or "без_имени", await f.read()) for f in files]
    try:
        run = ingest_files(
            session,
            code,
            incoming,
            data_class=data_class,
            aliases=[a.strip() for a in aliases.split(",") if a.strip()],
            agent="api",
            content=get_content(),
            separate=set(separate),
        )
    except (IngestError, ContentError) as e:
        session.rollback()
        raise HTTPException(422, str(e)) from e
    session.commit()
    return {"run_id": str(run.id), "report": run.report}


def _count(value) -> int | None:
    return len(value) if isinstance(value, list) else value


@app.get("/api/patients/{code}/runs")
def patient_runs(code: str, session: SessionDep) -> list[dict]:
    patient = _patient(session, code)
    runs = session.scalars(
        select(IngestionRun).where(IngestionRun.patient_id == patient.id).order_by(IngestionRun.started_at.desc())
    )
    return [
        {
            "id": str(r.id),
            "kind": r.kind,
            "agent": r.agent,
            "title": r.report.get("title"),
            "file": r.report.get("file"),
            "reason": r.report.get("reason"),
            "affected_documents": _count(r.report.get("documents", r.report.get("documents_deleted"))),
            "changes": r.report.get("changes"),
            "status": r.status,
            "started_at": r.started_at.isoformat(),
            "totals": r.report.get("totals", {}),
        }
        for r in runs
    ]


@app.get("/api/runs/{run_id}")
def run_report(run_id: uuid.UUID, session: SessionDep) -> dict:
    run = session.get(IngestionRun, run_id)
    if run is None:
        raise HTTPException(404, "приём не найден")
    return {"id": str(run.id), "status": run.status, "started_at": run.started_at.isoformat(), "report": run.report}


@app.get("/api/patients/{code}/export.ttl")
def export_turtle(code: str, session: SessionDep) -> Response:
    _patient(session, code)
    data = export_patient(session, code).serialize(format="turtle")
    return Response(data, media_type="text/turtle; charset=utf-8")


@app.get("/api/patients/{code}/validate")
def validate_patient(code: str, session: SessionDep) -> dict:
    _patient(session, code)
    graph = export_patient(session, code)
    return {"triples": len(graph), **validate_graph(graph)}


class DocumentPatch(BaseModel):
    """Поля, которые можно поправить вручную; не переданные поля не меняются."""

    doc_date: date | None = None
    doc_type: str | None = None
    specialty: str | None = None


@app.patch("/api/documents/{doc_id}")
def patch_document(doc_id: uuid.UUID, patch: DocumentPatch, session: SessionDep) -> dict:
    changes = patch.model_dump(exclude_unset=True)
    if "doc_type" in changes and changes["doc_type"] is None:
        raise HTTPException(422, "вид документа не может быть пустым")
    try:
        doc = edit_document(session, doc_id, changes, agent="web", content=get_content())
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except EditError as e:
        session.rollback()
        raise HTTPException(422, str(e)) from e
    session.commit()
    return document(doc.id, session)


@app.get("/api/patients/{code}/files")
def patient_files(code: str, session: SessionDep) -> list[dict]:
    try:
        return list_files(session, code)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e


class RetractBody(BaseModel):
    reason: str


class DeleteBody(BaseModel):
    reason: str
    confirm_name: str


def _file_action(session: Session, action):
    try:
        result = action()
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except FileActionError as e:
        session.rollback()
        raise HTTPException(422, str(e)) from e
    session.commit()
    return result


@app.post("/api/files/{file_id}/retract")
def retract(file_id: uuid.UUID, body: RetractBody, session: SessionDep) -> dict:
    sf = _file_action(session, lambda: retract_file(session, file_id, body.reason, agent="web"))
    return {"id": str(sf.id), "status": sf.status}


@app.post("/api/files/{file_id}/restore")
def restore(file_id: uuid.UUID, session: SessionDep) -> dict:
    sf = _file_action(session, lambda: restore_file(session, file_id, agent="web"))
    return {"id": str(sf.id), "status": sf.status}


@app.post("/api/files/{file_id}/delete")
def remove(file_id: uuid.UUID, body: DeleteBody, session: SessionDep) -> dict:
    return _file_action(session, lambda: delete_file(session, file_id, body.reason, body.confirm_name, agent="web"))
