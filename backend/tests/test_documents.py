"""Ручная правка документа: новая версия, снятие замечаний, перенос источников фактов."""

from datetime import date

import pytest
from sqlalchemy import select

from app.documents import EditError, edit_document
from app.ingest.pipeline import IncomingFile, ingest_files
from app.models import Document, Fact, Fragment, IngestionRun
from app.rdf.export import export_patient, validate_graph

from .conftest import make_form_xlsx, scale_labels

TALK = "Врач. Как сон?\nПациент. Плохо, просыпаюсь ночью.\n"


def _load(session, content, files):
    ingest_files(session, "SYN-2", files, data_class="synthetic", content=content)
    session.commit()
    return session.scalars(select(Document).where(Document.is_current.is_(True))).all()


def test_setting_date_creates_version_and_clears_note(session, content):
    [doc] = _load(session, content, [IncomingFile("транскрипт беседы.txt", TALK.encode())])
    assert doc.needs_review and doc.review_notes[0]["code"] == "missing_date"

    new = edit_document(session, doc.id, {"doc_date": date(2025, 10, 20)}, agent="test", content=content)
    session.commit()

    assert new.version == 2 and new.doc_date == date(2025, 10, 20) and new.date_source == "manual"
    assert not new.needs_review and new.review_notes == []
    assert [f.text for f in new.fragments] == [f.text for f in doc.fragments]
    old = session.get(Document, doc.id)
    assert not old.is_current and old.doc_date is None

    activity = session.get(IngestionRun, new.ingestion_run_id)
    assert activity.kind == "manual_edit" and activity.agent == "test"
    assert activity.report["changes"]["doc_date"] == [None, "2025-10-20"]
    assert validate_graph(export_patient(session, "SYN-2"))["conforms"]


def test_unknown_type_note_cleared_only_by_type(session, content):
    visits = "20240105_Непонятная_строка\n\tтекст\n"
    [doc] = _load(session, content, [IncomingFile("саммари выписок.txt", visits.encode())])
    known_type = next(c for c in content.codes("document_type") if c != "unknown")

    same = edit_document(session, doc.id, {"doc_date": date(2024, 1, 6)}, agent="test", content=content)
    assert [n["code"] for n in same.review_notes] == ["unknown_doc_type"]

    fixed = edit_document(session, same.id, {"doc_type": known_type}, agent="test", content=content)
    assert fixed.version == 3 and not fixed.needs_review


def test_no_changes_returns_same_document(session, content):
    [doc] = _load(session, content, [IncomingFile("транскрипт беседы.txt", TALK.encode())])
    assert edit_document(session, doc.id, {"doc_date": None}, agent="test", content=content).id == doc.id


def test_rejects_bad_edits(session, content):
    [doc] = _load(session, content, [IncomingFile("транскрипт беседы.txt", TALK.encode())])
    with pytest.raises(EditError):
        edit_document(session, doc.id, {"doc_type": "нет_такого"}, agent="t", content=content)
    with pytest.raises(EditError):
        edit_document(session, doc.id, {"text": "x"}, agent="t", content=content)
    new = edit_document(session, doc.id, {"doc_date": date(2025, 1, 1)}, agent="t", content=content)
    with pytest.raises(EditError, match="текущую"):
        edit_document(session, doc.id, {"doc_date": date(2025, 1, 2)}, agent="t", content=content)
    assert new.is_current


def test_table_date_is_not_editable_but_type_is_and_facts_follow(session, content):
    code = next(c for c, i in content.instruments.items()
                if i.answer_scale and all(s is not None for _, s in content.answer_scales[i.answer_scale].values()))
    answers = {(code, n): scale_labels(content, code)[0] for n in content.instruments[code].items}
    form = make_form_xlsx(content, [{"ts": 46000.0, "name": "С", "answers": answers}], [code])
    [doc] = _load(session, content, [IncomingFile("опросник.xlsx", form)])

    with pytest.raises(EditError, match="опросника"):
        edit_document(session, doc.id, {"doc_date": date(2025, 1, 1)}, agent="t", content=content)

    spec = next(iter(content.codes("specialty")))
    new = edit_document(session, doc.id, {"specialty": spec}, agent="t", content=content)
    session.commit()
    fact = session.scalar(select(Fact).where(Fact.is_current.is_(True)))
    fragment = session.get(Fragment, fact.sources[0].fragment_id)
    assert fragment.document_id == new.id and fact.version == 2
