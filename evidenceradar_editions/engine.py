from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .adapters import CrossrefAdapter, EuropePmcAdapter, PubMedAdapter, RadarRssAdapter
from .dedup import counts_by_source, deduplicate_articles, journal_matches
from .http import HttpClient
from .models import EditionSpec
from .radar_config import load_radar_hints
from .utils import utc_now_iso

UPSTREAM_REPOSITORY = "hoiyu915-droid/EvidenceRadar"
RECONSTRUCTION_SEMANTICS = "current_source_reconstruction_of_historical_publication_window"


def build_run(spec: EditionSpec, *, radar_root: Path | None = None, radar_commit: str | None = None, client: HttpClient | None = None) -> dict[str, Any]:
    client = client or HttpClient()
    hints = load_radar_hints(radar_root, journal=spec.journal, issn=spec.issn, explicit_commit=radar_commit)
    adapters = {
        "pubmed": PubMedAdapter(client),
        "europe_pmc": EuropePmcAdapter(client),
        "crossref": CrossrefAdapter(client),
        "radar_rss": RadarRssAdapter(client, hints),
    }
    accepted = []
    checks = []
    for source in spec.sources:
        result = adapters[source].fetch(spec)
        filtered = [
            article for article in result.articles
            if spec.start_date <= article.publication_date <= spec.end_date
            and journal_matches(article, journal=spec.journal, issn=spec.issn)
        ]
        result.check.accepted_count = len(filtered)
        checks.append(result.check)
        accepted.extend(filtered)

    articles = deduplicate_articles(accepted)
    type_counts = Counter((article.article_type or "unspecified") for article in articles)
    edition_id = f"{spec.slug}__{spec.start_date.isoformat()}__{spec.end_date.isoformat()}"
    return {
        "schema_version": "1.0",
        "artifact_type": "EvidenceRadar_Edition",
        "edition_id": edition_id,
        "retrieved_at": utc_now_iso(),
        "data_semantics": RECONSTRUCTION_SEMANTICS,
        "scope": spec.to_dict(),
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
            "by_source": counts_by_source(articles),
            "by_article_type": dict(sorted(type_counts.items())),
        },
        "articles": [article.to_dict() for article in articles],
    }
