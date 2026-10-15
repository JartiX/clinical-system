"""Проверки таблиц содержания и принципа «содержание — в таблицах, механизмы — в коде»."""

import re
from pathlib import Path

import pytest

from app.content import ContentError, load_content

APP_DIR = Path(__file__).resolve().parents[1] / "app"


def test_content_loads_and_is_consistent(content):
    assert content.instruments
    for inst in content.instruments.values():
        assert len(inst.items) == inst.item_count


def test_broken_table_points_to_line(tmp_path, content):
    src = Path(__file__).resolve().parents[2] / "content"
    for f in src.glob("*.csv"):
        (tmp_path / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    rules = tmp_path / "file_rules.csv"
    rules.write_text(rules.read_text(encoding="utf-8") + "\\.doc$,no_such_type,,paragraphs,\n", encoding="utf-8")
    with pytest.raises(ContentError, match=r"file_rules\.csv:\d+"):
        load_content(tmp_path)


# Примеры из ТЗ (раздел 11): поиск по коду должен давать пустой результат
TZ_TERMS = ["тревог", "эсциталопрам", "срб"]


def _clinical_terms(content) -> list[str]:
    """Специальности и опросники из таблиц содержания плюс примеры из ТЗ."""
    terms = {v.label for v in content.vocabulary if v.kind == "specialty"}
    terms |= {v.code for v in content.vocabulary if v.kind == "specialty"}
    terms |= {i.name for i in content.instruments.values()} | set(content.instruments)
    return sorted({re.escape(t.lower()) + r"(?!\w)" for t in terms if len(t) >= 4} | set(TZ_TERMS))


def test_no_clinical_terms_in_source_code(content):
    hits = []
    for path in APP_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        for term in _clinical_terms(content):
            if re.search(r"(?<!\w)" + term, text):
                hits.append(f"{path.relative_to(APP_DIR)}: {term}")
    assert not hits, hits
