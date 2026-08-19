from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import cli_v6 as legacy
from .bundle import write_bundle
from .incremental_backfill import build_incremental_month_backfill
from .utils import parse_iso_date
from .validate import validate_bundle


def build_parser() -> argparse.ArgumentParser:
    parser = legacy.build_parser()
    subparsers = next(
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    backfill = subparsers.add_parser(
        "backfill",
        help="acquire only a missing date suffix and publish a new monthly snapshot revision",
    )
    backfill.add_argument("--journal-slug", required=True)
    backfill.add_argument("--start")
    backfill.add_argument("--end", required=True)
    backfill.add_argument("--revision", type=int)
    backfill.add_argument("--editions-root", type=Path, default=Path("editions"))
    backfill.add_argument("--catalog-root", type=Path, default=Path("catalog"))
    backfill.add_argument("--radar-root", type=Path)
    backfill.add_argument("--radar-commit")
    backfill.add_argument("--max-records", type=int)
    backfill.add_argument("--sources")
    backfill.add_argument("--allow-planned", action="store_true")
    backfill.add_argument("--override-processing-policy", action="store_true")
    backfill.add_argument("--output-dir", type=Path, required=True)
    return parser


def _backfill(args: argparse.Namespace) -> int:
    sources = None
    if args.sources:
        sources = tuple(value.strip() for value in args.sources.split(",") if value.strip())
    result = build_incremental_month_backfill(
        journal_slug=args.journal_slug,
        acquisition_start=parse_iso_date(args.start) if args.start else None,
        acquisition_end=parse_iso_date(args.end),
        revision=args.revision,
        editions_root=args.editions_root,
        catalog_root=args.catalog_root,
        radar_root=args.radar_root,
        radar_commit=args.radar_commit,
        max_records=args.max_records,
        sources=sources,
        allow_planned=args.allow_planned,
        allow_policy_override=args.override_processing_policy,
    )
    manifest = write_bundle(result.run, args.output_dir)
    errors = validate_bundle(args.output_dir, require_zh_tw=False)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    info = result.run["incremental_backfill"]
    print(
        json.dumps(
            {
                "edition_id": result.run["edition_id"],
                "base_publication_id": info["base_publication_id"],
                "acquisition_start": info["acquisition_start"],
                "acquisition_end": info["acquisition_end"],
                "delta_acquired_articles": info["delta_acquired_article_count"],
                "added_articles": info["added_article_count"],
                "total_articles": info["result_article_count"],
                "manifest": manifest["manifest_name"],
                "output_dir": str(args.output_dir),
            },
            ensure_ascii=False,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command != "backfill":
        return legacy.main(argv)
    try:
        return _backfill(args)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


__all__ = ["build_parser", "main"]
