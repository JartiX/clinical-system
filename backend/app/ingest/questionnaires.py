"""Таблицы опросников в виде «одна строка — одно заполнение» (выгрузка Google Forms).

Колонки распознаются по тексту заголовка: формулировки пунктов из
instrument_items.csv, служебные колонки из table_columns.csv. В одном файле
может быть несколько опросников (одна форма на два опросника). Ответы —
текстовые подписи, баллы берутся из answer_scales.csv.
"""

import csv
import io
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from ..content import Content, normalize

_EXCEL_EPOCH = datetime(1899, 12, 30)
_TS_FORMATS = ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d")


@dataclass
class ItemAnswer:
    item_no: int
    header: str
    answer: str | None
    score: int | None


@dataclass
class InstrumentResult:
    code: str
    answers: list[ItemAnswer] = field(default_factory=list)
    total: int | None = None
    stated_total: int | None = None
    issues: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return all(a.answer is not None for a in self.answers)


@dataclass
class TableResponse:
    sheet_row: int
    timestamp: datetime | None
    alias: str | None
    cells: list[tuple[str, str]]
    instruments: dict[str, InstrumentResult]
    extras: dict[str, str]
    issues: list[str] = field(default_factory=list)


@dataclass
class ParsedTable:
    responses: list[TableResponse]
    instruments: list[str]
    unmapped_columns: list[str]
    skipped_rows: list[str]
    issues: list[str]


def _is_blank(value) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value)) or str(value).strip() == ""


