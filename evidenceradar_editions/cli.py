from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .bundle import write_bundle
from .engine import build_run
from .models import ALLOWED_SOURCES, EditionSpec
from .utils import parse_iso_date, slugify
from .validate import validate_bundle


def _spec_from_args(args: argparse.Namespace) -> EditionSpec:
    payload: dict[str, object] = {}
    if args.spec:
        payload = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    journal = args.journal or payload.get("journal")
    if not journal:
        raise ValueError("journal is required")
    start = args.start or payload.get("start_date")
    end = args.end or payload.get("end_date")
    if not start or not end:
        raise ValueError("start and end dates are required")
    issn = args.issn if args.issn is not None else payload.get("issn")
    slug = args.slug or payload.get("slug") or slugify(str(journal))
    sources_raw = args.sources or payload.get("sources") or list(ALLOWED_SOURCES)
    if isinstance(sources_raw, str):
        sources = tuple(s.strip() for s in sources_raw.split(",") if s.strip())
    else:
        sources = tuple(str(s) for s in sources_raw)
    max_records = args.max_records or int(payload.get("max_records") or 500)
    return EditionSpec(journal=str(journal), issn=str(issn) if issn else None, slug=str(slug), start_date=parse_iso_date(str(start)), end_date=parse_iso_date(str(end)), sources=sources, max_records=int(max_records))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evidenceradar-editions")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="query source APIs and build one scoped edition")
    run.add_argument("--spec")
    run.add_argument("--journal")
    run.add_argument("--issn")
    run.add_argument("--slug")
    run.add_argument("--start")
    run.add_argument("--end")
    run.add_argument("--sources")
    run.add_argument("--max-records", type=int)
    run.add_argument("--radar-root", type=Path)
    run.add_argument("--radar-commit")
    run.add_argument("--output-dir", type=Path, required=True)
    validate = sub.add_parser("validate", help="validate a generated edition bundle")
    validate.add_argument("--bundle-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "validate":
        errors = validate_bundle(args.bundle_dir)
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 1
        print("PASS: edition bundle validates")
        return 0
    try:
        spec = _spec_from_args(args)
        run = build_run(spec, radar_root=args.radar_root, radar_commit=args.radar_commit)
        manifest = write_bundle(run, args.output_dir)
        errors = validate_bundle(args.output_dir)
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 1
        print(json.dumps({"edition_id": run["edition_id"], "articles": run["counts"]["articles"], "output_dir": str(args.output_dir), "upstream_radar_commit": manifest.get("upstream_radar_commit")}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
