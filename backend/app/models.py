"""Модель данных М1.

По ТЗ три слоя; здесь слой данных: пациенты, файлы, документы, фрагменты,
факты с происхождением. Слои знаний и рассуждения (правила, гипотезы)
добавляются в М4 и М5.

Клинические понятия в код не зашиты: колонки *_type, *_status и specialty
хранят коды из таблицы `vocabulary`, которая загружается из content/vocabulary.csv.

Версии: документы и факты не изменяются на месте. Изменение создаёт новую
строку с тем же `logical_key`, `version + 1` и `supersedes_id` на прежнюю;
у прежней строки `is_current = false`.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class VocabularyEntry(Base):
    """Строка справочника: новое понятие — новая строка, а не новый код."""

    __tablename__ = "vocabulary"
    __table_args__ = (UniqueConstraint("kind", "code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(64))
    code: Mapped[str] = mapped_column(String(128))
    label: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    # синонимы, внешние коды (МКБ-10, АТХ, LOINC), подсказки для показа
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict)


class Patient(Base):
    __tablename__ = "patient"

    id: Mapped[uuid.UUID] = _uuid_pk()
    code: Mapped[str] = mapped_column(String(128), unique=True)
    data_class: Mapped[str] = mapped_column(String(32))
    # имена пациента в исходных файлах (например, колонка «Имя» в опроснике)
    aliases: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = _created_at()

    documents: Mapped[list["Document"]] = relationship(back_populates="patient")


class IngestionRun(Base):
    """prov:Activity — действие над данными пациента: приём файлов или ручная правка."""

    __tablename__ = "ingestion_run"

    id: Mapped[uuid.UUID] = _uuid_pk()
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patient.id"))
    # ingest — приём файлов, manual_edit — правка в интерфейсе,
    # retract / restore / delete — отзыв, возврат и удаление файла
    kind: Mapped[str] = mapped_column(String(32), default="ingest", server_default="ingest")
    agent: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="running")
    started_at: Mapped[datetime] = _created_at()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    report: Mapped[dict] = mapped_column(JSONB, default=dict)


class SourceFile(Base):
    """prov:Entity — файл в том виде, в каком получен. Позиции цитат считаются по `text`."""

    __tablename__ = "source_file"
    __table_args__ = (UniqueConstraint("patient_id", "sha256"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patient.id"))
    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingestion_run.id"))
    file_name: Mapped[str] = mapped_column(Text)
    media_type: Mapped[str] = mapped_column(String(128))
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)
    content: Mapped[bytes] = mapped_column(LargeBinary)
    # декодированный текст с приведёнными переводами строк; NULL для таблиц
    text: Mapped[str | None] = mapped_column(Text)
    data_class: Mapped[str] = mapped_column(String(32))
    received_at: Mapped[datetime] = _created_at()
    # active — используется; retracted — отозван (документы и факты из него не текущие)
    status: Mapped[str] = mapped_column(String(32), default="active", server_default="active")
    status_reason: Mapped[str | None] = mapped_column(Text)
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Document(Base):
    __tablename__ = "document"
    __table_args__ = (
        UniqueConstraint("patient_id", "logical_key", "version"),
        Index("ix_document_patient_current", "patient_id", "is_current"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patient.id"))
    source_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_file.id"))
    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingestion_run.id"))

    logical_key: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("document.id"))

    doc_type: Mapped[str] = mapped_column(String(128))
    author_specialty: Mapped[str | None] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(Text)
    doc_date: Mapped[date | None] = mapped_column(Date)
    doc_date_precision: Mapped[str] = mapped_column(String(32), default="unknown")
    # откуда дата: filename | header | table | manual | none
    date_source: Mapped[str] = mapped_column(String(32), default="none")
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    review_notes: Mapped[list] = mapped_column(JSONB, default=list)

    text: Mapped[str] = mapped_column(Text)
    # границы документа внутри source_file.text (в нарезанном файле много документов)
    source_start: Mapped[int] = mapped_column(Integer, default=0)
    source_end: Mapped[int] = mapped_column(Integer, default=0)

    data_class: Mapped[str] = mapped_column(String(32))
    # pending | done | failed — состояние извлечения для М3
    extraction_status: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime] = _created_at()

    patient: Mapped[Patient] = relationship(back_populates="documents")
    source_file: Mapped[SourceFile] = relationship()
    fragments: Mapped[list["Fragment"]] = relationship(
        back_populates="document", order_by="Fragment.ordinal", cascade="all, delete-orphan"
    )


class Fragment(Base):
    """Адресуемая часть документа: абзац, строка беседы или строка таблицы."""

    __tablename__ = "fragment"
    __table_args__ = (UniqueConstraint("document_id", "ordinal"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document.id"))
    ordinal: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text)
    # позиции внутри document.text
    start_offset: Mapped[int] = mapped_column(Integer)
    end_offset: Mapped[int] = mapped_column(Integer)
    speaker: Mapped[str | None] = mapped_column(String(64))
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict)

    document: Mapped[Document] = relationship(back_populates="fragments")


class Fact(Base):
    """Любое утверждение о пациенте. Измерения по опросникам — тоже факты."""

    __tablename__ = "fact"
    __table_args__ = (
        UniqueConstraint("patient_id", "logical_key", "version"),
        Index("ix_fact_patient_current", "patient_id", "is_current"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patient.id"))
    ingestion_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ingestion_run.id"))

    logical_key: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fact.id"))

    fact_type: Mapped[str] = mapped_column(String(128))
    code: Mapped[str | None] = mapped_column(String(128))
    value: Mapped[dict] = mapped_column(JSONB, default=dict)
    negated: Mapped[bool] = mapped_column(Boolean, default=False)

    # когда произошло (с точностью) и когда стало известно (дата документа)
    occurred_start: Mapped[date | None] = mapped_column(Date)
    occurred_end: Mapped[date | None] = mapped_column(Date)
    occurred_precision: Mapped[str] = mapped_column(String(32), default="unknown")
    known_at: Mapped[date | None] = mapped_column(Date)

    epistemic_status: Mapped[str] = mapped_column(String(64))
    confirmation_status: Mapped[str] = mapped_column(String(64), default="unconfirmed")
    data_class: Mapped[str] = mapped_column(String(32))
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = _created_at()

    sources: Mapped[list["FactSource"]] = relationship(
        back_populates="fact", cascade="all, delete-orphan"
    )


class FactSource(Base):
    """Связь факта с точной цитатой, на которой он основан."""

    __tablename__ = "fact_source"

    id: Mapped[uuid.UUID] = _uuid_pk()
    fact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("fact.id"))
    fragment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("fragment.id"))
    # позиции внутри document.text документа, к которому относится фрагмент
    quote_start: Mapped[int] = mapped_column(Integer)
    quote_end: Mapped[int] = mapped_column(Integer)
    quote: Mapped[str] = mapped_column(Text)

    fact: Mapped[Fact] = relationship(back_populates="sources")
    fragment: Mapped[Fragment] = relationship()
