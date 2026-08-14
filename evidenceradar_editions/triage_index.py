from __future__ import annotations

from collections import Counter, defaultdict, deque
from typing import Any, Iterable, Mapping

from .metadata_triage import ALLOWED_TIERS, triage_counts, triage_sort_key
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
            str(
                (publication.edition.get("scope") or {}).get("end_date")
                or ""
            ),
            str(
                (publication.edition.get("scope") or {}).get("journal")
                or ""
            ).casefold(),
            int(publication.revision),
        ),
        reverse=True,
    )


def _result_for_publication(
    publication: Any,
    results: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Any]:
    for result in results.values():
        candidate = result.get("publication")
        if candidate is None:
            continue
        if (
            str(candidate.journal_slug) == str(publication.journal_slug)
            and str(candidate.period_key) == str(publication.period_key)
            and int(candidate.revision) == int(publication.revision)
        ):
            return result
    raise KeyError(
        "triage result is missing for "
        f"{publication.journal_slug}/{publication.period_key}/r{publication.revision}"
    )


def _article_record(
    article: Mapping[str, Any],
    *,
    publication: Any,
    journal_record: Mapping[str, Any],
    processing_mode: str,
) -> dict[str, Any]:
    scope = publication.edition.get("scope") or {}
    return {
        "canonical_id": article.get("canonical_id"),
        "title_zh_tw": article.get("title_zh_tw"),
        "title_original": article.get("title_original") or article.get("title"),
        "publication_date": article.get("publication_date"),
        "publication_date_precision": article.get(
            "publication_date_precision"
        ) or "DAY",
        "article_type": article.get("article_type") or "unspecified",
        "authors": [str(value) for value in (article.get("authors") or []) if value],
        "doi": article.get("doi"),
        "pmid": article.get("pmid"),
        "pmcid": article.get("pmcid"),
        "sources": [str(value) for value in (article.get("sources") or []) if value],
        "curation_role": article.get("curation_role") or "primary",
        "default_projected": bool(article.get("default_projected")),
        "metadata_triage": article.get("metadata_triage") or {},
        "journal": str(scope.get("journal") or publication.journal_slug),
        "journal_slug": str(publication.journal_slug),
        "publisher": journal_record.get("publisher"),
        "categories": [
            str(value) for value in (journal_record.get("categories") or []) if value
        ],
        "period_key": str(publication.period_key),
        "revision": int(publication.revision),
        "processing_mode": processing_mode,
        "url": str(publication.relative_path),
    }


