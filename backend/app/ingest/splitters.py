"""Нарезка текста на документы и документов на адресуемые фрагменты.

Все позиции — номера символов в том тексте, по которому посчитаны, поэтому
цитату всегда можно открыть на своём месте.
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime

# Визит начинается со строки вида «20190718_Специальность»
DATED_HEADER = re.compile(r"^(?P<date>\d{8})_(?P<label>[^\n]*)$", re.MULTILINE)

_DATE_PATTERNS = [
    (re.compile(r"(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)"), lambda m: (m[1], m[2], m[3])),
    (re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)"), lambda m: (m[1], m[2], m[3])),
    (re.compile(r"(?<!\d)(\d{2})\.(\d{2})\.(\d{4})(?!\d)"), lambda m: (m[3], m[2], m[1])),
]


@dataclass
class Segment:
    start: int
    end: int
    header_date: date | None = None
    header_label: str | None = None
    # замечания: (код, текст)
    issues: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class Span:
    kind: str
    start: int
    end: int


def find_date(text: str) -> date | None:
    """Первая корректная дата в виде ГГГГММДД, ГГГГ-ММ-ДД или ДД.ММ.ГГГГ."""
    for pattern, parts in _DATE_PATTERNS:
        for m in pattern.finditer(text):
            y, mo, d = parts(m)
            try:
                return date(int(y), int(mo), int(d))
            except ValueError:
                continue
    return None


def _rstrip_end(text: str, start: int, end: int) -> int:
    while end > start and text[end - 1].isspace():
        end -= 1
    return end


def split_dated_headers(text: str) -> list[Segment]:
    matches = list(DATED_HEADER.finditer(text))
    if not matches:
        return [Segment(0, _rstrip_end(text, 0, len(text)), issues=[("no_visit_headers", "не найдено строк с датой визита")])]

    segments = []
    first = matches[0].start()
    if text[:first].strip():
        segments.append(Segment(0, _rstrip_end(text, 0, first), issues=[("orphan_text", "текст до первой строки с датой")]))
    for i, m in enumerate(matches):
        nxt = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        seg = Segment(m.start(), _rstrip_end(text, m.start(), nxt), header_label=m["label"].strip())
        try:
            seg.header_date = datetime.strptime(m["date"], "%Y%m%d").date()
        except ValueError:
            seg.issues.append(("invalid_header_date", f"неверная дата в строке «{m.group(0).strip()}»"))
        segments.append(seg)
    return segments


def line_spans(text: str, kind: str, first_kind: str | None = None) -> list[Span]:
    """Один фрагмент на непустую строку; пробелы по краям в границы не входят."""
    spans = []
    pos = 0
    for line in text.split("\n"):
        start = pos + (len(line) - len(line.lstrip()))
        end = pos + len(line.rstrip())
        if end > start:
            spans.append(Span(kind, start, end))
        pos += len(line) + 1
    if first_kind and spans:
        spans[0].kind = first_kind
    return spans
