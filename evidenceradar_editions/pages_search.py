from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .pages_volume import build_projected_browse_index
from .processing_policy import load_processing_policy_catalog, policy_for_slug
from .utils import utc_now_iso


def latest_publications(publications: Iterable[Any]) -> list[Any]:
    """Return the highest revision for each journal/period identity."""

    latest: dict[tuple[str, str], Any] = {}
    for publication in publications:
        key = (str(publication.journal_slug), str(publication.period_key))
        current = latest.get(key)
        if current is None or int(publication.revision) > int(current.revision):
            latest[key] = publication
    return sorted(
        latest.values(),
        key=lambda publication: (
            str((publication.edition.get("scope") or {}).get("end_date") or ""),
            str((publication.edition.get("scope") or {}).get("journal") or "").casefold(),
            int(publication.revision),
        ),
        reverse=True,
    )


def build_projected_search_index(
    publications: Iterable[Any],
    *,
    catalog_root: Path | str = Path("catalog"),
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build the default portal search index from volume-aware projections.

    Canonical edition JSON remains the complete bibliographic archive. This
    index deliberately mirrors each latest revision's Pages projection so a
    high-volume edition is not re-expanded into the global browser payload.
    """

    policy_catalog = load_processing_policy_catalog(catalog_root)
    articles: list[dict[str, Any]] = []
    projections: list[dict[str, Any]] = []
    canonical_total = 0
    projected_total = 0
    omitted_total = 0
    mode_counts: Counter[str] = Counter()

    for publication in latest_publications(publications):
        policy = policy_for_slug(
            publication.journal_slug,
            catalog_root=catalog_root,
            catalog=policy_catalog,
        )
        browse, effective = build_projected_browse_index(publication, policy)
        projection = browse.get("projection") or {}
        canonical = int(projection.get("canonical_article_count") or 0)
        projected = int(projection.get("projected_article_count") or 0)
        omitted = int(projection.get("omitted_article_count") or 0)
        scope = publication.edition.get("scope") or {}
        journal = str(scope.get("journal") or publication.journal_slug)
        mode_counts[str(effective.effective_mode)] += 1
        canonical_total += canonical
        projected_total += projected
        omitted_total += omitted

        projections.append(
            {
                "journal": journal,
                "journal_slug": publication.journal_slug,
                "period_key": publication.period_key,
                "revision": int(publication.revision),
                "processing_mode_configured": effective.configured_mode,
                "processing_mode_effective": effective.effective_mode,
                "policy_source": effective.policy_source,
                "canonical_article_count": canonical,
                "projected_article_count": projected,
                "omitted_article_count": omitted,
                "volume_guard_triggered": effective.volume_guard_triggered,
            }
        )

        for article in browse.get("articles") or []:
            if not isinstance(article, dict):
                continue
            articles.append(
                {
                    "canonical_id": article.get("canonical_id"),
                    "title_zh_tw": article.get("title_zh_tw"),
                    "title_original": article.get("title_original"),
                    "doi": article.get("doi"),
                    "pmid": article.get("pmid"),
                    "pmcid": article.get("pmcid"),
                    "journal": journal,
                    "journal_slug": publication.journal_slug,
                    "period_key": publication.period_key,
                    "revision": int(publication.revision),
                    "curation_role": article.get("curation_role"),
                    "processing_mode": effective.effective_mode,
                    "url": publication.relative_path,
                }
            )

    return {
        "schema_version": "1.3",
        "artifact_type": "EvidenceRadar_Editions_SearchIndex",
        "generated_at": generated_at or utc_now_iso(),
        "semantics": "latest_revision_per_journal_period_volume_projected",
        "article_count": len(articles),
        "canonical_article_count": canonical_total,
        "projected_article_count": projected_total,
        "omitted_article_count": omitted_total,
        "processing_mode_counts": dict(sorted(mode_counts.items())),
        "projection_semantics": (
            "Default portal search mirrors the non-destructive Pages projection. "
            "Omitted records remain available in each edition's complete canonical JSON; "
            "projection is operational capacity control, not quality or relevance ranking."
        ),
        "edition_projections": projections,
        "articles": articles,
    }
