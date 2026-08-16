from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

from .adapters import CambridgeCoreAdapter
from .http import HttpClient
from .journal_catalog_v2 import get_journal, spec_defaults
from .models import ALLOWED_SOURCES, EditionSpec
from .processing_policy import policy_for_slug
from .utils import parse_iso_date

RADAR_PIN = "6da659df845e4b76072dae016120ca76ed9c27c4"


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "on"}


def _github_output(values: dict[str, object]) -> None:
    target = os.environ.get("GITHUB_OUTPUT")
    if not target:
        return
    with Path(target).open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            text = str(value).replace("\n", " ")
            handle.write(f"{key}={text}\n")


def _source_tuple(raw: Any) -> tuple[str, ...]:
    if isinstance(raw, str):
        return tuple(value.strip() for value in raw.split(",") if value.strip())
    return tuple(str(value).strip() for value in raw or () if str(value).strip())


def _resolve_provider_journal(provider: str, slug: str) -> dict[str, Any]:
    if provider != "cambridge":
        raise ValueError(f"unsupported Edition provider: {provider}")
    if not slug:
        raise ValueError("provider live Edition requires EDITION_JOURNAL_SLUG")
    return CambridgeCoreAdapter(HttpClient()).resolve_journal(slug)


def _resolve_spec_and_policy() -> tuple[EditionSpec, Any, bool, dict[str, Any]]:
    catalog_root = Path(os.environ.get("EDITION_CATALOG_ROOT", "catalog"))
    registry_slug = str(os.environ.get("EDITION_JOURNAL_SLUG") or "").strip()
    legacy_slug = str(os.environ.get("EDITION_SLUG") or "").strip()
    provider = str(os.environ.get("EDITION_PROVIDER") or "").strip().casefold()
    allow_planned = _truthy(os.environ.get("EDITION_ALLOW_PLANNED"))

    registry_defaults: dict[str, Any] = {}
    provider_context: dict[str, Any] = {}
    if provider:
        journal_record = _resolve_provider_journal(provider, registry_slug)
        registry_defaults = {
            "journal": journal_record.get("name"),
            "slug": journal_record.get("slug"),
            "issn": journal_record.get("issn"),
            "sources": journal_record.get("sources"),
        }
        provider_context = {
            "provider": provider,
            "provider_journal_url": journal_record.get("url"),
        }
    elif registry_slug:
        journal_record = get_journal(
            registry_slug,
            catalog_root=catalog_root,
            require_enabled=not allow_planned,
        )
        registry_defaults = spec_defaults(journal_record)

    journal = (
        registry_defaults.get("journal")
        or os.environ.get("EDITION_JOURNAL")
        or ""
    )
    slug = registry_defaults.get("slug") or registry_slug or legacy_slug
    if not journal or not slug:
        raise ValueError(
            "journal identity is required; set EDITION_JOURNAL_SLUG or the legacy "
            "EDITION_JOURNAL and EDITION_SLUG pair"
        )

    policy = policy_for_slug(str(slug), catalog_root=catalog_root)
    max_records_raw = str(os.environ.get("EDITION_MAX_RECORDS") or "").strip()
    max_records = (
        int(max_records_raw)
        if max_records_raw
        else max(1, int(policy.source_record_limit or 1))
    )
    sources_raw = str(os.environ.get("EDITION_SOURCES") or "").strip()
    sources = (
        _source_tuple(sources_raw)
        if sources_raw
        else _source_tuple(registry_defaults.get("sources") or ALLOWED_SOURCES)
    )
    if provider == "cambridge" and "cambridge_core" not in sources:
        raise ValueError("Cambridge provider live Editions must include cambridge_core")

    spec = EditionSpec(
        journal=str(journal),
        start_date=parse_iso_date(os.environ["EDITION_START"]),
        end_date=parse_iso_date(os.environ["EDITION_END"]),
        slug=str(slug),
        issn=(
            str(registry_defaults.get("issn"))
            if registry_defaults.get("issn")
            else (os.environ.get("EDITION_ISSN") or None)
        ),
        sources=sources,
        max_records=max_records,
        period_kind=os.environ.get("EDITION_PERIOD_KIND", "auto"),
        revision=int(os.environ.get("EDITION_REVISION", "1")),
    )
    return (
        spec,
        policy,
        _truthy(os.environ.get("EDITION_POLICY_OVERRIDE")),
        provider_context,
    )


def run_workflow(
    *,
    build_run: Callable[..., dict[str, Any]],
    write_bundle: Callable[..., dict[str, Any]],
    write_translation_request: Callable[..., dict[str, Any]],
    validate_bundle: Callable[..., list[str]],
) -> int:
    spec, policy, allow_override, provider_context = _resolve_spec_and_policy()
    output = Path(os.environ.get("EDITION_OUTPUT_DIR", "dist/edition"))
    radar_root_value = os.environ.get("EDITION_RADAR_ROOT", "_upstream/EvidenceRadar")
    radar_root = Path(radar_root_value) if radar_root_value else None

    run = build_run(
        spec,
        radar_root=radar_root,
        radar_commit=os.environ.get("EDITION_RADAR_COMMIT", RADAR_PIN),
        processing_policy=policy,
        catalog_root=Path(os.environ.get("EDITION_CATALOG_ROOT", "catalog")),
        allow_policy_override=allow_override,
    )
    if provider_context:
        run.setdefault("scope", {}).update(provider_context)
    manifest = write_bundle(run, output)

    processing = run.get("processing") or {}
    translation_mode = str(
        processing.get("translation_mode")
        or (run.get("translation") or {}).get("generation_policy")
        or "ALL"
    ).upper()
    request_name = ""
    request_binding_sha256 = ""
    if translation_mode == "ALL":
        request_name = str(run["artifacts"]["translation_request_json"])
        request = write_translation_request(run, output / request_name)
        request_binding_sha256 = str(request["request_binding_sha256"])

    errors = validate_bundle(output)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    values = {
        "edition_id": run["edition_id"],
        "artifact_name": run["publication_id"],
        "bundle_dir": output.as_posix(),
        "edition_json": manifest["files"]["edition_json"]["name"],
        "report_html": manifest["files"]["report_html"]["name"],
        "manifest_json": manifest["manifest_name"],
        "translation_request_json": request_name,
        "article_count": run["counts"]["articles"],
        "run_status": run["run_status"],
        "request_binding_sha256": request_binding_sha256,
        "processing_mode_configured": processing.get("configured_mode", "FULL"),
        "processing_mode_effective": processing.get("effective_mode", "FULL"),
        "source_record_limit": processing.get(
            "applied_source_record_limit", spec.max_records
        ),
        "pages_record_limit": processing.get("pages_record_limit", ""),
        "translation_mode": translation_mode,
        "policy_override_used": processing.get("policy_override_used", False),
        "provider": provider_context.get("provider", ""),
    }
    _github_output(values)
    print(json.dumps(values, ensure_ascii=False, sort_keys=True))
    return 0
