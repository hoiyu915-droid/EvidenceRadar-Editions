from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, timedelta
import json
from pathlib import Path
from typing import Any

from .bundle import artifact_names
from .engine_v2 import build_run
from .journal_catalog_v2 import get_journal, spec_defaults
from .models import EditionSpec
from .naming import build_identity
from .processing_policy import policy_for_slug
from .store_v3 import validate_stored_publication
from .utils import parse_iso_date, sha256_file


INCREMENTAL_SEMANTICS = "incremental_acquisition_merged_with_immutable_base_snapshot"


@dataclass(frozen=True)
class BackfillResult:
    run: dict[str, Any]
    base_directory: Path
    acquisition_start: date
    acquisition_end: date


def _latest_month_directory(
    editions_root: Path,
    *,
    journal_slug: str,
    year: int,
    month: int,
) -> Path:
    month_root = Path(editions_root) / journal_slug / f"{year:04d}" / f"{month:02d}"
    candidates: list[tuple[int, Path]] = []
    for manifest_path in sorted(month_root.glob("r*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("period_kind") != "month":
            continue
        candidates.append((int(manifest.get("revision") or 0), manifest_path.parent))
    if not candidates:
        raise FileNotFoundError(
            f"no monthly base edition exists for {journal_slug} {year:04d}-{month:02d}"
        )
    return max(candidates, key=lambda item: item[0])[1]


def _load_base(directory: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    errors = validate_stored_publication(directory, require_zh_tw=False)
    if errors:
        raise ValueError(
            f"incremental base publication is invalid: {directory}\n" + "\n".join(errors)
        )
    edition = json.loads((directory / "edition.json").read_text(encoding="utf-8"))
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    return edition, manifest


def _merge_article(base: dict[str, Any], delta: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for field in (
        "doi",
        "pmid",
        "pmcid",
        "article_type",
        "publication_date",
        "publication_date_precision",
    ):
        if not merged.get(field) and delta.get(field):
            merged[field] = deepcopy(delta[field])
    if len(delta.get("authors") or []) > len(merged.get("authors") or []):
        merged["authors"] = deepcopy(delta["authors"])
    for field in ("issns", "urls"):
        merged[field] = sorted(
            {str(value) for value in [*(merged.get(field) or []), *(delta.get(field) or [])]}
        )
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for record in [*(merged.get("source_records") or []), *(delta.get("source_records") or [])]:
        key = (
            str(record.get("source") or ""),
            str(record.get("source_id") or ""),
            str(record.get("url") or ""),
        )
        if key not in seen:
            records.append(deepcopy(record))
            seen.add(key)
    merged["source_records"] = records
    return merged


def _merge_articles(
    base_articles: list[dict[str, Any]],
    delta_articles: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    merged: dict[str, dict[str, Any]] = {
        str(article["canonical_id"]): deepcopy(article) for article in base_articles
    }
    added = 0
    for article in delta_articles:
        canonical_id = str(article["canonical_id"])
        if canonical_id in merged:
            merged[canonical_id] = _merge_article(merged[canonical_id], article)
        else:
            merged[canonical_id] = deepcopy(article)
            added += 1
    articles = sorted(
        merged.values(),
        key=lambda article: (
            str(article.get("publication_date") or ""),
            str(article.get("title_original") or article.get("title") or "").casefold(),
        ),
        reverse=True,
    )
    return articles, added


def _article_counts(articles: list[dict[str, Any]]) -> dict[str, Any]:
    by_source: defaultdict[str, set[str]] = defaultdict(set)
    by_type: Counter[str] = Counter()
    translated = 0
    for article in articles:
        canonical_id = str(article["canonical_id"])
        for record in article.get("source_records") or []:
            source = str(record.get("source") or "")
            if source:
                by_source[source].add(canonical_id)
        by_type[str(article.get("article_type") or "unspecified")] += 1
        if article.get("title_zh_tw") and article.get("summary_zh_tw"):
            translated += 1
    return {
        "articles": len(articles),
        "translated_articles": translated,
        "by_source": {key: len(value) for key, value in sorted(by_source.items())},
        "by_article_type": dict(sorted(by_type.items())),
    }


def compose_incremental_month_revision(
    *,
    base: dict[str, Any],
    base_manifest: dict[str, Any],
    base_edition_sha256: str,
    delta: dict[str, Any],
    revision: int,
) -> dict[str, Any]:
    base_scope = base.get("scope") or {}
    delta_scope = delta.get("scope") or {}
    base_start = parse_iso_date(str(base_scope.get("start_date") or ""))
    base_end = parse_iso_date(str(base_scope.get("end_date") or ""))
    acquisition_start = parse_iso_date(str(delta_scope.get("start_date") or ""))
    acquisition_end = parse_iso_date(str(delta_scope.get("end_date") or ""))
    if str(base_scope.get("period_kind")) != "month":
        raise ValueError("incremental base must be a monthly edition")
    if base_start.day != 1:
        raise ValueError("incremental monthly base must start on the first day of its month")
    if acquisition_start != base_end + timedelta(days=1):
        raise ValueError("incremental acquisition must start on the day after the base window")
    if (base_start.year, base_start.month) != (acquisition_end.year, acquisition_end.month):
        raise ValueError("incremental acquisition cannot cross a calendar-month boundary")
    expected_revision = int(base_scope.get("revision") or 0) + 1
    if revision != expected_revision:
        raise ValueError(
            f"incremental revision must follow the base revision: expected {expected_revision}"
        )
    if base_scope.get("journal_slug") != delta_scope.get("journal_slug"):
        raise ValueError("incremental base and delta journal identities differ")
    if delta.get("run_status") in {"SOURCE_ACCESS_GAP", "PARTIAL_SOURCE_COVERAGE"}:
        journal_slug = str(
            delta_scope.get("journal_slug") or base_scope.get("journal_slug") or "unknown"
        )
        source_summaries = []
        for check in delta.get("source_checks") or []:
            summary = f"{check.get('source') or 'unknown'}={check.get('status') or 'UNKNOWN'}"
            detail = str(check.get("detail") or "").strip()
            if detail:
                summary += f" ({detail})"
            source_summaries.append(summary)
        sources = "; ".join(source_summaries) or "none"
        raise ValueError(
            "incremental acquisition is not complete for "
            f"{journal_slug}: {delta.get('run_status')}; source_checks: {sources}"
        )

    base_articles = [value for value in base.get("articles") or [] if isinstance(value, dict)]
    delta_articles = [value for value in delta.get("articles") or [] if isinstance(value, dict)]
    articles, added = _merge_articles(base_articles, delta_articles)
    counts = _article_counts(articles)
    identity = build_identity(
        slug=str(base_scope["journal_slug"]),
        start=base_start,
        end=acquisition_end,
        period_kind_requested="month",
        revision=revision,
    )

    run = deepcopy(base)
    run["edition_id"] = identity.publication_id
    run["edition_key"] = identity.edition_key
    run["publication_id"] = identity.publication_id
    run["retrieved_at"] = delta.get("retrieved_at")
    run["run_status"] = "COMPLETE" if articles else "NO_MATCHING_ARTICLES"
    run["data_semantics"] = INCREMENTAL_SEMANTICS
    run["scope"] = {
        **deepcopy(base_scope),
        "end_date": acquisition_end.isoformat(),
        "sources": deepcopy(delta_scope.get("sources") or base_scope.get("sources") or []),
        "max_records": delta_scope.get("max_records", base_scope.get("max_records")),
        "period_kind_requested": "month",
        **identity.to_dict(),
    }
    run["upstream_radar"] = deepcopy(delta.get("upstream_radar") or base.get("upstream_radar") or {})
    run["source_checks"] = deepcopy(delta.get("source_checks") or [])
    run["articles"] = articles
    run["counts"] = counts

    translation = deepcopy(base.get("translation") or {})
    translated = counts["translated_articles"]
    if not articles:
        translation_status = "NOT_REQUIRED"
    elif translated == len(articles):
        translation_status = "COMPLETE"
    elif translated:
        translation_status = "PARTIAL"
    else:
        translation_status = "NOT_REQUESTED"
        translation["source_edition_sha256"] = None
        translation["request_binding_sha256"] = None
        translation["response_sha256"] = None
    translation.update(
        {
            "language": "zh-TW",
            "status": translation_status,
            "translated_articles": translated,
            "total_articles": len(articles),
            "inherited_from_publication_id": base.get("publication_id"),
        }
    )
    run["translation"] = translation

    processing = deepcopy(delta.get("processing") or base.get("processing") or {})
    pages_limit = int(processing.get("pages_record_limit") or len(articles))
    projected = min(len(articles), max(0, pages_limit))
    processing.update(
        {
            "pages_projection_mode": "LIMITED" if projected < len(articles) else "INLINE_ALL",
            "pages_projected_article_count": projected,
            "pages_omitted_article_count": len(articles) - projected,
            "incremental_acquisition_start": acquisition_start.isoformat(),
            "incremental_acquisition_end": acquisition_end.isoformat(),
        }
    )
    run["processing"] = processing
    run["counts"]["pages_projected_articles"] = projected
    run["counts"]["pages_omitted_articles"] = len(articles) - projected

    run["incremental_backfill"] = {
        "mode": "INCREMENTAL_ACQUISITION_FULL_SNAPSHOT_REVISION",
        "base_publication_id": base.get("publication_id"),
        "base_revision": int(base_scope.get("revision") or 0),
        "base_edition_sha256": base_edition_sha256,
        "base_period_start": base_start.isoformat(),
        "base_period_end": base_end.isoformat(),
        "acquisition_start": acquisition_start.isoformat(),
        "acquisition_end": acquisition_end.isoformat(),
        "base_article_count": len(base_articles),
        "delta_acquired_article_count": len(delta_articles),
        "added_article_count": added,
        "deduplicated_article_count": len(base_articles) + len(delta_articles) - len(articles),
        "result_article_count": len(articles),
        "base_manifest_publication_id": base_manifest.get("publication_id"),
    }
    run["artifacts"] = {}
    artifact_names(run)
    return run


def build_incremental_month_backfill(
    *,
    journal_slug: str,
    acquisition_end: date,
    editions_root: Path = Path("editions"),
    catalog_root: Path = Path("catalog"),
    acquisition_start: date | None = None,
    revision: int | None = None,
    radar_root: Path | None = None,
    radar_commit: str | None = None,
    max_records: int | None = None,
    sources: tuple[str, ...] | None = None,
    allow_planned: bool = False,
    allow_policy_override: bool = False,
) -> BackfillResult:
    base_directory = _latest_month_directory(
        editions_root,
        journal_slug=journal_slug,
        year=acquisition_end.year,
        month=acquisition_end.month,
    )
    base, base_manifest = _load_base(base_directory)
    base_end = parse_iso_date(str((base.get("scope") or {})["end_date"]))
    start = acquisition_start or (base_end + timedelta(days=1))
    if start != base_end + timedelta(days=1):
        raise ValueError(
            f"backfill must extend the latest base contiguously from {base_end.isoformat()}"
        )
    if acquisition_end < start:
        raise ValueError("backfill acquisition end precedes the missing-date window")

    journal = get_journal(
        journal_slug,
        catalog_root=catalog_root,
        require_enabled=not allow_planned,
    )
    defaults = spec_defaults(journal)
    source_values = sources or tuple(str(value) for value in defaults["sources"])
    next_revision = int((base.get("scope") or {}).get("revision") or 0) + 1
    requested_revision = revision or next_revision
    delta_spec = EditionSpec(
        journal=str(defaults["journal"]),
        issn=str(defaults["issn"]) if defaults.get("issn") else None,
        slug=journal_slug,
        start_date=start,
        end_date=acquisition_end,
        sources=source_values,
        max_records=int(max_records or defaults.get("max_records") or 500),
        period_kind="range",
        revision=1,
    )
    delta = build_run(
        delta_spec,
        radar_root=radar_root,
        radar_commit=radar_commit,
        processing_policy=policy_for_slug(journal_slug, catalog_root=catalog_root),
        catalog_root=catalog_root,
        allow_policy_override=allow_policy_override,
    )
    run = compose_incremental_month_revision(
        base=base,
        base_manifest=base_manifest,
        base_edition_sha256=sha256_file(base_directory / "edition.json"),
        delta=delta,
        revision=requested_revision,
    )
    return BackfillResult(
        run=run,
        base_directory=base_directory,
        acquisition_start=start,
        acquisition_end=acquisition_end,
    )


__all__ = [
    "BackfillResult",
    "INCREMENTAL_SEMANTICS",
    "build_incremental_month_backfill",
    "compose_incremental_month_revision",
]
