from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from .pages_curation import classify_publication_role
from .pages_search import latest_publications
from .processing_policy import (
    apply_volume_guard,
    load_processing_policy_catalog,
    policy_for_slug,
)
from .triage_policy import load_triage_policy
from .utils import utc_now_iso

_WORD_RE = re.compile(r"[A-Za-z0-9]+")
_SIGNAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "GUIDANCE",
        re.compile(
            r"\bclinical practice guideline(?:s)?\b|"
            r"\bguideline(?:s)?\b|"
            r"\bconsensus (?:statement|guideline|recommendation|report)\b|"
            r"\bexpert consensus\b|"
            r"\bposition statement\b",
            re.IGNORECASE,
        ),
    ),
    (
        "EVIDENCE_SYNTHESIS",
        re.compile(
            r"\bsystematic review\b|"
            r"\bmeta[- ]analysis\b|"
            r"\bumbrella review\b|"
            r"\bscoping review\b|"
            r"\bnetwork meta[- ]analysis\b",
            re.IGNORECASE,
        ),
    ),
    (
        "RANDOMIZED_TRIAL",
        re.compile(
            r"\brandomi[sz]ed(?: controlled)? trial\b|"
            r"\brandomised(?: controlled)? trial\b|"
            r"\bcluster[- ]randomi[sz]ed\b|"
            r"\brandomly assigned\b",
            re.IGNORECASE,
        ),
    ),
    (
        "REPLICATION_VALIDATION",
        re.compile(
            r"\breplication(?: study)?\b|"
            r"\breproducib(?:ility|le)\b|"
            r"\bexternal validation\b|"
            r"\bindependent validation\b|"
            r"\bmulticent(?:re|er) validation\b|"
            r"\bvalidation study\b",
            re.IGNORECASE,
        ),
    ),
    (
        "SAFETY_SIGNAL",
        re.compile(
            r"\b(?:drug|treatment|clinical|patient|model|system|vaccine|device|"
            r"surgical|medication) safety\b|"
            r"\badverse (?:event|effect|outcome|reaction)s?\b|"
            r"\btoxicit(?:y|ies)\b|"
            r"\bself-harm\b|"
            r"\bmortality\b",
            re.IGNORECASE,
        ),
    ),
    (
        "RESOURCE_BENCHMARK",
        re.compile(
            r"\bbenchmark(?:ing)?\b|"
            r"\bdataset\b|"
            r"\bdata set\b|"
            r"\bcorpus\b|"
            r"\bopen database\b|"
            r"\breference database\b|"
            r"\bdata resource\b",
            re.IGNORECASE,
        ),
    ),
    (
        "PROSPECTIVE_LONGITUDINAL",
        re.compile(
            r"\bprospective\b|\bcohort study\b|\blongitudinal\b",
            re.IGNORECASE,
        ),
    ),
    (
        "OBSERVATIONAL_DESIGN",
        re.compile(
            r"\bretrospective\b|\bcase-control\b|\bcross[- ]sectional\b",
            re.IGNORECASE,
        ),
    ),
)
_SURVEY_RE = re.compile(r"\bsurvey\b", re.IGNORECASE)
_PROTOCOL_RE = re.compile(
    r"\b(?:study |trial )?protocol(?:\s+for|\s*:|\s*$)|^\s*protocol\b",
    re.IGNORECASE,
)
_CASE_RE = re.compile(r"\bcase report\b|\bcase series\b", re.IGNORECASE)
_ROUTE_ORDER = {
    "INTEGRITY_REVIEW": 0,
    "FETCH_CANDIDATE": 1,
    "RESERVE": 2,
    "CATALOG_ONLY": 3,
}


def _title(article: Mapping[str, Any]) -> str:
    return str(article.get("title_original") or article.get("title") or "").strip()


def _path_score(policy: Mapping[str, Any], path: str) -> int:
    return int((policy["paths"][path])["score"])


