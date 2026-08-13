from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .archive import publish_bundle
from .bundle import load_bundle_paths, write_bundle
from .engine import build_run
from .models import ALLOWED_SOURCES, EditionSpec
from .pages import build_pages_site
from .translation import (
    apply_translation_response,
    load_translation_response,
    write_translation_request,
)
from .utils import parse_iso_date, slugify
from .validate import validate_bundle


def _load_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _spec_from_args(args: argparse.Namespace) -> EditionSpec:
    payload: dict[str, object] = {}
    if args.spec:
        payload = _load_object(Path(args.spec))
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
        sources = tuple(value.strip() for value in sources_raw.split(",") if value.strip())
    else:
        sources = tuple(str(value) for value in sources_raw)
    max_records = args.max_records or int(payload.get("max_records") or 500)
    period_kind = args.period_kind or str(payload.get("period_kind") or "auto")
    revision = args.revision or int(payload.get("revision") or 1)
    return EditionSpec(
        journal=str(journal),
        issn=str(issn) if issn else None,
        slug=str(slug),
        start_date=parse_iso_date(str(start)),
        end_date=parse_iso_date(str(end)),
        sources=sources,
        max_records=int(max_records),
        period_kind=period_kind,
        revision=int(revision),
    )


def _add_scope_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--spec")
    parser.add_argument("--journal")
    parser.add_argument("--issn")
    parser.add_argument("--slug")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--period-kind", choices=("auto", "day", "week", "month", "range"))
    parser.add_argument("--revision", type=int)
    parser.add_argument("--sources")
    parser.add_argument("--max-records", type=int)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evidenceradar-editions")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="query source APIs and build one scoped edition")
    _add_scope_arguments(run)
    run.add_argument("--radar-root", type=Path)
    run.add_argument("--radar-commit")
    run.add_argument("--output-dir", type=Path, required=True)
    run.add_argument(
        "--translation-request",
        type=Path,
        help="also emit a zh-TW translation handoff request",
    )

    validate = sub.add_parser("validate", help="validate a generated edition bundle")
    validate.add_argument("--bundle-dir", type=Path, required=True)
    validate.add_argument("--require-zh-tw", action="store_true")

    request = sub.add_parser(
        "translation-request",
        help="create a hash-bound zh-TW translation request from an edition bundle",
    )
    request.add_argument("--bundle-dir", type=Path, required=True)
    request.add_argument("--output", type=Path, required=True)

    apply_translation = sub.add_parser(
        "apply-translation",
        help="apply a hash-bound zh-TW response and rebuild the canonical bundle",
    )
    apply_translation.add_argument("--bundle-dir", type=Path, required=True)
    apply_translation.add_argument("--response", type=Path, required=True)
    apply_translation.add_argument("--output-dir", type=Path, required=True)
    apply_translation.add_argument("--allow-partial", action="store_true")

    publish = sub.add_parser(
        "publish",
        help="copy a validated edition into the immutable journal/period archive",
    )
    publish.add_argument("--bundle-dir", type=Path, required=True)
    publish.add_argument("--archive-root", type=Path, default=Path("archive"))
    publish.add_argument("--allow-untranslated", action="store_true")

    pages = sub.add_parser(
        "build-pages", help="build the static multi-journal GitHub Pages portal"
    )
    pages.add_argument("--archive-root", type=Path, default=Path("archive"))
    pages.add_argument("--output-dir", type=Path, required=True)
    pages.add_argument("--repository", required=True)
    pages.add_argument("--base-url")
    pages.add_argument("--allow-untranslated", action="store_true")
    return parser


def _print_errors(errors: list[str]) -> None:
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate":
            errors = validate_bundle(args.bundle_dir, require_zh_tw=args.require_zh_tw)
            if errors:
                _print_errors(errors)
                return 1
            print("PASS: edition bundle validates")
            return 0

        if args.command == "translation-request":
            paths = load_bundle_paths(args.bundle_dir)
            run = _load_object(paths.json_path)
            request = write_translation_request(run, args.output)
            print(
                json.dumps(
                    {
                        "edition_id": request["edition_id"],
                        "items": request["item_count"],
                        "output": str(args.output),
                    },
                    ensure_ascii=False,
                )
            )
            return 0

        if args.command == "apply-translation":
            paths = load_bundle_paths(args.bundle_dir)
            run = _load_object(paths.json_path)
            response = load_translation_response(args.response)
            enriched = apply_translation_response(
                run, response, require_complete=not args.allow_partial
            )
            manifest = write_bundle(enriched, args.output_dir)
            errors = validate_bundle(
                args.output_dir, require_zh_tw=not args.allow_partial
            )
            if errors:
                _print_errors(errors)
                return 1
            print(
                json.dumps(
                    {
                        "edition_id": enriched["edition_id"],
                        "translated_articles": enriched["counts"]["translated_articles"],
                        "manifest": manifest["manifest_name"],
                        "output_dir": str(args.output_dir),
                    },
                    ensure_ascii=False,
                )
            )
            return 0

        if args.command == "publish":
            target = publish_bundle(
                args.bundle_dir,
                args.archive_root,
                require_zh_tw=not args.allow_untranslated,
            )
            print(json.dumps({"published": str(target)}, ensure_ascii=False))
            return 0

        if args.command == "build-pages":
            links = build_pages_site(
                archive_root=args.archive_root,
                output_dir=args.output_dir,
                repository=args.repository,
                base_url=args.base_url,
                require_zh_tw=not args.allow_untranslated,
            )
            print(json.dumps(links, ensure_ascii=False))
            return 0

        spec = _spec_from_args(args)
        run = build_run(
            spec, radar_root=args.radar_root, radar_commit=args.radar_commit
        )
        manifest = write_bundle(run, args.output_dir)
        if args.translation_request:
            write_translation_request(run, args.translation_request)
        errors = validate_bundle(args.output_dir)
        if errors:
            _print_errors(errors)
            return 1
        print(
            json.dumps(
                {
                    "edition_id": run["edition_id"],
                    "articles": run["counts"]["articles"],
                    "output_dir": str(args.output_dir),
                    "html": manifest["files"]["report_html"]["name"],
                    "json": manifest["files"]["edition_json"]["name"],
                    "manifest": manifest["manifest_name"],
                    "upstream_radar_commit": manifest.get("upstream_radar_commit"),
                },
                ensure_ascii=False,
            )
        )
        return 0
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
