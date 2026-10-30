"""Выгрузка случая пациента в RDF и проверка SHACL.

Словарь происхождения — PROV-O: исходный файл и документ — prov:Entity,
приём — prov:Activity. Выгружаются текущие версии документов и фактов.
"""

import json
from importlib import resources

from pyshacl import validate
from rdflib import RDF, RDFS, XSD, Graph, Literal, Namespace, URIRef
from rdflib.namespace import PROV
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import settings
from ..models import Document, Fact, Fragment, IngestionRun, Patient, VocabularyEntry

CS = Namespace("https://clinical-system.local/ns#")
ID = Namespace(settings.base_iri.rstrip("/") + "/id/")


def _class_name(kind: str) -> str:
    return "".join(part.capitalize() for part in kind.split("_"))


def _term(kind: str, code: str | None) -> URIRef | None:
    return None if code is None else ID[f"vocab/{kind}/{code}"]


def _iri(obj) -> URIRef:
    return ID[f"{type(obj).__tablename__}/{obj.id}"]


def _add(g: Graph, s, p, o) -> None:
    if o is not None:
        g.add((s, p, o if isinstance(o, (URIRef, Literal)) else Literal(o)))


def export_patient(session: Session, patient_code: str) -> Graph:
    patient = session.scalar(select(Patient).where(Patient.code == patient_code))
    if patient is None:
        raise LookupError(f"пациент {patient_code} не найден")

    g = Graph()
    g.bind("cs", CS)
    g.bind("prov", PROV)
    g.bind("id", ID)

    for v in session.scalars(select(VocabularyEntry)):
        t = _term(v.kind, v.code)
        g.add((t, RDF.type, CS[_class_name(v.kind)]))
        g.add((t, RDFS.label, Literal(v.label, lang="ru")))

    pu = _iri(patient)
    g.add((pu, RDF.type, CS.Patient))
    _add(g, pu, CS.code, patient.code)
    _add(g, pu, CS.dataClass, _term("data_class", patient.data_class))

    runs = set()
    docs = session.scalars(
        select(Document)
        .where(Document.patient_id == patient.id, Document.is_current.is_(True))
        .options(selectinload(Document.fragments), selectinload(Document.source_file))
    ).all()
    for doc in docs:
        du = _iri(doc)
        g.add((du, RDF.type, CS.Document))
        g.add((du, RDF.type, PROV.Entity))
        _add(g, du, CS.patient, pu)
        _add(g, du, CS.title, doc.title)
        _add(g, du, CS.docType, _term("document_type", doc.doc_type))
        _add(g, du, CS.specialty, _term("specialty", doc.author_specialty))
        _add(g, du, CS.dataClass, _term("data_class", doc.data_class))
        if doc.doc_date:
            _add(g, du, CS.docDate, Literal(doc.doc_date, datatype=XSD.date))
        _add(g, du, CS.datePrecision, _term("date_precision", doc.doc_date_precision))
        _add(g, du, CS.version, Literal(doc.version, datatype=XSD.integer))
        _add(g, du, CS.needsReview, Literal(doc.needs_review))
        for note in doc.review_notes:
            _add(g, du, CS.reviewNote, Literal(note, lang="ru"))

        sf = doc.source_file
        su = _iri(sf)
        g.add((su, RDF.type, CS.SourceFile))
        g.add((su, RDF.type, PROV.Entity))
        _add(g, su, CS.fileName, sf.file_name)
        _add(g, su, CS.sha256, sf.sha256)
        _add(g, du, PROV.wasDerivedFrom, su)
        _add(g, du, PROV.wasGeneratedBy, ID[f"ingestion_run/{doc.ingestion_run_id}"])
        runs.add(doc.ingestion_run_id)

        for fr in doc.fragments:
            fu = _iri(fr)
            g.add((fu, RDF.type, CS.Fragment))
            _add(g, fu, CS.document, du)
            _add(g, fu, CS.ordinal, Literal(fr.ordinal, datatype=XSD.integer))
            _add(g, fu, CS.kind, _term("fragment_kind", fr.kind))
            _add(g, fu, CS.startOffset, Literal(fr.start_offset, datatype=XSD.integer))
            _add(g, fu, CS.endOffset, Literal(fr.end_offset, datatype=XSD.integer))

    facts = session.scalars(
        select(Fact)
        .where(Fact.patient_id == patient.id, Fact.is_current.is_(True))
        .options(selectinload(Fact.sources))
    ).all()
    for fact in facts:
        fu = _iri(fact)
        g.add((fu, RDF.type, CS.Fact))
        _add(g, fu, CS.patient, pu)
        _add(g, fu, CS.factType, _term("fact_type", fact.fact_type))
        _add(g, fu, CS.code, fact.code)
        _add(g, fu, CS.value, Literal(json.dumps(fact.value, ensure_ascii=False)))
        _add(g, fu, CS.negated, Literal(fact.negated))
        _add(g, fu, CS.epistemicStatus, _term("epistemic_status", fact.epistemic_status))
        _add(g, fu, CS.confirmationStatus, _term("confirmation_status", fact.confirmation_status))
        _add(g, fu, CS.dataClass, _term("data_class", fact.data_class))
        _add(g, fu, CS.version, Literal(fact.version, datatype=XSD.integer))
        if fact.occurred_start:
            _add(g, fu, CS.occurredStart, Literal(fact.occurred_start, datatype=XSD.date))
        if fact.occurred_end:
            _add(g, fu, CS.occurredEnd, Literal(fact.occurred_end, datatype=XSD.date))
        _add(g, fu, CS.occurredPrecision, _term("date_precision", fact.occurred_precision))
        if fact.known_at:
            _add(g, fu, CS.knownAt, Literal(fact.known_at, datatype=XSD.date))
        if fact.ingestion_run_id:
            _add(g, fu, PROV.wasGeneratedBy, ID[f"ingestion_run/{fact.ingestion_run_id}"])
            runs.add(fact.ingestion_run_id)
        for src in fact.sources:
            srcu = _iri(src)
            g.add((srcu, RDF.type, CS.FactSource))
            _add(g, fu, CS.hasSource, srcu)
            _add(g, srcu, CS.fragment, ID[f"{Fragment.__tablename__}/{src.fragment_id}"])
            _add(g, srcu, CS.quoteStart, Literal(src.quote_start, datatype=XSD.integer))
            _add(g, srcu, CS.quoteEnd, Literal(src.quote_end, datatype=XSD.integer))
            _add(g, srcu, CS.quote, src.quote)

    for run in session.scalars(select(IngestionRun).where(IngestionRun.id.in_(runs))):
        ru = _iri(run)
        g.add((ru, RDF.type, PROV.Activity))
        _add(g, ru, PROV.startedAtTime, Literal(run.started_at, datatype=XSD.dateTime))
        if run.finished_at:
            _add(g, ru, PROV.endedAtTime, Literal(run.finished_at, datatype=XSD.dateTime))
        agent = ID[f"agent/{run.agent}"]
        g.add((agent, RDF.type, PROV.SoftwareAgent))
        _add(g, ru, PROV.wasAssociatedWith, agent)
    return g


def _shapes() -> Graph:
    text = resources.files("app.rdf").joinpath("shapes.ttl").read_text(encoding="utf-8")
    return Graph().parse(data=text, format="turtle")


def validate_graph(g: Graph) -> dict:
    conforms, report_graph, _ = validate(g, shacl_graph=_shapes(), inference="none")
    sh = Namespace("http://www.w3.org/ns/shacl#")
    violations = []
    for r in report_graph.subjects(RDF.type, sh.ValidationResult):
        violations.append(
            {
                "focus": str(report_graph.value(r, sh.focusNode)),
                "path": str(report_graph.value(r, sh.resultPath) or ""),
                "message": str(report_graph.value(r, sh.resultMessage) or ""),
            }
        )
    return {"conforms": bool(conforms), "violations": violations}
