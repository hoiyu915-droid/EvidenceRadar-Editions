from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from . import __version__
from .pipeline import BuildError, BuildOptions, build_edition
from .sources import SUPPORTED_SOURCES
from .upstream import UpstreamError, declared_reference, inspect_radar_checkout
from .validate import ValidationError, validate_edition_directory


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc


def _source_list(value: str) -> tuple[str, ...]:
    sources = tuple(part.strip() for part in value.split(",") if part.strip())
    unknown = sorted(set(sources).difference(SUPPORTED_SOURCES))
    if unknown:
        raise argparse.ArgumentTypeError(f"unsupported sources: {', '.join(unknown)}")
    return sources


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evidenceradar-editions",
        description=(
            "Build auditable journal editions by querying primary bibliographic sources "
            "directly for a journal and publication-date range."
        ),
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="query sources and build one edition directory")
    build.add_argument("--collection", type=Path, required=True, help="collection YAML path")
    build.add_argument("--start", type=_iso_date, required=True, help="inclusive YYYY-MM-DD")
    build.add_argument("--end", type=_iso_date, required=True, help="inclusive YYYY-MM-DD")
    build.add_argument("--output", type=Path, required=True, help="new edition directory")
    build.add_argument(
        "--sources",
        type=_source_list,
        help="comma-separated override: pubmed,europe_pmc,crossref",
    )
    build.add_argument(
        "--fixture-dir",
        type=Path,
        help="read pubmed.xml/europe_pmc.json/crossref.json instead of network",
    )
    build.add_argument(
        "--radar-root",
        type=Path,
        help="pinned EvidenceRadar checkout used only for approved source-side helpers",
    )
    build.add_argument(
        "--allow-radar-drift",
        action="store_true",
        help="allow an upstream commit other than the pinned compatibility commit",
    )
    build.add_argument("--strict-sources", action="store_true", help="fail on any source failure")
    build.add_argument("--max-records-per-source", type=int, default=5000)
    build.add_argument("--timezone", default="Asia/Tokyo")
    build.add_argument("--replace", action="store_true", help="atomically replace output directory")

    validate = subparsers.add_parser("validate", help="validate an existing edition directory")
    validate.add_argument("path", type=Path)

    inspect = subparsers.add_parser(
        "inspect-upstream",
        help="verify a local EvidenceRadar checkout against the pinned source reference",
    )
    inspect.add_argument("--radar-root", type=Path)
    inspect.add_argument("--allow-radar-drift", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "build":
            summary = build_edition(
                BuildOptions(
                    collection_path=args.collection,
                    start=args.start,
                    end=args.end,
                    output_dir=args.output,
                    sources=args.sources or (),
                    fixture_dir=args.fixture_dir,
                    radar_root=args.radar_root,
                    allow_radar_drift=args.allow_radar_drift,
                    strict_sources=args.strict_sources,
                    max_records_per_source=args.max_records_per_source,
                    replace=args.replace,
                    timezone=args.timezone,
                )
            )
        elif args.command == "validate":
            summary = validate_edition_directory(args.path)
        elif args.command == "inspect-upstream":
            if args.radar_root:
                summary = inspect_radar_checkout(
                    args.radar_root,
                    allow_drift=args.allow_radar_drift,
                ).reference.as_dict()
            else:
                summary = declared_reference().as_dict()
        else:  # pragma: no cover
            raise AssertionError(args.command)
    except (BuildError, UpstreamError, ValidationError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0