def _fair_global_order(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Interleave journals within each tier so one megajournal cannot own page one."""

    tier_rank = {tier: index for index, tier in enumerate(ALLOWED_TIERS)}
    grouped: defaultdict[
        tuple[int, str], list[dict[str, Any]]
    ] = defaultdict(list)
    for item in items:
        triage = item.get("metadata_triage") or {}
        tier = str(triage.get("tier") or "MEDIUM")
        grouped[
            (tier_rank.get(tier, len(ALLOWED_TIERS)), str(item["journal_slug"]))
        ].append(item)
    for values in grouped.values():
        values.sort(key=triage_sort_key)

    ordered: list[dict[str, Any]] = []
    for tier_index in range(len(ALLOWED_TIERS)):
        queues = {
            journal: deque(values)
            for (observed_tier, journal), values in grouped.items()
            if observed_tier == tier_index
        }
        journals = sorted(
            queues,
            key=lambda journal: (
                triage_sort_key(queues[journal][0]),
                journal,
            ),
        )
        while any(queues[journal] for journal in journals):
            for journal in journals:
                if queues[journal]:
                    ordered.append(queues[journal].popleft())
    for rank, item in enumerate(ordered, start=1):
        item["global_triage_rank"] = rank
    return ordered


def build_metadata_triage_indices(
    publications: Iterable[Any],
    *,
    triage_results: Mapping[str, Mapping[str, Any]],
    registry_by_slug: Mapping[str, Mapping[str, Any]],
    policy_id: str,
    generated_at: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    generated = generated_at or utc_now_iso()
    all_records: list[dict[str, Any]] = []
    projected_records: list[dict[str, Any]] = []
    edition_summaries: list[dict[str, Any]] = []
    mode_counts: Counter[str] = Counter()

    for publication in latest_publications(publications):
        result = _result_for_publication(publication, triage_results)
        effective = result["effective_processing_policy"]
        browse = result["browse"]
        all_articles = result["all_articles"]
        journal_record = registry_by_slug.get(publication.journal_slug) or {}
        processing_mode = str(effective.effective_mode)
        mode_counts[processing_mode] += 1

        records = [
            _article_record(
                article,
                publication=publication,
                journal_record=journal_record,
                processing_mode=processing_mode,
            )
            for article in all_articles
        ]
        projected = [record for record in records if record["default_projected"]]
        all_records.extend(records)
        projected_records.extend(projected)
        projection = browse.get("projection") or {}
        edition_summaries.append(
            {
                "journal": (
                    publication.edition.get("scope") or {}
                ).get("journal"),
                "journal_slug": publication.journal_slug,
                "period_key": publication.period_key,
                "revision": int(publication.revision),
                "processing_mode_configured": effective.configured_mode,
                "processing_mode_effective": effective.effective_mode,
                "policy_source": effective.policy_source,
                "canonical_article_count": int(
                    projection.get("canonical_article_count") or 0
                ),
                "projected_article_count": int(
                    projection.get("projected_article_count") or 0
                ),
                "omitted_article_count": int(
                    projection.get("omitted_article_count") or 0
                ),
                "volume_guard_triggered": bool(
                    projection.get("volume_guard_triggered")
                ),
                "triage_counts": (browse.get("metadata_triage") or {}).get(
                    "canonical_counts"
                ) or {},
                "url": publication.relative_path,
            }
        )

    all_records = _fair_global_order(all_records)
    projected_ids = {
        (
            record.get("journal_slug"),
            record.get("period_key"),
            record.get("revision"),
            record.get("canonical_id"),
        )
        for record in projected_records
    }
    projected_records = [
        record
        for record in all_records
        if (
            record.get("journal_slug"),
            record.get("period_key"),
            record.get("revision"),
            record.get("canonical_id"),
        )
        in projected_ids
    ]

    canonical_count = len(all_records)
    projected_count = len(projected_records)
    omitted_count = canonical_count - projected_count
    canonical_triage_counts = triage_counts(all_records)
    projected_triage_counts = triage_counts(projected_records)
    tier_counts = canonical_triage_counts.get("by_tier") or {}
    priority_count = int(tier_counts.get("ALERT", 0)) + int(
        tier_counts.get("HIGH", 0)
    )

    triage_index = {
        "schema_version": "1.0",
        "artifact_type": "EvidenceRadar_Editions_MetadataTriageIndex",
        "generated_at": generated,
        "policy_id": policy_id,
        "basis": "TITLE_AND_BIBLIOGRAPHIC_METADATA",
        "semantics": (
            "All latest-revision canonical records receive a deterministic metadata "
            "tier. This index is loaded only by the triage dashboard; canonical edition "
            "JSON remains authoritative and unchanged."
        ),
        "canonical_article_count": canonical_count,
        "priority_candidate_count": priority_count,
        "default_projected_article_count": projected_count,
        "default_omitted_article_count": omitted_count,
        "processing_mode_counts": dict(sorted(mode_counts.items())),
        "canonical_triage_counts": canonical_triage_counts,
        "projected_triage_counts": projected_triage_counts,
        "edition_count": len(edition_summaries),
        "edition_summaries": edition_summaries,
        "articles": all_records,
    }

    search_articles = [
        {
            "canonical_id": record.get("canonical_id"),
            "title_zh_tw": record.get("title_zh_tw"),
            "title_original": record.get("title_original"),
            "doi": record.get("doi"),
            "pmid": record.get("pmid"),
            "pmcid": record.get("pmcid"),
            "journal": record.get("journal"),
            "journal_slug": record.get("journal_slug"),
            "period_key": record.get("period_key"),
            "revision": record.get("revision"),
            "curation_role": record.get("curation_role"),
            "processing_mode": record.get("processing_mode"),
            "metadata_triage": record.get("metadata_triage"),
            "global_triage_rank": record.get("global_triage_rank"),
            "url": record.get("url"),
        }
        for record in projected_records
    ]
    search_index = {
        "schema_version": "1.4",
        "artifact_type": "EvidenceRadar_Editions_SearchIndex",
        "generated_at": generated,
        "semantics": "latest_revision_per_journal_period_metadata_triage_projected",
        "article_count": projected_count,
        "canonical_article_count": canonical_count,
        "priority_candidate_count": priority_count,
        "projected_article_count": projected_count,
        "omitted_article_count": omitted_count,
        "processing_mode_counts": dict(sorted(mode_counts.items())),
        "metadata_triage_policy_id": policy_id,
        "canonical_triage_counts": canonical_triage_counts,
        "projected_triage_counts": projected_triage_counts,
        "projection_semantics": (
            "Default portal search contains the bounded metadata-triage projection. "
            "Omitted records remain in canonical edition JSON and in the on-demand "
            "metadata triage index. Priority is operational, not evidence-quality or "
            "relevance grading."
        ),
        "edition_projections": edition_summaries,
        "articles": search_articles,
    }
    return triage_index, search_index
