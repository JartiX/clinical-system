"""Отзыв, возврат и удаление исходного файла. Данные синтетические."""

import pytest
from sqlalchemy import func, select

from app.files import FileActionError, delete_file, list_files, restore_file, retract_file
from app.ingest.pipeline import IncomingFile, ingest_files
from app.models import Document, Fact, Fragment, IngestionRun, SourceFile

from .conftest import make_form_xlsx, scale_labels

VISITS = "20240105_Эндокринолог\n\tПервый визит.\n\n20240301_Эндокринолог\n\tВторой визит.\n"


def _form(content):
    code = next(c for c, i in content.instruments.items()
                if i.answer_scale and all(s is not None for _, s in content.answer_scales[i.answer_scale].values()))
    answers = {(code, n): scale_labels(content, code)[0] for n in content.instruments[code].items}
    return make_form_xlsx(content, [{"ts": 46000.0, "name": "С", "answers": answers}], [code])


def _load(session, content):
    run = ingest_files(session, "SYN-F", [
        IncomingFile("саммари выписок.txt", VISITS.encode()),
        IncomingFile("опросник.xlsx", _form(content)),
    ], data_class="synthetic", content=content)
    session.commit()
    return run


def _file(session, name):
    return session.scalar(select(SourceFile).where(SourceFile.file_name == name))


def _current_docs(session):
    return session.scalar(select(func.count()).select_from(Document).where(Document.is_current.is_(True)))


def test_list_files_counts(session, content):
    _load(session, content)
    files = {f["file_name"]: f for f in list_files(session, "SYN-F")}
    assert files["саммари выписок.txt"]["documents_current"] == 2
    assert files["опросник.xlsx"]["facts_current"] == 1


def test_retract_hides_all_documents_and_facts_and_restore_brings_back(session, content):
    _load(session, content)
    summary, form = _file(session, "саммари выписок.txt"), _file(session, "опросник.xlsx")

    retract_file(session, summary.id, "файл другого пациента", agent="t")
    retract_file(session, form.id, "не тот опросник", agent="t")
    session.commit()
    assert _current_docs(session) == 0
    assert not session.scalar(select(func.count()).select_from(Fact).where(Fact.is_current.is_(True)))
    with pytest.raises(FileActionError):
        retract_file(session, summary.id, "ещё раз", agent="t")

    # повторная загрузка отозванного файла подсказывает вернуть его
    run = ingest_files(session, "SYN-F", [IncomingFile("копия.txt", VISITS.encode())], data_class="synthetic", content=content)
    assert "отозван" in run.report["files"][0]["issues"][0]

    restore_file(session, summary.id, agent="t")
    restore_file(session, form.id, agent="t")
    session.commit()
    assert _current_docs(session) == 3
    assert session.scalar(select(func.count()).select_from(Fact).where(Fact.is_current.is_(True))) == 1
    kinds = sorted(session.scalars(select(IngestionRun.kind)))
    assert kinds.count("retract") == 2 and kinds.count("restore") == 2


def test_retract_requires_reason(session, content):
    _load(session, content)
    with pytest.raises(FileActionError, match="причину"):
        retract_file(session, _file(session, "опросник.xlsx").id, "  ", agent="t")


def test_delete_removes_everything_but_keeps_activity(session, content):
    _load(session, content)
    form = _file(session, "опросник.xlsx")
    with pytest.raises(FileActionError, match="имя файла"):
        delete_file(session, form.id, "чужой файл", "не то имя", agent="t")

    result = delete_file(session, form.id, "чужой файл", "опросник.xlsx", agent="t")
    session.commit()
    assert result["documents_deleted"] == 1 and result["facts_deleted"] == 1
    assert _file(session, "опросник.xlsx") is None
    assert not session.scalar(select(func.count()).select_from(Fact))
    assert session.scalar(select(func.count()).select_from(Fragment)) > 0  # фрагменты выписок на месте
    deleted = session.scalar(select(IngestionRun).where(IngestionRun.kind == "delete"))
    assert deleted.report["file"] == "опросник.xlsx" and deleted.report["reason"] == "чужой файл"

    # после удаления тот же файл можно загрузить заново
    run = ingest_files(session, "SYN-F", [IncomingFile("опросник.xlsx", _form(content))], data_class="synthetic", content=content)
    assert run.report["totals"]["documents_created"] == 1


def test_delete_file_with_edited_document_versions(session, content):
    from datetime import date
    from app.documents import edit_document

    _load(session, content)
    summary = _file(session, "саммари выписок.txt")
    doc = session.scalar(select(Document).where(Document.source_file_id == summary.id))
    edit_document(session, doc.id, {"doc_date": date(2024, 1, 6)}, agent="t", content=content)
    session.commit()
    result = delete_file(session, summary.id, "ошибка", "саммари выписок.txt", agent="t")
    session.commit()
    assert result["documents_deleted"] == 3
    assert session.scalar(select(func.count()).select_from(Document)) == 1  # остался только опросник
