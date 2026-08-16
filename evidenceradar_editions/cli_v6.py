from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import cli_v5 as legacy
from .adapters.cambridge_core import CambridgeCoreAdapter
from .bundle import write_bundle
from .engine_v2 import build_run
from .http import HttpClient
from .models import EditionSpec
from .processing_policy import policy_for_slug
from .translation import write_translation_request
from .utils import parse_iso_date
from .validate import validate_bundle

PROVIDERS = ("cambridge",)


def _subparser(parser: argparse.ArgumentParser, name: str) -> argparse.ArgumentParser:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices[name]
    raise RuntimeError("CLI subparser registry is missing")


def build_parser() -> argparse.ArgumentParser:
    parser = legacy.build_parser()
    run = _subparser(parser, "run")
    run.add_argument(
        "--provider",
        choices=PROVIDERS,
        help=(
            "resolve the journal through a publisher provider instead of "
            "catalog/journals.json; provider runs acquire only the selected journal"
        ),
    )
    journals = _subparser(parser, "journals")
    journals.add_argument(
        "--provider",
        choices=PROVIDERS,
        help="list journals exposed by a publisher provider",
    )
    return parser


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _provider_adapter(provider: str) -> CambridgeCoreAdapter:
    if provider == "cambridge":
        return CambridgeCoreAdapter(HttpClient())
    raise ValueError(f"unsupported provider: {provider}")


def _resolve_provider_journal(
    args: argparse.Namespace,
    adapter: CambridgeCoreAdapter,
) -> dict[str, Any]:
    if args.journal_slug:
        return adapter.resolve_journal(str(args.journal_slug))
    if args.journal:
        wanted = str(args.journal).strip().casefold()
        matches = [
            item
            for item in adapter.list_journals()
            if str(item.get("name") or "").strip().casefold() == wanted
        ]
        if not matches:
            raise KeyError(f"provider journal was not found: {args.journal}")
        if len(matches) > 1:
            raise ValueError(
                "provider journal name is ambiguous; use --journal-slug instead"
            )
        return adapter.resolve_journal(str(matches[0]["slug"]))
    raise ValueError(
        "provider run requires --journal-slug (preferred) or an exact --journal name"
    )


def _provider_spec(
    args: argparse.Namespace,
    journal_record: dict[str, Any],
) -> EditionSpec:
    payload: dict[str, Any] = _load_object(Path(args.spec)) if args.spec else {}
    start = args.start or payload.get("start_date")
    end = args.end or payload.get("end_date")
    if not start or not end:
        raise ValueError("start and end dates are required")

    journal_name = str(journal_record["name"])
    journal_slug = str(journal_record["slug"])
    journal_issn = str(journal_record.get("issn") or "") or None
    if args.journal and str(args.journal).strip().casefold() != journal_name.casefold():
        raise ValueError("--journal does not match the selected provider journal")
    if args.slug and str(args.slug) != journal_slug:
        raise ValueError("--slug does not match the selected provider journal slug")

    requested_issn = args.issn or payload.get("issn") or journal_issn
    sources_raw = args.sources or payload.get("sources") or journal_record.get("sources")
    if isinstance(sources_raw, str):
        sources = tuple(
            value.strip() for value in sources_raw.split(",") if value.strip()
        )
    else:
        sources = tuple(str(value) for value in (sources_raw or ()))
    if not sources:
        raise ValueError("provider journal does not expose acquisition sources")
    if "cambridge_core" not in sources:
        raise ValueError("Cambridge provider runs must include the cambridge_core source")

    return EditionSpec(
        journal=journal_name,
        issn=str(requested_issn) if requested_issn else None,
        slug=journal_slug,
        start_date=parse_iso_date(str(start)),
        end_date=parse_iso_date(str(end)),
        sources=sources,
        max_records=int(args.max_records or payload.get("max_records") or 500),
        period_kind=args.period_kind or str(payload.get("period_kind") or "auto"),
        revision=int(args.revision or payload.get("revision") or 1),
    )


def _run_provider(args: argparse.Namespace) -> int:
    adapter = _provider_adapter(args.provider)
    journal_record = _resolve_provider_journal(args, adapter)
    spec = _provider_spec(args, journal_record)
    policy = policy_for_slug(spec.slug, catalog_root=Path(args.catalog_root))
    run = build_run(
        spec,
        radar_root=args.radar_root,
        radar_commit=args.radar_commit,
        processing_policy=policy,
        catalog_root=Path(args.catalog_root),
        allow_policy_override=bool(args.override_processing_policy),
    )
    scope = run.setdefault("scope", {})
    scope["provider"] = args.provider
    scope["provider_journal_url"] = journal_record.get("url")
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
        legacy.legacy._print_errors(errors)
        return 1
    processing = run.get("processing") or {}
    print(
        json.dumps(
            {
                "provider": args.provider,
                "journal": spec.journal,
                "journal_slug": spec.slug,
                "edition_id": run["edition_id"],
                "articles": run["counts"]["articles"],
                "output_dir": str(args.output_dir),
                "html": manifest["files"]["report_html"]["name"],
                "json": manifest["files"]["edition_json"]["name"],
                "manifest": manifest["manifest_name"],
                "processing_mode_configured": processing.get("configured_mode"),
                "processing_mode_effective": processing.get("effective_mode"),
                "translation_request_written": translation_request_written,
            },
            ensure_ascii=False,
        )
    )
    return 0


def _journals_provider(args: argparse.Namespace) -> int:
    if args.category:
        raise ValueError(
            "publisher provider journals do not carry Editions category labels; "
            "omit --category or use the local registry"
        )
    adapter = _provider_adapter(args.provider)
    items = adapter.list_journals()
    if args.status:
        items = [item for item in items if item.get("status") == args.status]
    if args.publisher:
        wanted = str(args.publisher).casefold()
        items = [
            item
            for item in items
            if str(item.get("publisher") or "").casefold() == wanted
        ]
    if args.processing_mode:
        wanted_mode = str(args.processing_mode).upper()
        enriched: list[dict[str, Any]] = []
        for item in items:
            policy = policy_for_slug(
                str(item["slug"]),
                catalog_root=Path(args.catalog_root),
            )
            if policy.configured_mode == wanted_mode:
                enriched.append({**item, "processing_policy": policy.to_dict()})
        items = enriched
    else:
        items = [
            {
                **item,
                "processing_policy": policy_for_slug(
                    str(item["slug"]),
                    catalog_root=Path(args.catalog_root),
                ).to_dict(),
            }
            for item in items
        ]
    print(
        json.dumps(
            {
                "provider": args.provider,
                "journal_count": len(items),
                "journals": items,
            },
            ensure_ascii=False,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "run" and args.provider:
            return _run_provider(args)
        if args.command == "journals" and args.provider:
            return _journals_provider(args)
        return legacy.main(argv)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


__all__ = ["build_parser", "main"]
