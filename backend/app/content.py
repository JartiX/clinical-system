"""Загрузка таблиц содержания (content/*.csv): справочники, правила файлов и заголовков, опросники.

Содержание — данные, а не код: новый вид документа, вариант заголовка или
новый опросник добавляются строками. Каждая таблица проверяется при загрузке,
ошибка указывает файл и строку.
"""

import csv
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .config import settings

SPLITTERS = {"dated_headers", "lines", "paragraphs", "table"}
RULE_MATCH = {"name", "text"}
SCORINGS = {"sum"}
COLUMN_ROLES = {"timestamp", "patient_alias", "stated_total", "extra"}


class ContentError(ValueError):
    pass


def normalize(text: str) -> str:
    """Ключ сравнения подписей: без учёта регистра, ё/е, кавычек и пробелов."""
    text = unicodedata.normalize("NFKC", text).lower().replace("ё", "е")
    text = text.replace("_", " ").replace("«", '"').replace("»", '"')
    return re.sub(r"\s+", " ", text).strip()


@dataclass(frozen=True)
class VocabularyRow:
    kind: str
    code: str
    label: str
    description: str | None


@dataclass(frozen=True)
class FileRule:
    pattern: re.Pattern
    doc_type: str | None
    specialty: str | None
    splitter: str
    # где искать образец: в имени файла или в первых строках текста
    match: str = "name"


@dataclass(frozen=True)
class HeaderRule:
    pattern: re.Pattern
    doc_type: str
    specialty: str | None
    # название документа вместо строки-заголовка (section_rules, колонка title)
    title: str | None = None


@dataclass
class Instrument:
    code: str
    name: str
    answer_scale: str | None
    scoring: str | None
    item_count: int
    loinc_total: str | None
    items: dict[int, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ColumnRole:
    role: str
    instrument: str | None


@dataclass
class Content:
    vocabulary: list[VocabularyRow]
    file_rules: list[FileRule]
    header_rules: list[HeaderRule]
    # строки, с которых начинается документ внутри сводного файла без строк визита
    section_rules: list[HeaderRule]
    instruments: dict[str, Instrument]
    # шкала -> нормализованная подпись -> (подпись, балл или None, если ключ не задан)
    answer_scales: dict[str, dict[str, tuple[str, int | None]]]
    # нормализованный заголовок -> роль колонки
    column_roles: dict[str, ColumnRole]
    # нормализованный текст пункта -> (код опросника, номер пункта)
    item_index: dict[str, tuple[str, int]]

    def codes(self, kind: str) -> set[str]:
        return {v.code for v in self.vocabulary if v.kind == kind}

    def label(self, kind: str, code: str | None) -> str | None:
        for v in self.vocabulary:
            if v.kind == kind and v.code == code:
                return v.label
        return code

    def match_file(self, file_name: str) -> FileRule | None:
        name = normalize(file_name)
        return next((r for r in self.file_rules if r.match == "name" and r.pattern.search(name)), None)

    def match_text(self, text: str, lines: int = 5) -> FileRule | None:
        """Правило по началу текста: первые непустые строки, каждая отдельно."""
        head = [normalize(s) for s in text.split("\n") if s.strip()][:lines]
        return next(
            (r for r in self.file_rules if r.match == "text" and any(r.pattern.search(s) for s in head)),
            None,
        )

    def match_header(self, label: str) -> HeaderRule | None:
        key = normalize(label)
        return next((r for r in self.header_rules if r.pattern.search(key)), None)

    def match_section(self, line: str) -> HeaderRule | None:
        key = normalize(line)
        return next((r for r in self.section_rules if r.pattern.search(key)), None) if key else None


def _rows(path: Path, required: list[str]):
    if not path.exists():
        raise ContentError(f"{path.name}: файл не найден")
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in required if c not in (reader.fieldnames or [])]
        if missing:
            raise ContentError(f"{path.name}: нет колонок {missing}")
        for line_no, row in enumerate(reader, start=2):
            if None in row:
                raise ContentError(f"{path.name}:{line_no}: лишние значения в строке (кавычки?)")
            yield line_no, {k: (v or "").strip() for k, v in row.items()}


def _regex(value: str, where: str) -> re.Pattern:
    try:
        return re.compile(normalize(value))
    except re.error as e:
        raise ContentError(f"{where}: неверное регулярное выражение: {e}") from e


