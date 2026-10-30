"""Форматы второй партии обезличенных случаев: выгрузка медкарты, расшифровки
с заголовками записей, Markdown, CSV с хвостовыми пустыми полями. Данные синтетические."""

import csv
import io
from datetime import date

import pytest

from app.ingest.drafts import build_file_draft
from app.ingest.questionnaires import TableError, parse_table, table_names
from app.ingest.readers import read_document_text
from app.ingest.splitters import find_date, split_dated_headers, split_recordings

from .conftest import scale_labels

EHR = (
    "ВЫПИСНОЙ ЭПИКРИЗ\n"
    "Дата поступления\n03-06-2026 08:57\n"
    "Дата выписки\n24-06-2026 08:32\n"
    "03.06.2026 : Поступил на отделение\n"
    "Время :\n03.06.2026 08:57\n"
    "05.06.2026 14:19 : Дневник \n"
    "Жалобы на тревогу.\n"
    "05.06.2026 18:00 : Дневник \n"
    "Вечером спокойна.\n"
    ": Консультация\n"
    "Осмотр терапевта.\n"
)

RECORDINGS = (
    "Заголовок: 20250903_110011.m4a\n"
    "========================================\n"
    "Как спите?\nПлохо.\n\n"
    "Заголовок: audio_2025-09-04_19-04-51.ogg\n"
    "========================================\n"
    "Как сегодня?\nЛучше.\n"
)


def test_new_date_formats():
    assert find_date("транскрипт 24102025") == date(2025, 10, 24)
    assert find_date("20250903_110011.m4a") == date(2025, 9, 3)
    assert find_date("Дата выписки 24-06-2026") == date(2026, 6, 24)
    assert find_date("11.03.15.") == date(2015, 3, 11)
    assert find_date("версия 1.10.10.20") is None
    assert find_date("код 12345678") is None


def test_ehr_entries_split_with_and_without_date():
    segs = split_dated_headers(EHR)
    assert [s.header_label for s in segs] == [
        None, "Поступил на отделение", "Дневник", "Дневник", "Консультация"
    ]
    assert segs[2].header_date == date(2026, 6, 5)
    assert segs[4].header_date is None
    assert segs[4].issues[0][0] == "missing_header_date"
    # строка «Время :» без подписи — не заголовок записи
    assert "Время :" in EHR[segs[1].start : segs[1].end]


def test_ehr_file_recognized_by_text_and_preface_is_title_page(content):
    draft = build_file_draft("Пациент 1.docx.txt", EHR.encode(), content)
    assert draft.splitter == "dated_headers"
    preface = draft.documents[0]
    assert preface.doc_type == "discharge_summary"
    assert preface.title == "ВЫПИСНОЙ ЭПИКРИЗ"
    assert preface.doc_date == date(2026, 6, 24)
    types = [d.doc_type for d in draft.documents[1:]]
    assert types == ["administrative_record", "progress_note", "progress_note", "specialist_consultation"]
    # две записи одного дня с одинаковой подписью — разные ключи
    keys = [d.logical_key for d in draft.documents]
    assert len(keys) == len(set(keys))


def test_recordings_become_separate_documents(content):
    assert split_recordings("просто текст") is None
    draft = build_file_draft("Пациент транскрипты.txt", RECORDINGS.encode(), content)
    assert [d.doc_date for d in draft.documents] == [date(2025, 9, 3), date(2025, 9, 4)]
    assert all(d.doc_type == "interview_transcript" for d in draft.documents)
    assert not any(d.notes for d in draft.documents)
    assert "Плохо." in draft.documents[0].text and "Лучше." not in draft.documents[0].text


def test_single_recording_date_mismatch_is_noted(content):
    text = RECORDINGS.split("\n\n")[0]
    draft = build_file_draft("транскрипт 01012025.txt", text.encode(), content)
    doc = draft.documents[0]
    assert doc.doc_date == date(2025, 9, 3)
    assert [n["code"] for n in doc.notes] == ["date_mismatch"]


