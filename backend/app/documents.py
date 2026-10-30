"""Ручная правка сведений о документе: дата, вид, специальность автора.

Правка не меняет документ на месте: создаётся новая версия с теми же текстом и
фрагментами, а сама правка записывается действием (prov:Activity) с автором.
"""

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .content import Content
from .models import Document, Fact, FactSource, Fragment, IngestionRun

# какие замечания снимает правка какого поля
DATE_NOTES = {"missing_date", "date_from_header", "invalid_header_date"}
TYPE_NOTES = {"unknown_doc_type"}


class EditError(ValueError):
    pass


def edit_document(
    session: Session,
    doc_id: uuid.UUID,
    changes: dict,
    *,
    agent: str,
    content: Content,
) -> Document:
    """changes: любые из ключей doc_date, doc_type, specialty."""
    doc = session.scalar(
        select(Document).where(Document.id == doc_id).options(selectinload(Document.fragments))
    )
    if doc is None:
        raise LookupError("документ не найден")
    if not doc.is_current:
        raise EditError("править можно только текущую версию документа")
    unknown = set(changes) - {"doc_date", "doc_type", "specialty"}
    if unknown:
        raise EditError(f"эти поля нельзя править: {sorted(unknown)}")

    new_date: date | None = changes.get("doc_date", doc.doc_date)
    new_type: str = changes.get("doc_type", doc.doc_type)
    new_specialty: str | None = changes.get("specialty", doc.author_specialty)

    if "doc_date" in changes and doc.date_source == "table":
        raise EditError("дата опросника берётся из отметок времени в таблице")
    if new_type not in content.codes("document_type"):
        raise EditError(f"вида документа '{new_type}' нет в справочнике")
    if new_specialty is not None and new_specialty not in content.codes("specialty"):
        raise EditError(f"специальности '{new_specialty}' нет в справочнике")

    diff = {}
    if new_date != doc.doc_date:
        diff["doc_date"] = [_iso(doc.doc_date), _iso(new_date)]
    if new_type != doc.doc_type:
        diff["doc_type"] = [doc.doc_type, new_type]
    if new_specialty != doc.author_specialty:
        diff["specialty"] = [doc.author_specialty, new_specialty]
    if not diff:
        return doc

    cleared = set()
    if "doc_date" in diff and new_date is not None:
        cleared |= DATE_NOTES
    if "doc_type" in diff and new_type != "unknown":
        cleared |= TYPE_NOTES
    notes = [n for n in doc.review_notes if n.get("code") not in cleared]
    if new_date is None and not any(n.get("code") == "missing_date" for n in notes):
        notes.append({"code": "missing_date", "text": "дата документа не указана"})

    now = datetime.now(timezone.utc)
    activity = IngestionRun(
        id=uuid.uuid4(),
        patient_id=doc.patient_id,
        kind="manual_edit",
        agent=agent,
        status="done",
        finished_at=now,
        report={"document": doc.logical_key, "title": doc.title, "changes": diff},
    )
    session.add(activity)
    session.flush()

    new = Document(
        id=uuid.uuid4(),
        patient_id=doc.patient_id,
        source_file_id=doc.source_file_id,
        ingestion_run_id=activity.id,
        logical_key=doc.logical_key,
        version=doc.version + 1,
        is_current=True,
        supersedes_id=doc.id,
        doc_type=new_type,
        author_specialty=new_specialty,
        title=doc.title,
        doc_date=new_date,
        doc_date_precision="day" if new_date else "unknown",
        date_source="manual" if "doc_date" in diff else doc.date_source,
        needs_review=bool(notes),
        review_notes=notes,
        text=doc.text,
        source_start=doc.source_start,
        source_end=doc.source_end,
        data_class=doc.data_class,
        extraction_status=doc.extraction_status,
    )
    fragment_map = {}
    for f in doc.fragments:
        nf = Fragment(
            id=uuid.uuid4(),
            ordinal=f.ordinal,
            kind=f.kind,
            text=f.text,
            start_offset=f.start_offset,
            end_offset=f.end_offset,
            speaker=f.speaker,
            attributes=f.attributes,
        )
        fragment_map[f.id] = nf
        new.fragments.append(nf)
    doc.is_current = False
    session.flush()
    session.add(new)
    session.flush()

    # источники текущих фактов переводятся на фрагменты новой версии, чтобы цитата
    # открывалась в актуальном документе; старая связь остаётся в старой версии факта
    _repoint_facts(session, fragment_map, activity)
    return new


def _repoint_facts(session: Session, fragment_map: dict, activity: IngestionRun) -> None:
    facts = session.scalars(
        select(Fact)
        .join(FactSource, FactSource.fact_id == Fact.id)
        .where(Fact.is_current.is_(True), FactSource.fragment_id.in_(list(fragment_map)))
        .options(selectinload(Fact.sources))
        .distinct()
    ).all()
    for fact in facts:
        copy = Fact(
            id=uuid.uuid4(),
            patient_id=fact.patient_id,
            ingestion_run_id=activity.id,
            logical_key=fact.logical_key,
            version=fact.version + 1,
            supersedes_id=fact.id,
            fact_type=fact.fact_type,
            code=fact.code,
            value=fact.value,
            negated=fact.negated,
            occurred_start=fact.occurred_start,
            occurred_end=fact.occurred_end,
            occurred_precision=fact.occurred_precision,
            known_at=fact.known_at,
            epistemic_status=fact.epistemic_status,
            confirmation_status=fact.confirmation_status,
            data_class=fact.data_class,
            created_by=fact.created_by,
        )
        for s in fact.sources:
            target = fragment_map.get(s.fragment_id)
            copy.sources.append(
                FactSource(
                    id=uuid.uuid4(),
                    fragment_id=target.id if target else s.fragment_id,
                    quote_start=s.quote_start,
                    quote_end=s.quote_end,
                    quote=s.quote,
                )
            )
        fact.is_current = False
        session.flush()
        session.add(copy)
    session.flush()


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None