def load_content(content_dir: Path | None = None) -> Content:
    d = Path(content_dir or settings.content_dir)

    vocabulary = [
        VocabularyRow(r["kind"], r["code"], r["label"], r.get("description") or None)
        for _, r in _rows(d / "vocabulary.csv", ["kind", "code", "label"])
    ]
    doc_types = {v.code for v in vocabulary if v.kind == "document_type"}
    specialties = {v.code for v in vocabulary if v.kind == "specialty"}

    def check_code(value: str, allowed: set[str], what: str, where: str) -> str | None:
        if not value:
            return None
        if value not in allowed:
            raise ContentError(f"{where}: {what} '{value}' нет в vocabulary.csv")
        return value

    file_rules = []
    for ln, r in _rows(d / "file_rules.csv", ["pattern", "doc_type", "specialty", "splitter"]):
        where = f"file_rules.csv:{ln}"
        if r["splitter"] not in SPLITTERS:
            raise ContentError(f"{where}: splitter '{r['splitter']}' не из {sorted(SPLITTERS)}")
        match = r.get("match") or "name"
        if match not in RULE_MATCH:
            raise ContentError(f"{where}: match '{match}' не из {sorted(RULE_MATCH)}")
        file_rules.append(
            FileRule(
                _regex(r["pattern"], where),
                check_code(r["doc_type"], doc_types, "doc_type", where),
                check_code(r["specialty"], specialties, "specialty", where),
                r["splitter"],
                match,
            )
        )

    def label_rules(file_name: str) -> list[HeaderRule]:
        rules = []
        for ln, r in _rows(d / file_name, ["pattern", "doc_type", "specialty"]):
            where = f"{file_name}:{ln}"
            rules.append(
                HeaderRule(
                    _regex(r["pattern"], where),
                    check_code(r["doc_type"], doc_types, "doc_type", where) or "unknown",
                    check_code(r["specialty"], specialties, "specialty", where),
                    r.get("title") or None,
                )
            )
        return rules

    header_rules = label_rules("header_rules.csv")
    section_rules = label_rules("section_rules.csv")

    answer_scales: dict[str, dict[str, tuple[str, int | None]]] = {}
    for ln, r in _rows(d / "answer_scales.csv", ["scale", "label", "score"]):
        where = f"answer_scales.csv:{ln}"
        try:
            score = int(r["score"]) if r["score"] else None
        except ValueError as e:
            raise ContentError(f"{where}: балл '{r['score']}' не целое число") from e
        answer_scales.setdefault(r["scale"], {})[normalize(r["label"])] = (r["label"], score)

    instruments: dict[str, Instrument] = {}
    for ln, r in _rows(
        d / "instruments.csv", ["code", "name", "answer_scale", "scoring", "item_count"]
    ):
        where = f"instruments.csv:{ln}"
        if r["answer_scale"] and r["answer_scale"] not in answer_scales:
            raise ContentError(f"{where}: шкала ответов '{r['answer_scale']}' не описана")
        if r["scoring"] and r["scoring"] not in SCORINGS:
            raise ContentError(f"{where}: правило подсчёта '{r['scoring']}' не из {SCORINGS}")
        instruments[r["code"]] = Instrument(
            code=r["code"],
            name=r["name"],
            answer_scale=r["answer_scale"] or None,
            scoring=r["scoring"] or None,
            item_count=int(r["item_count"]),
            loinc_total=r.get("loinc_total") or None,
        )

    item_index: dict[str, tuple[str, int]] = {}
    for ln, r in _rows(d / "instrument_items.csv", ["instrument", "item_no", "text"]):
        where = f"instrument_items.csv:{ln}"
        inst = instruments.get(r["instrument"])
        if inst is None:
            raise ContentError(f"{where}: инструмент '{r['instrument']}' не описан")
        no = int(r["item_no"])
        inst.items[no] = r["text"]
        key = normalize(r["text"])
        if key in item_index and item_index[key] != (inst.code, no):
            raise ContentError(f"{where}: формулировка пункта уже занята {item_index[key]}")
        item_index[key] = (inst.code, no)
    for inst in instruments.values():
        if len(inst.items) != inst.item_count:
            raise ContentError(
                f"instruments.csv: у {inst.code} заявлено {inst.item_count} пунктов, "
                f"описано {len(inst.items)}"
            )

    column_roles: dict[str, ColumnRole] = {}
    for ln, r in _rows(d / "table_columns.csv", ["header", "role", "instrument"]):
        where = f"table_columns.csv:{ln}"
        if r["role"] not in COLUMN_ROLES:
            raise ContentError(f"{where}: роль '{r['role']}' не из {sorted(COLUMN_ROLES)}")
        if r["instrument"] and r["instrument"] not in instruments:
            raise ContentError(f"{where}: инструмент '{r['instrument']}' не описан")
        column_roles[normalize(r["header"])] = ColumnRole(r["role"], r["instrument"] or None)

    return Content(
        vocabulary=vocabulary,
        file_rules=file_rules,
        header_rules=header_rules,
        section_rules=section_rules,
        instruments=instruments,
        answer_scales=answer_scales,
        column_roles=column_roles,
        item_index=item_index,
    )


@lru_cache
def get_content() -> Content:
    return load_content()