def _to_timestamp(value) -> datetime | None:
    if _is_blank(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        return (_EXCEL_EPOCH + timedelta(days=float(value))).replace(microsecond=0)
    text = str(value).strip()
    try:
        return _to_timestamp(float(text.replace(",", ".")))
    except ValueError:
        pass
    for fmt in _TS_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _display(value) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


class TableError(ValueError):
    pass


def _read_csv(data: bytes) -> pd.DataFrame:
    """Строки выгрузки бывают длиннее заголовка за счёт пустых полей в конце: их
    отбрасываем. Иначе pandas сделал бы лишние поля индексом и сдвинул колонки."""
    rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"), newline="")))
    if not rows:
        return pd.DataFrame()
    header, body = rows[0], []
    for line_no, row in enumerate(rows[1:], start=2):
        extra = row[len(header):]
        if any(v.strip() for v in extra):
            raise TableError(f"строка {line_no}: значений больше, чем колонок в заголовке")
        row = row[: len(header)] + [""] * (len(header) - len(row))
        body.append([v if v.strip() else None for v in row])
    return pd.DataFrame(body, columns=header, dtype=object)


def read_table(file_name: str, data: bytes) -> pd.DataFrame:
    if Path(file_name).suffix.lower() == ".csv":
        df = _read_csv(data)
    else:
        df = pd.read_excel(io.BytesIO(data), dtype=object)
    return df.dropna(how="all")


def _alias_column(headers: list[str], content: Content) -> int | None:
    for col, header in enumerate(headers):
        role = content.column_roles.get(normalize(header))
        if role and role.role == "patient_alias":
            return col
    return None


@dataclass
class TableNames:
    has_name_column: bool
    names: list[tuple[str, int]]  # (имя, сколько строк) в порядке первого появления
    unnamed_rows: int


def table_names(file_name: str, data: bytes, content: Content) -> TableNames:
    """Имена из колонки имени — чтобы выбрать пациента до загрузки, не открывая таблицу."""
    df = read_table(file_name, data)
    col = _alias_column([str(c).strip() for c in df.columns], content)
    if col is None:
        return TableNames(False, [], len(df))
    counts: dict[str, int] = {}
    shown: dict[str, str] = {}
    unnamed = 0
    for value in df.iloc[:, col]:
        if _is_blank(value):
            unnamed += 1
            continue
        name = _display(value)
        key = normalize(name)
        shown.setdefault(key, name)
        counts[key] = counts.get(key, 0) + 1
    return TableNames(True, [(shown[k], n) for k, n in counts.items()], unnamed)


def parse_table(file_name: str, data: bytes, content: Content, aliases: list[str]) -> ParsedTable:
    df = read_table(file_name, data)
    headers = [str(c).strip() for c in df.columns]

    item_cols: dict[str, list[tuple[int, int, str]]] = {}  # опросник -> [(колонка, номер пункта, заголовок)]
    role_cols: dict[str, list[tuple[int, str | None]]] = {}
    unmapped = []
    for col, header in enumerate(headers):
        key = normalize(header)
        if key in content.item_index:
            code, no = content.item_index[key]
            item_cols.setdefault(code, []).append((col, no, header))
        elif key in content.column_roles:
            role = content.column_roles[key]
            role_cols.setdefault(role.role, []).append((col, role.instrument))
        elif not header.lower().startswith("unnamed"):
            unmapped.append(header)

    issues = []
    for code, cols in item_cols.items():
        expected = content.instruments[code].item_count
        if len(cols) != expected:
            issues.append(f"{code}: найдено {len(cols)} пунктов из {expected}")
    if not item_cols:
        issues.append("ни одна колонка не совпала с пунктами известных опросников")

    alias_keys = {normalize(a) for a in aliases}
    ts_col = role_cols.get("timestamp", [(None, None)])[0][0]
    alias_col = role_cols.get("patient_alias", [(None, None)])[0][0]

    responses, skipped = [], []
    for row_pos, row in enumerate(df.itertuples(index=False), start=2):
        values = list(row)
        alias = None if alias_col is None or _is_blank(values[alias_col]) else _display(values[alias_col])
        if alias_keys and (alias is None or normalize(alias) not in alias_keys):
            skipped.append(f"строка {row_pos}: имя «{alias or ''}» не относится к пациенту")
            continue

        ts = None if ts_col is None else _to_timestamp(values[ts_col])
        resp = TableResponse(
            sheet_row=row_pos,
            timestamp=ts,
            alias=alias,
            cells=[],
            instruments={},
            extras={},
        )
        if ts is None:
            resp.issues.append("нет отметки времени")
        for col, header in enumerate(headers):
            if not _is_blank(values[col]):
                shown = ts.isoformat(sep=" ") if col == ts_col and ts else _display(values[col])
                resp.cells.append((header, shown))
        for col, _ in role_cols.get("extra", []):
            if not _is_blank(values[col]):
                resp.extras[headers[col]] = _display(values[col])

        for code, cols in item_cols.items():
            inst = content.instruments[code]
            scale = content.answer_scales.get(inst.answer_scale or "", {})
            result = InstrumentResult(code=code)
            for col, no, header in sorted(cols, key=lambda c: c[1]):
                raw = values[col]
                if _is_blank(raw):
                    result.answers.append(ItemAnswer(no, header, None, None))
                    result.issues.append(f"пункт {no}: нет ответа")
                    continue
                answer = _display(raw)
                hit = scale.get(normalize(answer))
                if scale and hit is None:
                    result.issues.append(f"пункт {no}: ответ «{answer}» не из шкалы {inst.answer_scale}")
                result.answers.append(ItemAnswer(no, header, answer, hit[1] if hit else None))

            scores = [a.score for a in result.answers]
            if inst.scoring == "sum" and len(scores) == inst.item_count and None not in scores:
                result.total = sum(scores)
            elif result.complete and not result.issues:
                result.issues.append("ключ подсчёта не задан: сумма не рассчитана")

            for col, target in role_cols.get("stated_total", []):
                if target == code and not _is_blank(values[col]):
                    try:
                        result.stated_total = int(float(values[col]))
                    except (TypeError, ValueError):
                        result.issues.append(f"сумма в таблице «{values[col]}» не число")
            if result.stated_total is not None and result.total is not None and result.stated_total != result.total:
                result.issues.append(
                    f"сумма в таблице {result.stated_total} не совпадает с расчётной {result.total}"
                )
            resp.instruments[code] = result
        responses.append(resp)

    if aliases and not responses:
        issues.append("нет строк, относящихся к пациенту")
    return ParsedTable(
        responses=responses,
        instruments=sorted(item_cols),
        unmapped_columns=unmapped,
        skipped_rows=skipped,
        issues=issues,
    )
