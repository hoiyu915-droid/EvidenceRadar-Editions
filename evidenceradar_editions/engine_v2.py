from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from .engine import build_run as _build_core_run
from .http import HttpClient
from .models import EditionSpec
from .processing_policy import (
    JournalProcessingPolicy,
    apply_volume_guard,
    ensure_load_allowed,
    policy_for_slug,
)


def _projection_mode(article_count: int, pages_record_limit: int) -> str:
    if pages_record_limit <= 0:
        return "NONE"
    if article_count > pages_record_limit:
        return "LIMITED"
    return "INLINE_ALL"


def build_run(
    spec: EditionSpec,
    *,
    radar_root: Path | None = None,
    radar_commit: str | None = None,
    client: HttpClient | None = None,
    processing_policy: JournalProcessingPolicy | None = None,
    catalog_root: Path | str = Path("catalog"),
    allow_policy_override: bool = False,
) -> dict[str, Any]:
    """Run metadata acquisition under a journal volume policy.

    The underlying source adapters acquire bibliographic metadata only. This
    wrapper prevents SUSPENDED journals from touching the network, clamps the
    per-source record budget, records the exact processing level, and applies a
    non-destructive FULL -> TRIAGE guard when a source reports extreme volume.
    """

    configured = processing_policy or policy_for_slug(
        spec.slug,
        catalog_root=catalog_root,
    )
    active_policy = ensure_load_allowed(
        configured,
        allow_override=allow_policy_override,
    )

    if allow_policy_override:
        applied_limit = spec.max_records
    else:
        applied_limit = min(spec.max_records, active_policy.source_record_limit)
    if applied_limit < 1:
        raise ValueError("applied source record limit must be at least 1")

    effective_spec = replace(spec, max_records=applied_limit)
    run = _build_core_run(
        effective_spec,
        radar_root=radar_root,
        radar_commit=radar_commit,
        client=client,
    )
    effective = apply_volume_guard(
        active_policy,
        run.get("source_checks") or [],
    )

    article_count = int((run.get("counts") or {}).get("articles") or 0)
    projected_count = min(article_count, max(0, effective.pages_record_limit))
    processing = {
        **effective.to_dict(),
        "configured_source_record_limit": configured.source_record_limit,
        "requested_source_record_limit": spec.max_records,
        "applied_source_record_limit": applied_limit,
        "policy_override_used": bool(allow_policy_override),
        "acquisition_level": "BIBLIOGRAPHIC_METADATA",
        "full_text_requested": False,
        "full_text_fetched": False,
        "evidence_evaluated": False,
        "pages_projection_mode": _projection_mode(
            article_count,
            effective.pages_record_limit,
        ),
        "pages_projected_article_count": projected_count,
        "pages_omitted_article_count": article_count - projected_count,
        "selection_semantics": (
            "Operational volume projection only; canonical metadata remain intact, "
            "and no quality or relevance ranking is implied."
        ),
    }
    run["processing"] = processing

    scope = run.setdefault("scope", {})
    scope["processing_mode_configured"] = effective.configured_mode
    scope["processing_mode_effective"] = effective.effective_mode
    scope["processing_policy_source"] = effective.policy_source

    presentation = run.setdefault("presentation", {})
    presentation["pages_projection_mode"] = processing["pages_projection_mode"]
    presentation["pages_record_limit"] = effective.pages_record_limit
    presentation["translation_required_for_publication"] = (
        effective.translation_mode == "ALL"
    )

    translation = run.setdefault("translation", {})
    translation["generation_policy"] = effective.translation_mode
    translation["automatic_request_allowed"] = effective.translation_mode == "ALL"

    counts = run.setdefault("counts", {})
    counts["pages_projected_articles"] = projected_count
    counts["pages_omitted_articles"] = article_count - projected_count
    return run


__all__ = ["build_run"]
