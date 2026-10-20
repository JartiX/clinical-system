"""Нарезка текста на документы и документов на адресуемые фрагменты.

Все позиции — номера символов в том тексте, по которому посчитаны, поэтому
цитату всегда можно открыть на своём месте.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime

# Визит начинается со строки вида «20190718_Специальность»
DATED_HEADER = re.compile(r"^(?P<date>\d{8})_(?P<label>[^\n]*)$", re.MULTILINE)
# Запись в выгрузке медкарты: «05.06.2026 14:19 : Дневник»; дата бывает пустой («: Консультация»)
ENTRY_HEADER = re.compile(
    r"^(?:(?P<date>\d{2}\.\d{2}\.\d{4})(?: \d{1,2}:\d{2})? )?: (?P<label>[^\n]*\S)[ \t]*$", re.MULTILINE
)
# Запись диктофона в расшифровке: строка «Заголовок: 20250903_110011.m4a», под ней «=====»
RECORDING_HEADER = re.compile(r"^Заголовок: (?P<label>[^\n]*\S)[ \t]*\n=+[ \t]*$", re.MULTILINE)

# Виды строк визита по порядку проверки: берётся первый, который встретился в тексте
_HEADER_STYLES = [(DATED_HEADER, "%Y%m%d"), (ENTRY_HEADER, "%d.%m.%Y")]


# Месяц словом: «29» октября 2024г., " 17 " июля 20 24 г.
_MONTHS = {"янв": 1, "фев": 2, "мар": 3, "апр": 4, "мая": 5, "май": 5, "июн": 6,
           "июл": 7, "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12}
_MONTH_WORDS = r"(январ[яь]|феврал[яь]|марта?|апрел[яь]|ма[яй]|июн[яь]|июл[яь]|августа?|сентябр[яь]|октябр[яь]|ноябр[яь]|декабр[яь])"

# Сколько непустых строк должно пройти после заголовка раздела, чтобы следующий заголовок
# начал новый документ: «Отделение №:» сразу под «ВЫПИСНОЙ ЭПИКРИЗ» — тот же документ
MIN_SECTION_LINES = 8


def _two_digit_year(yy: str) -> str:
    year = 2000 + int(yy)
    return str(year if year <= date.today().year else year - 100)


_DATE_PATTERNS = [
    (re.compile(r"(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)"), lambda m: (m[1], m[2], m[3])),
    (re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)"), lambda m: (m[1], m[2], m[3])),
    (re.compile(r"(?<!\d)(\d{2})\.(\d{2})\.(\d{4})(?!\d)"), lambda m: (m[3], m[2], m[1])),
    (re.compile(r"(?<!\d)(\d{2})-(\d{2})-(\d{4})(?!\d)"), lambda m: (m[3], m[2], m[1])),
    (re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{4})(?!\d)"), lambda m: (m[3], m[2], m[1])),
    (re.compile(r"(?<![\d.])(\d{2})\.(\d{2})\.(\d{2})(?!\d)"), lambda m: (_two_digit_year(m[3]), m[2], m[1])),
    (
        re.compile(r"(?<!\d)[\"«]?\s*(\d{1,2})\s*[\"»]?\s+" + _MONTH_WORDS + r"\s+(\d{2}) ?(\d{2})(?!\d)", re.IGNORECASE),
        lambda m: (m[3] + m[4], str(_MONTHS[m[2][:3].lower()]), m[1]),
    ),
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


def _valid_date(y: str, mo: str, d: str) -> date | None:
    if not 1900 <= int(y) <= 2100:
        return None
    try:
        return date(int(y), int(mo), int(d))
    except ValueError:
        return None


def find_date(text: str) -> date | None:
    """Первая корректная дата. Форматы проверяются по порядку: ГГГГММДД, ГГГГ-ММ-ДД,
    ДД.ММ.ГГГГ, ДД-ММ-ГГГГ, ДДММГГГГ, ДД.ММ.ГГ."""
    for pattern, parts in _DATE_PATTERNS:
        for m in pattern.finditer(text):
            found = _valid_date(*parts(m))
            if found:
                return found
    return None


def find_dates(text: str) -> list[date]:
    """Все корректные даты в тексте, в любом из форматов find_date."""
    dates = []
    for pattern, parts in _DATE_PATTERNS:
        for m in pattern.finditer(text):
            found = _valid_date(*parts(m))
            if found:
                dates.append(found)
    return dates


def _rstrip_end(text: str, start: int, end: int) -> int:
    while end > start and text[end - 1].isspace():
        end -= 1
    return end


def _split(text: str, matches: list[re.Match], date_of) -> list[Segment]:
    """Сегмент на каждую строку-заголовок; текст до первой — отдельным сегментом без заголовка."""
    segments = []
    first = matches[0].start()
    if text[:first].strip():
        segments.append(Segment(0, _rstrip_end(text, 0, first), issues=[("orphan_text", "текст до первой строки с датой")]))
    for i, m in enumerate(matches):
        nxt = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        seg = Segment(m.start(), _rstrip_end(text, m.start(), nxt), header_label=m["label"].strip())
        seg.header_date = date_of(m, seg)
        segments.append(seg)
    return segments


def split_dated_headers(text: str) -> list[Segment]:
    for pattern, fmt in _HEADER_STYLES:
        matches = list(pattern.finditer(text))
        if matches:
            break
    else:
        return [Segment(0, _rstrip_end(text, 0, len(text)), issues=[("no_visit_headers", "не найдено строк с датой визита")])]

    def date_of(m: re.Match, seg: Segment) -> date | None:
        if not m["date"]:
            seg.issues.append(("missing_header_date", f"нет даты в строке «{m.group(0).strip()}»"))
            return None
        try:
            return datetime.strptime(m["date"], fmt).date()
        except ValueError:
            seg.issues.append(("invalid_header_date", f"неверная дата в строке «{m.group(0).strip()}»"))
            return None

    return _split(text, matches, date_of)


def split_recordings(text: str) -> list[Segment] | None:
    """Расшифровка нескольких записей в одном файле; None, если строк «Заголовок:» нет.
    Дата записи берётся из имени аудиофайла."""
    matches = list(RECORDING_HEADER.finditer(text))
    if not matches:
        return None
    return _split(text, matches, lambda m, seg: find_date(m["label"]))


def split_sections(text: str, is_start: Callable[[str], bool]) -> list[Segment] | None:
    """Сводный файл без строк визита: документ начинается со строки-заголовка
    (is_start); None, если таких строк нет."""
    starts: list[tuple[int, str]] = []
    pos, since = 0, 0
    for line in text.split("\n"):
        if line.strip():
            if is_start(line) and (not starts or since >= MIN_SECTION_LINES):
                starts.append((pos, line.strip()))
                since = 0
            since += 1
        pos += len(line) + 1
    if not starts:
        return None
    segments = []
    if text[: starts[0][0]].strip():
        first = starts[0][0]
        segments.append(Segment(0, _rstrip_end(text, 0, first), issues=[("orphan_text", "текст до первого заголовка")]))
    for i, (start, label) in enumerate(starts):
        nxt = starts[i + 1][0] if i + 1 < len(starts) else len(text)
        segments.append(Segment(start, _rstrip_end(text, start, nxt), header_label=label))
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
