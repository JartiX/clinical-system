"""Командная строка: загрузка содержания, приём папки пациента, выгрузка и проверка графа.

    python -m app.cli load-content
    python -m app.cli ingest "путь/к/папке" --patient-code X --alias Х --data-class deidentified
    python -m app.cli export-rdf X -o case.ttl
    python -m app.cli validate X
"""

import argparse
import json
import sys
from pathlib import Path

from .config import settings
from .content import ContentError, load_content
from .db import SessionLocal
from .ingest.pipeline import IngestError, ingest_folder
from .rdf.export import export_patient, validate_graph
from .vocabulary import sync_vocabulary


def _print_report(report: dict) -> None:
    for f in report["files"]:
        print(f"\n[{f['status']}] {f['file']}")
        for issue in f.get("issues", []):
            print(f"  ! {issue}")
        for col in f.get("unmapped_columns", []):
            print(f"  ? колонка не распознана: {col}")
        for row in f.get("skipped_rows", []):
            print(f"  - пропущено: {row}")
        for d in f["documents"]:
            mark = "*" if d["notes"] else " "
            extra = f", измерений {d['measurements']}" if d["measurements"] else ""
            print(f" {mark} {d['date'] or '----------'}  {d['title']} [{d['doc_type']}] "
                  f"{d['action']} v{d['version']}, фрагментов {d['fragments']}{extra}")
            for note in d["notes"]:
                print(f"      · {note['text']}")
        for key in f.get("retired", []):
            print(f"  x больше не текущий: {key}")
    print("\nИтого:", json.dumps(report["totals"], ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("load-content", help="проверить content/*.csv и обновить справочник в БД")

    p_ing = sub.add_parser("ingest", help="принять папку с файлами пациента")
    p_ing.add_argument("folder", type=Path)
    p_ing.add_argument("--patient-code", help="код пациента (по умолчанию имя папки)")
    p_ing.add_argument("--alias", action="append", default=[], help="имя пациента в опросниках")
    p_ing.add_argument("--data-class", default=settings.default_data_class)

    p_exp = sub.add_parser("export-rdf", help="выгрузить случай в Turtle")
    p_exp.add_argument("patient_code")
    p_exp.add_argument("-o", "--output", type=Path)

    p_val = sub.add_parser("validate", help="проверить граф случая по SHACL")
    p_val.add_argument("patient_code")

    args = parser.parse_args(argv)
    try:
        content = load_content()
    except ContentError as e:
        print(f"Ошибка в таблицах содержания: {e}", file=sys.stderr)
        return 2

    with SessionLocal() as session:
        if args.cmd == "load-content":
            result = sync_vocabulary(session, content)
            session.commit()
            print("Справочник:", json.dumps(result, ensure_ascii=False))
            print(f"Опросников: {len(content.instruments)}, правил файлов: {len(content.file_rules)}, "
                  f"правил заголовков: {len(content.header_rules)}")
            return 0

        if args.cmd == "ingest":
            try:
                run = ingest_folder(
                    session,
                    args.folder,
                    args.patient_code,
                    data_class=args.data_class,
                    aliases=args.alias,
                    content=content,
                )
            except IngestError as e:
                session.rollback()
                print(f"Ошибка: {e}", file=sys.stderr)
                return 1
            session.commit()
            print(f"Приём {run.id}")
            _print_report(run.report)
            return 0

        graph = export_patient(session, args.patient_code)
        if args.cmd == "export-rdf":
            data = graph.serialize(format="turtle")
            if args.output:
                args.output.write_text(data, encoding="utf-8")
                print(f"{len(graph)} троек -> {args.output}")
            else:
                sys.stdout.write(data)
            return 0

        result = validate_graph(graph)
        print(f"Троек: {len(graph)}. Соответствует SHACL: {'да' if result['conforms'] else 'нет'}")
        for v in result["violations"]:
            print(f"  ! {v['message']} — {v['focus']} {v['path']}")
        return 0 if result["conforms"] else 1


if __name__ == "__main__":
    sys.exit(main())