def extract_paths(
    article: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> tuple[str, list[str], str]:
    title = _title(article)
    role = classify_publication_role(title)
    if role == "concern":
        return role, ["INTEGRITY_EVENT"], "INTEGRITY_EVENT"
    if role == "correction":
        return role, ["CORRECTION_EVENT"], "CORRECTION_EVENT"
    if role == "editorial":
        return role, ["EDITORIAL"], "EDITORIAL"

    paths = [name for name, pattern in _SIGNAL_PATTERNS if pattern.search(title)]
    if _SURVEY_RE.search(title):
        paths.append("SURVEY")
    if _PROTOCOL_RE.search(title):
        paths.append("PROTOCOL")
    if _CASE_RE.search(title):
        paths.append("CASE_REPORT")
    if not paths:
        paths = ["PRIMARY_METADATA"]
    primary = max(paths, key=lambda name: (_path_score(policy, name), name))
    return role, sorted(set(paths)), primary


def _identifier_bonus(
    article: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> tuple[int, list[str]]:
    bonus = 0
    reasons: list[str] = []
    configured = policy["identifier_bonus"]
    if article.get("pmcid"):
        bonus += int(configured["pmcid"])
        reasons.append("PMCID_ROUTE")
    elif article.get("pmid"):
        bonus += int(configured["pmid"])
        reasons.append("PMID_ROUTE")
    if article.get("doi"):
        bonus += int(configured["doi"])
        reasons.append("DOI_ROUTE")
    return bonus, reasons


def _specificity_bonus(
    title: str,
    policy: Mapping[str, Any],
) -> tuple[int, list[str]]:
    token_count = len(_WORD_RE.findall(title))
    configured = policy["title_specificity_bonus"]
    bonus = 0
    reasons: list[str] = []
    if token_count >= int(configured["minimum_tokens"]):
        bonus += int(configured["bonus"])
        reasons.append("TITLE_SPECIFICITY_1")
    if token_count >= int(configured["second_minimum_tokens"]):
        bonus += int(configured["second_bonus"])
        reasons.append("TITLE_SPECIFICITY_2")
    return bonus, reasons


def _initial_record(
    publication: Any,
    article: Mapping[str, Any],
    *,
    categories: list[str],
    processing_mode: str,
    processing_policy_source: str,
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    title = _title(article)
    role, paths, primary_path = extract_paths(article, policy)
    identifier_bonus, identifier_reasons = _identifier_bonus(article, policy)
    specificity_bonus, specificity_reasons = _specificity_bonus(title, policy)
    base_score = _path_score(policy, primary_path)
    raw_score = min(100, base_score + identifier_bonus + specificity_bonus)
    scope = publication.edition.get("scope") or {}
    return {
        "canonical_id": article.get("canonical_id"),
        "journal": scope.get("journal") or article.get("journal"),
        "journal_slug": publication.journal_slug,
        "period_key": publication.period_key,
        "revision": int(publication.revision),
        "publication_date": article.get("publication_date"),
        "publication_date_precision": article.get("publication_date_precision"),
        "title_original": title,
        "title_zh_tw": article.get("title_zh_tw"),
        "article_type": article.get("article_type") or "unspecified",
        "authors": [str(value) for value in (article.get("authors") or []) if value],
        "identifiers": {
            "doi": article.get("doi"),
            "pmid": article.get("pmid"),
            "pmcid": article.get("pmcid"),
        },
        "source_urls": [str(value) for value in (article.get("urls") or []) if value],
        "categories": list(categories),
        "publication_role": role,
        "matched_paths": paths,
        "primary_path": primary_path,
        "score": raw_score,
        "raw_score": raw_score,
        "score_components": {
            "base": base_score,
            "identifier_bonus": identifier_bonus,
            "title_specificity_bonus": specificity_bonus,
            "saturation_penalty": 0,
        },
        "reason_codes": [primary_path, *identifier_reasons, *specificity_reasons],
        "route": None,
        "processing_mode": processing_mode,
        "processing_policy_source": processing_policy_source,
        "journal_soft_cap": None,
        "journal_soft_cap_demoted": False,
        "full_text_requested": False,
        "full_text_fetched": False,
        "abstract_reviewed": False,
        "evidence_evaluated": False,
        "fetch_status": "NOT_REQUESTED",
        "edition_url": publication.relative_path,
        "canonical_json_url": publication.relative_path + "edition.json",
    }


def _apply_saturation(
    records: list[dict[str, Any]],
    policy: Mapping[str, Any],
) -> None:
    configuration = policy["signal_saturation"]
    eligible_paths = set(configuration["paths"])
    minimum_matches = int(configuration["minimum_matches"])
    prevalence_threshold = float(configuration["prevalence_threshold"])
    penalty = int(configuration["penalty"])

    journal_totals = Counter(str(record["journal_slug"]) for record in records)
    path_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for record in records:
        slug = str(record["journal_slug"])
        for path in set(record["matched_paths"]):
            path_counts[slug][path] += 1

    for record in records:
        slug = str(record["journal_slug"])
        primary = str(record["primary_path"])
        match_count = int(path_counts[slug][primary])
        total = int(journal_totals[slug])
        prevalence = match_count / total if total else 0.0
        saturated = (
            primary in eligible_paths
            and match_count >= minimum_matches
            and prevalence >= prevalence_threshold
        )
        record["signal_prevalence"] = {
            "journal_match_count": match_count,
            "journal_article_count": total,
            "journal_prevalence": round(prevalence, 6),
            "saturation_applied": saturated,
        }
        if saturated:
            record["score"] = max(0, int(record["score"]) - penalty)
            record["score_components"]["saturation_penalty"] = penalty
            record["reason_codes"].append("COMMON_SOURCE_PATTERN")


def _assign_initial_routes(
    records: list[dict[str, Any]],
    policy: Mapping[str, Any],
) -> None:
    fetch_threshold = int(policy["thresholds"]["fetch_candidate"])
    reserve_threshold = int(policy["thresholds"]["reserve"])
    for record in records:
        role = str(record["publication_role"])
        primary = str(record["primary_path"])
        if role in {"concern", "correction"}:
            route = "INTEGRITY_REVIEW"
        elif primary == "EDITORIAL":
            route = "CATALOG_ONLY"
        elif int(record["score"]) >= fetch_threshold:
            route = "FETCH_CANDIDATE"
        elif int(record["score"]) >= reserve_threshold:
            route = "RESERVE"
        else:
            route = "CATALOG_ONLY"
        record["route"] = route


def _apply_journal_soft_caps(
    records: list[dict[str, Any]],
    policy: Mapping[str, Any],
) -> None:
    exceptional = int(policy["thresholds"]["exceptional_bypass"])
    by_journal: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_journal[str(record["journal_slug"])].append(record)

    for journal_records in by_journal.values():
        mode = str(journal_records[0]["processing_mode"])
        cap = int(policy["journal_soft_caps"][mode])
        candidates = [
            record for record in journal_records if record["route"] == "FETCH_CANDIDATE"
        ]
        for record in candidates:
            record["journal_soft_cap"] = cap
        exceptional_records = [
            record for record in candidates if int(record["score"]) >= exceptional
        ]
        regular_records = [
            record for record in candidates if int(record["score"]) < exceptional
        ]
        regular_records.sort(
            key=lambda record: (
                -int(record["score"]),
                -int(
                    str(record.get("publication_date") or "0000-00-00").replace("-", "")
                    or 0
                ),
                str(record.get("title_original") or "").casefold(),
                str(record.get("canonical_id") or ""),
            )
        )
        remaining = max(0, cap - len(exceptional_records))
        keep = {id(record) for record in exceptional_records}
        keep.update(id(record) for record in regular_records[:remaining])
        for record in candidates:
            if id(record) in keep:
                continue
            record["route"] = "RESERVE"
            record["journal_soft_cap_demoted"] = True
            record["reason_codes"].append("JOURNAL_SOFT_CAP")


def _record_sort_key(record: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        _ROUTE_ORDER.get(str(record.get("route")), 99),
        -int(record.get("score") or 0),
        str(record.get("journal") or "").casefold(),
        str(record.get("publication_date") or ""),
        str(record.get("title_original") or "").casefold(),
        str(record.get("canonical_id") or ""),
    )


def _summary(
    records: list[dict[str, Any]],
    *,
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    route_counts = Counter(str(record["route"]) for record in records)
    path_counts = Counter(
        str(record["primary_path"])
        for record in records
        if record["route"] in {"INTEGRITY_REVIEW", "FETCH_CANDIDATE", "RESERVE"}
    )
    mode_counts = Counter(str(record["processing_mode"]) for record in records)
    journal_summaries: list[dict[str, Any]] = []
    by_journal: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_journal[str(record["journal_slug"])].append(record)
    for slug, values in by_journal.items():
        counts = Counter(str(record["route"]) for record in values)
        journal_summaries.append(
            {
                "journal": values[0]["journal"],
                "journal_slug": slug,
                "processing_mode": values[0]["processing_mode"],
                "canonical_article_count": len(values),
                "integrity_review_count": counts["INTEGRITY_REVIEW"],
                "fetch_candidate_count": counts["FETCH_CANDIDATE"],
                "reserve_count": counts["RESERVE"],
                "catalog_only_count": counts["CATALOG_ONLY"],
                "soft_cap_demoted_count": sum(
                    1 for record in values if record["journal_soft_cap_demoted"]
                ),
                "saturation_penalty_count": sum(
                    1
                    for record in values
                    if record["signal_prevalence"]["saturation_applied"]
                ),
                "triage_json_url": values[0]["edition_url"] + "triage.json",
            }
        )
    journal_summaries.sort(
        key=lambda item: (
            -int(item["fetch_candidate_count"]),
            -int(item["integrity_review_count"]),
            str(item["journal"]).casefold(),
        )
    )
    return {
        "canonical_article_count": len(records),
        "integrity_review_count": route_counts["INTEGRITY_REVIEW"],
        "fetch_candidate_count": route_counts["FETCH_CANDIDATE"],
        "reserve_count": route_counts["RESERVE"],
        "catalog_only_count": route_counts["CATALOG_ONLY"],
        "actionable_count": (
            route_counts["INTEGRITY_REVIEW"] + route_counts["FETCH_CANDIDATE"]
        ),
        "published_index_count": (
            route_counts["INTEGRITY_REVIEW"]
            + route_counts["FETCH_CANDIDATE"]
            + route_counts["RESERVE"]
        ),
        "processing_mode_article_counts": dict(sorted(mode_counts.items())),
        "primary_path_counts": dict(sorted(path_counts.items())),
        "thresholds": dict(policy["thresholds"]),
        "journal_summaries": journal_summaries,
    }


def build_prefetch_triage(
    publications: Iterable[Any],
    *,
    catalog_root: Path | str = Path("catalog"),
    generated_at: str | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Build a portfolio triage index and full per-edition audit artifacts.

    The function uses title and bibliographic metadata only. It never fetches
    abstracts or full text and never assigns evidence quality or novelty.
    """

    resolved_catalog_root = Path(catalog_root)
    triage_policy = load_triage_policy(resolved_catalog_root)
    processing_catalog = load_processing_policy_catalog(resolved_catalog_root)
    registry = _load_registry(resolved_catalog_root)
    registry_by_slug = {
        str(item["slug"]): item
        for item in registry.get("journals") or []
        if isinstance(item, dict) and item.get("slug")
    }

    current = latest_publications(publications)
    records: list[dict[str, Any]] = []
    publication_ids: dict[tuple[str, str, int], str] = {}
    for publication in current:
        article_count = len(publication.edition.get("articles") or [])
        processing = apply_volume_guard(
            policy_for_slug(
                publication.journal_slug,
                catalog_root=resolved_catalog_root,
                catalog=processing_catalog,
            ),
            observed_total=article_count,
        )
        registry_item = registry_by_slug.get(publication.journal_slug) or {}
        categories = [
            str(value) for value in (registry_item.get("categories") or []) if str(value)
        ]
        manifest = getattr(publication, "manifest", {}) or {}
        publication_id = str(
            manifest.get("publication_id")
            or publication.edition.get("publication_id")
            or publication.edition.get("edition_id")
            or f"{publication.journal_slug}__{publication.period_key}__r{publication.revision:02d}"
        )
        publication_ids[
            (publication.journal_slug, publication.period_key, int(publication.revision))
        ] = publication_id
        for article in publication.edition.get("articles") or []:
            if not isinstance(article, dict):
                continue
            records.append(
                _initial_record(
                    publication,
                    article,
                    categories=categories,
                    processing_mode=processing.effective_mode,
                    processing_policy_source=processing.policy_source,
                    policy=triage_policy,
                )
            )

    _apply_saturation(records, triage_policy)
    _assign_initial_routes(records, triage_policy)
    _apply_journal_soft_caps(records, triage_policy)
    records.sort(key=_record_sort_key)
    summary = _summary(records, policy=triage_policy)
    generated = generated_at or utc_now_iso()

    published_records = [
        record
        for record in records
        if record["route"] in {"INTEGRITY_REVIEW", "FETCH_CANDIDATE", "RESERVE"}
    ]
    index = {
        "schema_version": "1.0",
        "artifact_type": "EvidenceRadar_Editions_PrefetchTriageIndex",
        "generated_at": generated,
        "semantics": (
            "Title-and-metadata pre-fetch triage. Routes indicate operational "
            "attention or fetch priority only; they do not assert relevance, "
            "novelty, evidence quality, abstract review, or full-text verification."
        ),
        "policy_file": "prefetch-triage-policy.json",
        "policy": {
            "thresholds": triage_policy["thresholds"],
            "journal_soft_caps": triage_policy["journal_soft_caps"],
            "signal_saturation": triage_policy["signal_saturation"],
        },
        "counts": {
            key: value
            for key, value in summary.items()
            if key
            not in {
                "journal_summaries",
                "thresholds",
                "primary_path_counts",
                "processing_mode_article_counts",
            }
        },
        "processing_mode_article_counts": summary["processing_mode_article_counts"],
        "primary_path_counts": summary["primary_path_counts"],
        "journal_summaries": summary["journal_summaries"],
        "item_count": len(published_records),
        "items": published_records,
    }

    per_edition_records: defaultdict[tuple[str, str, int], list[dict[str, Any]]] = (
        defaultdict(list)
    )
    for record in records:
        per_edition_records[
            (
                str(record["journal_slug"]),
                str(record["period_key"]),
                int(record["revision"]),
            )
        ].append(record)

    edition_artifacts: dict[str, dict[str, Any]] = {}
    for key, values in per_edition_records.items():
        slug, period_key, revision = key
        counts = Counter(str(record["route"]) for record in values)
        relative = str(values[0]["edition_url"])
        publication_id = publication_ids[key]
        edition_artifacts[relative] = {
            "schema_version": "1.0",
            "artifact_type": "EvidenceRadar_Editions_EditionPrefetchTriage",
            "generated_at": generated,
            "publication_id": publication_id,
            "journal": values[0]["journal"],
            "journal_slug": slug,
            "period_key": period_key,
            "revision": revision,
            "processing_mode": values[0]["processing_mode"],
            "semantics": index["semantics"],
            "counts": {
                "canonical_article_count": len(values),
                "integrity_review_count": counts["INTEGRITY_REVIEW"],
                "fetch_candidate_count": counts["FETCH_CANDIDATE"],
                "reserve_count": counts["RESERVE"],
                "catalog_only_count": counts["CATALOG_ONLY"],
            },
            "articles": sorted(values, key=_record_sort_key),
        }
    return index, edition_artifacts


def _load_registry(catalog_root: Path) -> dict[str, Any]:
    import json

    path = catalog_root / "journals.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("journal registry must be a JSON object")
    return value
