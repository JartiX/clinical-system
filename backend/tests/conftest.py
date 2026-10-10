"""Общие фикстуры. Все тестовые данные синтетические и строятся в коде."""

import io
import os
from collections.abc import Iterator

import pytest
from openpyxl import Workbook
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app import models  # noqa: F401  регистрирует таблицы
from app.content import Content, load_content
from app.db import Base
from app.vocabulary import sync_vocabulary

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://clinical:clinical@localhost:55440/clinical_test"
)


@pytest.fixture(scope="session")
def content() -> Content:
    return load_content()


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(TEST_DATABASE_URL)
    try:
        with eng.connect():
            pass
    except OperationalError:
        pytest.skip(f"тестовая БД недоступна: {TEST_DATABASE_URL} (docker compose up -d db)")
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine, content) -> Iterator[Session]:
    with engine.begin() as conn:
        names = ", ".join(t.name for t in Base.metadata.sorted_tables)
        conn.execute(text(f"TRUNCATE {names} CASCADE"))
    with sessionmaker(bind=engine, expire_on_commit=False)() as s:
        sync_vocabulary(s, content)
        s.commit()
        yield s


def make_form_xlsx(content: Content, rows: list[dict], instruments: list[str], extra_headers: list[str] = ()) -> bytes:
    """Таблица в виде выгрузки формы: метка времени, имя, пункты опросников.

    rows: [{"ts": datetime | float, "name": str, "answers": {(код, номер): подпись}, "extra": {заголовок: значение}}]
    """
    columns = []
    for code in instruments:
        inst = content.instruments[code]
        columns += [(code, no, inst.items[no]) for no in sorted(inst.items)]
    wb = Workbook()
    ws = wb.active
    ws.append(["Отметка времени", "Имя"] + [c[2] for c in columns] + list(extra_headers))
    for r in rows:
        ws.append(
            [r["ts"], r["name"]]
            + [r["answers"].get((c[0], c[1])) for c in columns]
            + [r.get("extra", {}).get(h) for h in extra_headers]
        )
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def scale_labels(content: Content, code: str) -> list[str]:
    """Подписи шкалы ответов опросника по возрастанию балла."""
    scale = content.answer_scales[content.instruments[code].answer_scale]
    return [label for label, score in sorted(scale.values(), key=lambda x: x[1] or 0)]
