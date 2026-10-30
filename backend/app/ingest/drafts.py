"""Файл -> черновики документов. Чистые функции без БД: легко тестировать и смотреть заранее."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from ..content import Content, FileRule, HeaderRule, normalize
from . import questionnaires, readers, splitters


def note(code: str, text: str) -> dict:
    """Замечание к документу: код нужен, чтобы снять его после исправления."""
    return {"code": code, "text": text}


@dataclass
class FragmentDraft:
    kind: str
    start: int
    end: int
    attributes: dict = field(default_factory=dict)


@dataclass
class MeasurementDraft:
    logical_key: str
    fragment_ordinal: int
    timestamp: datetime | None
    result: questionnaires.InstrumentResult


@dataclass
class DocumentDraft:
    logical_key: str
    doc_type: str
    specialty: str | None
    title: str
    doc_date: date | None
    doc_date_precision: str
    date_source: str
    text: str
    source_start: int
    source_end: int
    fragments: list[FragmentDraft] = field(default_factory=list)
    notes: list[dict] = field(default_factory=list)
    measurements: list[MeasurementDraft] = field(default_factory=list)


@dataclass
class FileDraft:
    file_name: str
    splitter: str | None
    text: str | None = None
    documents: list[DocumentDraft] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    unmapped_columns: list[str] = field(default_factory=list)
    skipped_rows: list[str] = field(default_factory=list)


def _single_document_date(file_name: str, text: str) -> tuple[date | None, str, list[dict]]:
    """Дата из имени файла, иначе из первых строк текста (с пометкой на проверку)."""
    found = splitters.find_date(Path(file_name).stem)
    if found:
        return found, "filename", []
    head = "\n".join(text.strip().split("\n")[:3])
    found = splitters.find_date(head)
    if found:
        return found, "header", [note("date_from_header", "дата взята из заголовка документа — проверить")]
    return None, "none", [note("missing_date", "дата документа не указана")]


def _head_date(text: str, lines: int = 15) -> date | None:
    """Самая поздняя дата в шапке документа: в титульной части выписки это дата выписки."""
    found = splitters.find_dates("\n".join(text.strip().split("\n")[:lines]))
    return max(found) if found else None


def _title_line(text: str, rule: FileRule) -> str:
    """Строка, по которой распознан вид документа («ВЫПИСНОЙ ЭПИКРИЗ»)."""
    lines = [s.strip() for s in text.split("\n") if s.strip()]
    return next((s for s in lines if rule.pattern.search(normalize(s))), lines[0] if lines else "")[:120]


def _segment_documents(
    file_name: str,
    text: str,
    segments: list[splitters.Segment],
    content: Content,
    kind: str,
    label_rule: Callable[[str], HeaderRule | None] | None,
    default: tuple[str, str | None],
    date_from_body: bool = False,
) -> list[DocumentDraft]:
    """Документ на каждый сегмент. label_rule: вид документа по строке-заголовку сегмента
    (header_rules, section_rules); без него вид из правила файла (default).
    date_from_body: дату сегмента без даты в заголовке искать в его шапке."""
    typed_by_header = label_rule is not None
    docs = []
    seen: dict[str, int] = {}
    for seg in segments:
        body = text[seg.start : seg.end]
        notes = [note(code, msg) for code, msg in seg.issues]
        doc_type, specialty = default
        doc_date, date_source = seg.header_date, "header" if seg.header_date else "none"
        title = (seg.header_label or Path(file_name).stem).replace("_", " ")
        if seg.header_label is not None and typed_by_header:
            rule = label_rule(seg.header_label)
            if rule:
                doc_type, specialty = rule.doc_type, rule.specialty
                title = rule.title or title
            else:
                doc_type, specialty = "unknown", None
                notes.append(note("unknown_doc_type", f"вид документа не распознан по строке «{seg.header_label}»"))
            if date_from_body and doc_date is None:
                doc_date = _head_date(body)
                date_source = "header" if doc_date else "none"
                notes.append(
                    note("date_from_header", "дата взята из шапки документа — проверить")
                    if doc_date
                    else note("missing_date", "дата документа не указана")
                )
        elif seg.header_label is None and typed_by_header:
            # Текст без строки визита: титульная часть выписки или файл совсем без визитов
            rule = content.match_text(body)
            if rule and rule.doc_type:
                doc_type, specialty = rule.doc_type, rule.specialty
                notes = [n for n in notes if n["code"] not in ("orphan_text", "no_visit_headers")]
                title = _title_line(body, rule) or title
                doc_date = _head_date(body)
                date_source = "header" if doc_date else "none"
                notes.append(
                    note("date_from_header", "дата взята из шапки документа — проверить")
                    if doc_date
                    else note("missing_date", "дата документа не указана")
                )
            else:
                doc_type, specialty = "unknown", None
                notes.append(note("orphan_text", "фрагмент без строки визита"))
        stamp = seg.header_date.strftime("%Y%m%d") if seg.header_date else "nodate"
        base = f"{file_name}#{stamp}_{seg.header_label or ''}"
        seen[base] = seen.get(base, 0) + 1
        docs.append(
            DocumentDraft(
                logical_key=f"{base}#{seen[base]}",
                doc_type=doc_type,
                specialty=specialty,
                title=title,
                doc_date=doc_date,
                doc_date_precision="day" if doc_date else "unknown",
                date_source=date_source,
                text=body,
                source_start=seg.start,
                source_end=seg.end,
                fragments=[
                    FragmentDraft(s.kind, s.start, s.end)
                    for s in splitters.line_spans(body, kind, "header" if seg.header_label is not None else None)
                ],
                notes=notes,
            )
        )
    return docs


def _from_dated_headers(file_name: str, text: str, content: Content) -> list[DocumentDraft]:
    segments = splitters.split_dated_headers(text)
    if segments[0].header_label is None and len(segments) == 1:
        # Строк визита нет: сводный файл из нескольких документов режется по их заголовкам
        sections = splitters.split_sections(text, lambda line: content.match_section(line) is not None)
        if sections:
            return _segment_documents(
                file_name, text, sections, content, "paragraph", content.match_section, ("unknown", None),
                date_from_body=True,
            )
    docs = _segment_documents(file_name, text, segments, content, "paragraph", content.match_header, ("unknown", None))
    # Титульная часть выписки без своей даты относится к последней записи файла
    last = max((s.header_date for s in segments if s.header_date), default=None)
    for doc, seg in zip(docs, segments):
        if seg.header_label is None and doc.doc_date is None and last and doc.doc_type != "unknown":
            doc.doc_date, doc.doc_date_precision, doc.date_source = last, "day", "header"
            doc.notes = [n for n in doc.notes if n["code"] != "missing_date"]
            doc.notes.append(note("date_from_header", "дата взята по последней записи файла — проверить"))
    return docs


def _from_recordings(
    file_name: str,
    text: str,
    segments: list[splitters.Segment],
    content: Content,
    default: tuple[str, str | None],
) -> list[DocumentDraft]:
    """Расшифровка с заголовками записей: документ на запись. Дата из имени аудиофайла,
    иначе из имени файла."""
    docs = _segment_documents(file_name, text, segments, content, "line", None, default)
    file_date = splitters.find_date(Path(file_name).stem)
    for doc, seg in zip(docs, segments):
        stem = Path(file_name).stem
        doc.title = f"{stem} · {seg.header_label}" if len(segments) > 1 and seg.header_label else stem
        if doc.doc_date is None and file_date:
            doc.doc_date, doc.doc_date_precision, doc.date_source = file_date, "day", "filename"
        elif doc.doc_date and file_date and doc.doc_date != file_date and len(segments) == 1:
            doc.notes.append(
                note("date_mismatch", f"дата в имени файла {file_date:%d.%m.%Y} не совпадает с датой записи")
            )
        if doc.doc_date is None:
            doc.notes.append(note("missing_date", "дата документа не указана"))
    return docs


def _from_table(
    file_name: str, data: bytes, content: Content, aliases: list[str], draft: FileDraft, rule_doc_type: str
) -> None:
    parsed = questionnaires.parse_table(file_name, data, content, aliases)
    draft.issues.extend(parsed.issues)
    draft.unmapped_columns = parsed.unmapped_columns
    draft.skipped_rows = parsed.skipped_rows
    if not parsed.responses:
        return

    parts, fragments, measurements = [], [], []
    offset = 0
    for ordinal, resp in enumerate(parsed.responses):
        heading = f"Строка {resp.sheet_row}"
        if resp.timestamp:
            heading += f" · {resp.timestamp:%d.%m.%Y %H:%M}"
        if resp.alias:
            heading += f" · {resp.alias}"
        block = "\n".join([heading] + [f"{h}: {v}" for h, v in resp.cells])
        if parts:
            offset += 2  # пустая строка между блоками
        fragments.append(
            FragmentDraft(
                "table_row",
                offset,
                offset + len(block),
                {
                    "sheet_row": resp.sheet_row,
                    "timestamp": resp.timestamp.isoformat() if resp.timestamp else None,
                    "extras": resp.extras,
                    "issues": resp.issues,
                },
            )
        )
        parts.append(block)
        offset += len(block)
        stamp = resp.timestamp.isoformat() if resp.timestamp else f"row{resp.sheet_row}"
        for code, result in resp.instruments.items():
            measurements.append(
                MeasurementDraft(f"{file_name}#{stamp}#{code}", ordinal, resp.timestamp, result)
            )

    text = "\n\n".join(parts)
    dates = [r.timestamp.date() for r in parsed.responses if r.timestamp]
    notes = [note("table_issue", f"{m.result.code}, строка {parsed.responses[m.fragment_ordinal].sheet_row}: {i}")
             for m in measurements for i in m.result.issues]
    notes += [note("table_issue", f"строка {r.sheet_row}: {i}") for r in parsed.responses for i in r.issues]
    draft.text = text
    draft.documents.append(
        DocumentDraft(
            logical_key=file_name,
            doc_type=rule_doc_type,
            specialty=None,
            title=Path(file_name).stem,
            doc_date=min(dates) if dates else None,
            doc_date_precision="day" if dates else "unknown",
            date_source="table" if dates else "none",
            text=text,
            source_start=0,
            source_end=len(text),
            fragments=fragments,
            notes=notes,
            measurements=measurements,
        )
    )


def _single_document(
    file_name: str, text: str, doc_type: str, specialty: str | None, kind: str, notes: list[dict]
) -> DocumentDraft:
    doc_date, date_source, date_notes = _single_document_date(file_name, text)
    start = len(text) - len(text.lstrip())
    end = len(text.rstrip())
    body = text[start:end]
    return DocumentDraft(
        logical_key=file_name,
        doc_type=doc_type,
        specialty=specialty,
        title=Path(file_name).stem,
        doc_date=doc_date,
        doc_date_precision="day" if doc_date else "unknown",
        date_source=date_source,
        text=body,
        source_start=start,
        source_end=end,
        fragments=[FragmentDraft(s.kind, s.start, s.end) for s in splitters.line_spans(body, kind)],
        notes=date_notes + notes,
    )


def build_file_draft(
    file_name: str,
    data: bytes,
    content: Content,
    aliases: list[str] | None = None,
) -> FileDraft:
    rule = content.match_file(file_name)
    draft = FileDraft(file_name=file_name, splitter=rule.splitter if rule else None)

    if rule and rule.splitter == "table":
        try:
            _from_table(file_name, data, content, aliases or [], draft, rule.doc_type or "unknown")
        except ValueError as e:
            draft.issues.append(f"не удалось прочитать таблицу: {e}")
        return draft

    try:
        text = readers.read_document_text(file_name, data)
    except ValueError as e:  # ReadError и ошибки декодирования
        draft.issues.append(str(e))
        return draft
    draft.text = text

    if rule is None:
        # По имени не распознан: пробуем по началу текста
        rule = content.match_text(text)
    if rule is None:
        # Файл всё равно сохраняется, вид документа врач укажет вручную
        draft.splitter = "paragraphs"
        draft.documents.append(
            _single_document(
                file_name, text, "unknown", None, "paragraph",
                [note("unknown_doc_type", "вид документа не распознан ни по имени файла, ни по началу текста")],
            )
        )
        return draft
    draft.splitter = rule.splitter

    doc_type = rule.doc_type or "unknown"
    if rule.splitter == "dated_headers":
        draft.documents = _from_dated_headers(file_name, text, content)
        return draft

    if rule.splitter == "lines":
        recordings = splitters.split_recordings(text)
        if recordings:
            draft.documents = _from_recordings(file_name, text, recordings, content, (doc_type, rule.specialty))
            return draft

    notes = [note("unknown_doc_type", "вид документа не определён")] if doc_type == "unknown" else []
    kind = "line" if rule.splitter == "lines" else "paragraph"
    draft.documents.append(_single_document(file_name, text, doc_type, rule.specialty, kind, notes))
    return draft
