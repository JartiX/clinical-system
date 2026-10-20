"""Файл -> черновики документов. Чистые функции без БД: легко тестировать и смотреть заранее."""

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from ..content import Content
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


def _from_dated_headers(file_name: str, text: str, content: Content) -> list[DocumentDraft]:
    docs = []
    seen: dict[str, int] = {}
    for seg in splitters.split_dated_headers(text):
        body = text[seg.start : seg.end]
        notes = [note(code, text) for code, text in seg.issues]
        doc_type, specialty = "unknown", None
        if seg.header_label is not None:
            rule = content.match_header(seg.header_label)
            if rule:
                doc_type, specialty = rule.doc_type, rule.specialty
            else:
                notes.append(note("unknown_doc_type", f"вид документа не распознан по строке «{seg.header_label}»"))
        else:
            notes.append(note("orphan_text", "фрагмент без строки визита"))
        stamp = seg.header_date.strftime("%Y%m%d") if seg.header_date else "nodate"
        base = f"{file_name}#{stamp}_{seg.header_label or ''}"
        seen[base] = seen.get(base, 0) + 1
        title = (seg.header_label or Path(file_name).stem).replace("_", " ")
        docs.append(
            DocumentDraft(
                logical_key=f"{base}#{seen[base]}",
                doc_type=doc_type,
                specialty=specialty,
                title=title,
                doc_date=seg.header_date,
                doc_date_precision="day" if seg.header_date else "unknown",
                date_source="header" if seg.header_date else "none",
                text=body,
                source_start=seg.start,
                source_end=seg.end,
                fragments=[
                    FragmentDraft(s.kind, s.start, s.end)
                    for s in splitters.line_spans(
                        body, "paragraph", "header" if seg.header_label is not None else None
                    )
                ],
                notes=notes,
            )
        )
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


def build_file_draft(
    file_name: str,
    data: bytes,
    content: Content,
    aliases: list[str] | None = None,
) -> FileDraft:
    rule = content.match_file(file_name)
    splitter = rule.splitter if rule else None
    draft = FileDraft(file_name=file_name, splitter=splitter)
    if splitter is None:
        draft.issues.append("тип файла не распознан по имени: добавьте правило в content/file_rules.csv")
        return draft

    doc_type = rule.doc_type or "unknown"
    specialty = rule.specialty

    if splitter == "table":
        _from_table(file_name, data, content, aliases or [], draft, doc_type)
        return draft

    try:
        text = readers.read_document_text(file_name, data)
    except readers.ReadError as e:
        draft.issues.append(str(e))
        return draft
    draft.text = text

    if splitter == "dated_headers":
        draft.documents = _from_dated_headers(file_name, text, content)
        return draft

    doc_date, date_source, notes = _single_document_date(file_name, text)
    if doc_type == "unknown":
        notes.append(note("unknown_doc_type", "вид документа не определён"))
    start = len(text) - len(text.lstrip())
    end = len(text.rstrip())
    body = text[start:end]
    kind = "line" if splitter == "lines" else "paragraph"
    draft.documents.append(
        DocumentDraft(
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
            notes=notes,
        )
    )
    return draft
