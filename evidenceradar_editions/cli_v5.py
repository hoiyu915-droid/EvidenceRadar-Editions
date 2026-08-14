from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import cli_v4 as legacy
from .bundle import write_bundle
from .engine_v2 import build_run
from .journal_catalog_v2 import list_journals as catalog_list_journals
from .processing_policy import (
    ALLOWED_PROCESSING_MODES,
    policy_for_slug,
)
from .translation import write_translation_request
from .validate import validate_bundle


def _subparser(parser: argparse.ArgumentParser, name: str) -> argparse.ArgumentParser:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices[name]
    raise RuntimeError("CLI subparser registry is missing")


def build_parser() -> argparse.ArgumentParser:
    parser = legacy.build_parser()
    run = _subparser(parser, "run")
    run.add_argument(
        "--override-processing-policy",
        action="store_true",
        help=(
            "explicitly bypass a SUSPENDED journal or its source-record cap; "
            "the override is recorded in edition processing provenance"
        ),
    )
    journals = _subparser(parser, "journals")
    journals.add_argument(
        "--processing-mode",
        choices=ALLOWED_PROCESSING_MODES,
        help="filter by FULL, TRIAGE, INDEX_ONLY or SUSPENDED",
    )
    return parser


def _run(args: argparse.Namespace) -> int:
    spec = legacy._spec_from_args(args)
    policy = policy_for_slug(spec.slug, catalog_root=Path(args.catalog_root))
    run = build_run(
        spec,
        radar_root=args.radar_root,
        radar_commit=args.radar_commit,
        processing_policy=policy,
        catalog_root=Path(args.catalog_root),
        allow_policy_override=bool(args.override_processing_policy),
    )
    manifest = write_bundle(run, args.output_dir)

    translation_request_written = False
    if args.translation_request:
        automatic_allowed = bool(
            (run.get("translation") or {}).get("automatic_request_allowed")
        )
        if not automatic_allowed and not args.override_processing_policy:
            mode = (run.get("processing") or {}).get("effective_mode")
            raise ValueError(
                f"automatic translation request is disabled in {mode} mode; "
                "use the explicit translation-request command later, or pass "
                "--override-processing-policy"
            )
        write_translation_request(run, args.translation_request)
        translation_request_written = True

    errors = validate_bundle(args.output_dir)
    if errors:
        legacy._print_errors(errors)
        return 1
    processing = run.get("processing") or {}
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
                "processing_mode_configured": processing.get("configured_mode"),
                "processing_mode_effective": processing.get("effective_mode"),
                "source_record_limit": processing.get("applied_source_record_limit"),
                "pages_record_limit": processing.get("pages_record_limit"),
                "translation_mode": processing.get("translation_mode"),
                "translation_request_written": translation_request_written,
                "policy_override_used": processing.get("policy_override_used"),
            },
            ensure_ascii=False,
        )
    )
    return 0


def _journals(args: argparse.Namespace) -> int:
    items = catalog_list_journals(
        catalog_root=args.catalog_root,
        status=args.status,
        category=args.category,
        publisher=args.publisher,
        enabled_only=args.enabled_only,
        processing_mode=args.processing_mode,
    )
    print(
        json.dumps(
            {"journal_count": len(items), "journals": items},
            ensure_ascii=False,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command not in {"run", "journals"}:
        return legacy.main(argv)
    try:
        if args.command == "journals":
            return _journals(args)
        return _run(args)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


__all__ = ["build_parser", "main"]
