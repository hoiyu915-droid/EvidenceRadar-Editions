from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .adapters import (
    CambridgeCoreAdapter,
    CrossrefAdapter,
    EuropePmcAdapter,
    PubMedAdapter,
    RadarRssAdapter,
    RscChemicalScienceAdapter,
    TmlrOfficialSnapshotAdapter,
)
from .dedup_v2 import counts_by_source, deduplicate_articles, journal_matches
from .http import HttpClient
from .models import EditionSpec
from .naming import build_identity
from .radar_config import load_radar_hints
from .utils import period_overlaps, utc_now_iso

UPSTREAM_REPOSITORY = "hoiyu915-droid/EvidenceRadar"
RECONSTRUCTION_SEMANTICS = (
    "current_source_reconstruction_of_historical_publication_window"
)


def build_run(
    spec: EditionSpec,
    *,
    radar_root: Path | None = None,
    radar_commit: str | None = None,
    client: HttpClient | None = None,
) -> dict[str, Any]:
    client = client or HttpClient()
    hints = load_radar_hints(
        radar_root,
        journal=spec.journal,
        issn=spec.issn,
        explicit_commit=radar_commit,
    )
    adapters = {
        "pubmed": PubMedAdapter(client),
        "europe_pmc": EuropePmcAdapter(client),
        "crossref": CrossrefAdapter(client),
        "radar_rss": RadarRssAdapter(client, hints),
        "rsc_chemical_science": RscChemicalScienceAdapter(client),
        "cambridge_core": CambridgeCoreAdapter(client),
        "tmlr_official_snapshot": TmlrOfficialSnapshotAdapter(client),
    }
    accepted = []
    checks = []
    for source in spec.sources:
        result = adapters[source].fetch(spec)
        filtered = [
            article
            for article in result.articles
            if period_overlaps(
                article.publication_date,
                article.publication_date_precision,
                spec.start_date,
                spec.end_date,
            )
            and journal_matches(article, journal=spec.journal, issn=spec.issn)
        ]
        result.check.accepted_count = len(filtered)
        checks.append(result.check)
        accepted.extend(filtered)

    articles = deduplicate_articles(accepted)
    active_statuses = [
        check.status for check in checks if check.source != "radar_rss"
    ]
    if active_statuses and all(status == "FAILED" for status in active_statuses):
        run_status = "SOURCE_ACCESS_GAP"
    elif any(status in {"FAILED", "PARTIAL"} for status in active_statuses):
        run_status = "PARTIAL_SOURCE_COVERAGE"
    elif articles:
        run_status = "COMPLETE"
    else:
        run_status = "NO_MATCHING_ARTICLES"
    type_counts = Counter((article.article_type or "unspecified") for article in articles)
    identity = build_identity(
        slug=spec.slug,
        start=spec.start_date,
        end=spec.end_date,
        period_kind_requested=spec.period_kind,
        revision=spec.revision,
    )
    scope = spec.to_dict()
    scope.update(identity.to_dict())
    artifact_stem = identity.artifact_stem
    return {
        "schema_version": "2.0",
        "artifact_type": "EvidenceRadar_Edition",
        "edition_id": identity.publication_id,
        "edition_key": identity.edition_key,
        "publication_id": identity.publication_id,
        "retrieved_at": utc_now_iso(),
        "run_status": run_status,
        "data_semantics": RECONSTRUCTION_SEMANTICS,
        "scope": scope,
        "presentation": {
            "default_language": "zh-TW",
            "html_language": "zh-Hant",
            "preserve_original_title": True,
            "interactive_filters": True,
            "translation_required_for_publication": True,
        },
        "translation": {
            "language": "zh-TW",
            "status": "NOT_REQUIRED" if not articles else "NOT_REQUESTED",
            "translated_articles": 0,
            "total_articles": len(articles),
            "source_edition_sha256": None,
            "request_binding_sha256": None,
            "response_sha256": None,
        },
        "artifacts": {
            "stem": artifact_stem,
            "edition_json": f"{artifact_stem}.json",
            "report_html": f"{artifact_stem}.html",
            "manifest_json": f"{artifact_stem}.manifest.json",
            "translation_request_json": f"{artifact_stem}.translation-request.zh-TW.json",
            "translation_response_json": f"{artifact_stem}.translation-response.zh-TW.json",
        },
        "upstream_radar": {
            "repository": UPSTREAM_REPOSITORY,
            "commit": hints.upstream_commit,
            "control_plane": "config/radar_master.json",
            "matched_source_ids": list(hints.matched_source_ids),
            "config_sha256": hints.config_sha256,
            "uses_radar_output_artifacts": False,
        },
        "source_checks": [check.to_dict() for check in checks],
        "counts": {
            "articles": len(articles),
            "translated_articles": 0,
            "by_source": counts_by_source(articles),
            "by_article_type": dict(sorted(type_counts.items())),
        },
        "articles": [article.to_dict() for article in articles],
    }
