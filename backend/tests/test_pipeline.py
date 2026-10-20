"""Приём файлов в БД: документы, версии, измерения, проверка SHACL. Данные синтетические."""

from datetime import date

from sqlalchemy import select

from app.ingest.pipeline import IncomingFile, ingest_files
from app.models import Document, Fact, SourceFile
from app.rdf.export import export_patient, validate_graph

from .conftest import make_form_xlsx, scale_labels

SUMMARY = "саммари из выписок.txt"
TRANSCRIPT = "транскрипт беседы 1.txt"
DATED_TRANSCRIPT = "транскрипт беседы 2024-03-15.txt"
FORM = "опросник.xlsx"

VISITS = (
    "20240105_Эндокринолог\n\tЖалобы: слабость.\n\tРекомендовано: контроль через месяц.\n\n"
    "20240210_Непонятный_заголовок\n\n"
    "20240301_Эндокринолог\n\tСостояние стабильное.\n"
)
TALK = "Врач. Как вы себя чувствуете?\nПациент. Лучше, сплю нормально.\n"


def _form(content):
    code = next(c for c, i in content.instruments.items()
                if i.answer_scale and all(s is not None for _, s in content.answer_scales[i.answer_scale].values()))
    labels = scale_labels(content, code)
    answers = {(code, n): labels[1] for n in content.instruments[code].items}
    return code, make_form_xlsx(content, [{"ts": 46100.25, "name": "Синт", "answers": answers}], [code])


def _ingest(session, content, files, **kw):
    run = ingest_files(session, "SYN-1", files, data_class="synthetic", aliases=["Синт"], content=content, **kw)
    session.commit()
    return run


def _current(session):
    return session.scalars(select(Document).where(Document.is_current.is_(True)).order_by(Document.logical_key)).all()


def test_first_ingest_builds_documents_and_measurements(session, content):
    code, form = _form(content)
    run = _ingest(session, content, [
        IncomingFile(SUMMARY, VISITS.encode()),
        IncomingFile(DATED_TRANSCRIPT, TALK.encode("cp1251")),
        IncomingFile(FORM, form),
    ])
    totals = run.report["totals"]
    assert totals["documents_created"] == 5
    assert totals["measurements"] == 1

    docs = {d.title: d for d in _current(session)}
    assert docs["Эндокринолог"].doc_date in (date(2024, 1, 5), date(2024, 3, 1))
    unknown = docs["Непонятный заголовок"]
    assert unknown.doc_type == "unknown" and unknown.needs_review

    talk = next(d for d in docs.values() if d.doc_type == "interview_transcript")
    assert talk.doc_date == date(2024, 3, 15) and talk.date_source == "filename"
    assert [f.text for f in talk.fragments][1] == "Пациент. Лучше, сплю нормально."

    # каждая позиция указывает на тот же текст в исходном файле
    for d in docs.values():
        if d.source_file.text is not None:
            assert d.source_file.text[d.source_start : d.source_end] == d.text
        for f in d.fragments:
            assert d.text[f.start_offset : f.end_offset] == f.text

    fact = session.scalar(select(Fact))
    assert fact.value["instrument"] == code
    assert fact.value["total"] == content.instruments[code].item_count
    assert fact.epistemic_status == "measured" and fact.sources

    result = validate_graph(export_patient(session, "SYN-1"))
    assert result["conforms"], result["violations"]


def test_reingest_same_files_changes_nothing(session, content):
    files = [IncomingFile(SUMMARY, VISITS.encode())]
    _ingest(session, content, files)
    run = _ingest(session, content, files)
    assert run.report["totals"]["files_unchanged"] == 1
    assert session.query(SourceFile).count() == 1


def test_changed_file_versions_only_changed_visits(session, content):
    _ingest(session, content, [IncomingFile(SUMMARY, VISITS.encode())])
    changed = VISITS.replace("Состояние стабильное.", "Состояние улучшилось.").replace(
        "20240210_Непонятный_заголовок\n\n", ""
    )
    run = _ingest(session, content, [IncomingFile(SUMMARY, changed.encode())])

    actions = sorted(d["action"] for d in run.report["files"][0]["documents"])
    assert actions == ["new_version", "unchanged"]
    assert len(run.report["files"][0]["retired"]) == 1

    current = _current(session)
    assert len(current) == 2
    updated = next(d for d in current if d.version == 2)
    assert "улучшилось" in updated.text
    old = session.get(Document, updated.supersedes_id)
    assert old is not None and not old.is_current and "стабильное" in old.text


def test_unknown_file_is_skipped_with_reason(session, content):
    run = _ingest(session, content, [IncomingFile("что-то.bin", b"\x00\x01")])
    report = run.report["files"][0]
    assert report["status"] == "skipped" and report["issues"]


def test_missing_date_marks_document_for_review(session, content):
    _ingest(session, content, [IncomingFile(TRANSCRIPT, TALK.encode())])
    doc = _current(session)[0]
    assert doc.doc_date is None and doc.needs_review
    assert validate_graph(export_patient(session, "SYN-1"))["conforms"]


def test_same_name_other_content_can_be_kept_separately(session, content):
    from app.ingest.pipeline import find_name_conflicts
    import hashlib

    first = TALK.encode()
    second = "Врач. Что нового?\nПациент. Всё так же.\n".encode()
    _ingest(session, content, [IncomingFile(TRANSCRIPT, first)])

    sha = hashlib.sha256(second).hexdigest()
    conflicts = find_name_conflicts(session, "SYN-1", [(TRANSCRIPT, sha)])
    assert [c["file"] for c in conflicts] == [TRANSCRIPT]
    assert find_name_conflicts(session, "SYN-1", [(TRANSCRIPT, hashlib.sha256(first).hexdigest())]) == []

    run = _ingest(session, content, [IncomingFile(TRANSCRIPT, second)], separate={TRANSCRIPT})
    assert run.report["files"][0]["renamed_from"] == TRANSCRIPT
    titles = sorted(d.title for d in _current(session))
    assert titles == ["транскрипт беседы 1", "транскрипт беседы 1 (2)"]