def test_informant_interview_by_name(content):
    draft = build_file_draft("транскрипт беседы с матерью.txt", "Как она спала?\nПлохо.\n".encode(), content)
    assert draft.documents[0].doc_type == "informant_interview"


def test_markdown_escapes_removed(content):
    assert read_document_text("б.md", "В 2011\\. году \\*\\*".encode()) == "В 2011. году **"
    draft = build_file_draft("транскрипт 20190130.md", "Врач\\.\nПациент\\.\n".encode(), content)
    assert draft.documents[0].text == "Врач.\nПациент."
    assert draft.documents[0].doc_date == date(2019, 1, 30)


def test_unrecognized_readable_file_is_kept_as_unknown(content):
    draft = build_file_draft("Пациент 7.txt", "Какой-то текст.\n".encode(), content)
    doc = draft.documents[0]
    assert doc.doc_type == "unknown"
    assert [n["code"] for n in doc.notes] == ["missing_date", "unknown_doc_type"]


def _csv(rows: list[list[str]]) -> bytes:
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    return buf.getvalue().encode("utf-8")


def _scored_code(content):
    return next(c for c, i in content.instruments.items()
                if i.answer_scale and all(s is not None for _, s in content.answer_scales[i.answer_scale].values()))


def test_csv_rows_longer_than_header_keep_columns(content):
    code = _scored_code(content)
    inst = content.instruments[code]
    label = scale_labels(content, code)[1]
    header = ["Отметка времени", "Имя"] + [inst.items[n] for n in sorted(inst.items)]
    row = ["19.10.2026 13:21:18", "П1"] + [label] * inst.item_count + [""] * 20
    data = _csv([header, row])

    assert table_names("ф.csv", data, content).names == [("П1", 1)]
    parsed = parse_table("ф.csv", data, content, aliases=["П1"])
    resp = parsed.responses[0]
    assert resp.instruments[code].total == inst.item_count
    assert not resp.instruments[code].issues

    with pytest.raises(TableError):
        parse_table("ф.csv", _csv([header, row[:-1] + ["лишнее"]]), content, aliases=["П1"])
    draft = build_file_draft("ф.csv", _csv([header, row[:-1] + ["лишнее"]]), content, ["П1"])
    assert not draft.documents and "значений больше" in draft.issues[0]


BUNDLE = (
    "ВЫПИСНОЙ ЭПИКРИЗ\n\nОтделение №:\n"
    "Период нахождения в стационаре: с «29» октября 2024г. По \"06\" декабря 2024\nг.\n"
    + "Строка эпикриза.\n" * 8
    + "Отделение №:\nПериод: с \" 17 \" апреля 20 24 г. по \" 23 \" мая 20 24 г.\n"
    + "Строка эпикриза.\n" * 8
    + "Дневник составленный матерью\nЯ дала утром таблетку.\n"
)


def test_month_word_dates():
    assert find_date("с «29» октября 2024г.") == date(2024, 10, 29)
    assert find_date('Выписан: " 23 " августа 20 24 г.') == date(2024, 8, 23)
    assert find_date("3 Мая 2019") == date(2019, 5, 3)


def test_bundle_of_discharge_summaries_is_split_by_titles(content):
    draft = build_file_draft("Пациент выписки.txt", BUNDLE.encode(), content)
    docs = draft.documents
    # «Отделение №:» сразу под заголовком новый документ не начинает
    assert [d.title for d in docs] == ["ВЫПИСНОЙ ЭПИКРИЗ", "Выписной эпикриз", "Дневник составленный матерью"]
    assert [d.doc_type for d in docs] == ["discharge_summary", "discharge_summary", "informant_record"]
    assert [d.doc_date for d in docs] == [date(2024, 12, 6), date(2024, 5, 23), None]
    assert "17" not in docs[0].text and "таблетку" in docs[2].text
    assert len({d.logical_key for d in docs}) == 3
