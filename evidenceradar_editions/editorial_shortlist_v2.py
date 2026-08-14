from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from .editorial_shortlist_v2_policy import (
    ABSTRACT_FETCH_PLAN_FILENAME, SHORTLIST_INDEX_FILENAME,
    SHORTLIST_PAGE_FILENAME, SHORTLIST_POLICY_FILENAME,
    EditorialShortlistPolicyV2Error, _ROUTES, _digest,
    builtin_editorial_shortlist_policy_v2, load_editorial_shortlist_policy_v2,
    validate_editorial_shortlist_policy_v2,
)
from .editorial_shortlist_v2_selection import (
    _fetchable, _flatten, _identifiers, _journal_contexts, _selection,
    _source_order,
)
from .journal_impact import (
    IMPACT_REGISTRY_FILENAME, impact_registry_sha256,
    load_journal_impact_registry, resolve_journal_impact_priors,
    validate_journal_impact_registry,
)
from .utils import utc_now_iso

def _decision(
    record: Mapping[str, Any],
    *,
    route: str,
    reasons: list[str],
    context: Mapping[str, Any],
    selection_ordinal: int | None,
) -> dict[str, Any]:
    if route not in _ROUTES:
        raise ValueError(f"unsupported editorial route: {route}")
    integrity = record.get("route") == "INTEGRITY_REVIEW"
    prior = dict(context.get("impact_prior") or {})
    return {
        "record_key": record["_record_key"],
        "canonical_id": record.get("canonical_id"),
        "journal": record.get("journal"),
        "journal_slug": record.get("journal_slug"),
        "period_key": record.get("period_key"),
        "revision": int(record.get("revision") or 0),
        "publication_date": record.get("publication_date"),
        "title_original": record.get("title_original"),
        "title_zh_tw": record.get("title_zh_tw"),
        "article_type": record.get("article_type"),
        "identifiers": _identifiers(record),
        "source_urls": list(record.get("source_urls") or []),
        "categories": list(record.get("categories") or []),
        "primary_category": record["_primary_category"],
        "topic_signature": record["_topic_signature"],
        "prefetch_route": record.get("route"),
        "prefetch_score": int(record.get("score") or 0),
        "primary_path": record.get("primary_path"),
        "matched_paths": list(record.get("matched_paths") or []),
        "processing_mode": record.get("processing_mode"),
        "editorial_route": route,
        "selection_ordinal": selection_ordinal,
        "decision_reasons": list(dict.fromkeys(reasons)),
        "journal_impact_prior": prior,
        "journal_metric_capture_band": context.get("capture_band"),
        "journal_metric_capture_rate": context.get("metric_capture_rate"),
        "journal_mode_capture_modifier": context.get("mode_capture_modifier"),
        "journal_adaptive_fetch_target": context.get("adaptive_fetch_target"),
        "journal_fetch_hard_cap": context.get("journal_fetch_hard_cap"),
        "integrity_attention": integrity,
        "integrity_action": "RECORD_MAINTENANCE" if integrity else "NONE",
        "abstract_fetch_eligible": route == "FETCH_NOW" and _fetchable(record),
        "abstract_fetch_requested": False,
        "abstract_acquired": False,
        "abstract_reviewed": False,
        "full_text_fetched": False,
        "evidence_evaluated": False,
        "edition_url": record.get("edition_url"),
        "canonical_json_url": record.get("canonical_json_url"),
    }

def _plan(
    fetch: list[dict[str, Any]],
    policy: Mapping[str, Any],
    *,
    shortlist_binding: str,
    impact_digest: str,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for ordinal, item in enumerate(fetch, 1):
        items.append(
            {
                "ordinal": ordinal,
                "record_key": item["record_key"],
                "canonical_id": item.get("canonical_id"),
                "journal": item.get("journal"),
                "journal_slug": item.get("journal_slug"),
                "period_key": item.get("period_key"),
                "revision": item.get("revision"),
                "title_original": item.get("title_original"),
                "identifiers": item.get("identifiers"),
                "source_order": _source_order(item, policy),
                "journal_metric_kind": (
                    item.get("journal_impact_prior") or {}
                ).get("primary_metric_kind"),
                "journal_registry_category_percentile": (
                    item.get("journal_impact_prior") or {}
                ).get("registry_category_percentile"),
                "selection_reasons": item.get("decision_reasons"),
                "status": "PLANNED",
                "abstract_fetch_requested": False,
                "abstract_acquired": False,
                "abstract_reviewed": False,
                "full_text_fetched": False,
                "evidence_evaluated": False,
            }
        )
    plan_binding = _digest(
        {
            "shortlist_binding_sha256": shortlist_binding,
            "impact_registry_sha256": impact_digest,
            "items": [
                {
                    "record_key": item["record_key"],
                    "identifiers": item["identifiers"],
                    "source_order": item["source_order"],
                    "journal_metric_kind": item["journal_metric_kind"],
                    "journal_registry_category_percentile": item[
                        "journal_registry_category_percentile"
                    ],
                    "selection_reasons": item["selection_reasons"],
                }
                for item in items
            ],
        }
    )
    return {
        "schema_version": "2.0",
        "artifact_type": "EvidenceRadar_Editions_AbstractFetchPlan",
        "semantics": (
            "At most 300 FETCH_NOW records selected from the public metric-aware "
            "shortlist. No network request has occurred and no abstract text is present."
        ),
        "shortlist_binding_sha256": shortlist_binding,
        "impact_registry_sha256": impact_digest,
        "plan_binding_sha256": plan_binding,
        "item_count": len(items),
        "items": items,
    }

def build_editorial_shortlist_v2(
    audits: Iterable[Mapping[str, Any]],
    *,
    policy: Mapping[str, Any] | None = None,
    impact_registry: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    p = validate_editorial_shortlist_policy_v2(
        policy or builtin_editorial_shortlist_policy_v2()
    )
    impact = validate_journal_impact_registry(
        impact_registry or load_journal_impact_registry(Path("catalog"))
    )
    records = _flatten(audits, p)
    slugs = {str(record.get("journal_slug") or "") for record in records}
    priors = resolve_journal_impact_priors(
        impact,
        journal_slugs=slugs,
        neutral_percentile=p["neutral_percentile"],
    )
    impact_digest = impact_registry_sha256(impact)
    contexts = _journal_contexts(records, priors, p)
    policy_digest = _digest(p)
    source_rows = [
        {
            "record_key": record["_record_key"],
            "prefetch_route": record.get("route"),
            "primary_path": record.get("primary_path"),
            "score": int(record.get("score") or 0),
            "reason_codes": list(record.get("reason_codes") or []),
            "processing_mode": record.get("processing_mode"),
            "identifiers": _identifiers(record),
        }
        for record in records
    ]
    source_digest = _digest(source_rows)
    state = _selection(records, contexts, p)
    selected_ordinals = {
        record["_record_key"]: ordinal
        for ordinal, record in enumerate(state.selected, 1)
    }

    decisions: list[dict[str, Any]] = []
    eligible_routes = set(p["eligible_prefetch_routes"])
    for record in records:
        key = record["_record_key"]
        slug = str(record.get("journal_slug") or "")
        if key in state.selected_keys:
            route = "FETCH_NOW"
            reasons = state.reasons.get(key, ["BOUNDED_SELECTION"])
        elif record.get("route") in eligible_routes:
            route = "HOLD_RESERVE"
            reasons = sorted(state.blocks.get(key, set()))
            if not _fetchable(record):
                reasons = ["NO_FETCHABLE_IDENTIFIER", *reasons]
            if not reasons:
                reasons = ["GLOBAL_MONTHLY_SOFT_CEILING"]
        else:
            route = "CATALOG_ONLY"
            if record.get("route") == "INTEGRITY_REVIEW":
                reasons = ["INTEGRITY_MAINTENANCE_NOT_ABSTRACT_FETCH"]
            else:
                reasons = ["PREFETCH_CATALOG_ONLY"]
        decisions.append(
            _decision(
                record,
                route=route,
                reasons=reasons,
                context=contexts[slug],
                selection_ordinal=selected_ordinals.get(key),
            )
        )

    decision_rows = [
        {
            "record_key": item["record_key"],
            "editorial_route": item["editorial_route"],
            "decision_reasons": item["decision_reasons"],
            "journal_registry_category_percentile": (
                item["journal_impact_prior"].get("registry_category_percentile")
            ),
            "journal_adaptive_fetch_target": item["journal_adaptive_fetch_target"],
        }
        for item in sorted(decisions, key=lambda value: value["record_key"])
    ]
    binding = _digest(
        {
            "policy_sha256": policy_digest,
            "impact_registry_sha256": impact_digest,
            "source_prefetch_digest": source_digest,
            "decisions": decision_rows,
        }
    )

    by_key = {item["record_key"]: item for item in decisions}
    fetch = [by_key[record["_record_key"]] for record in state.selected]
    hold = sorted(
        (item for item in decisions if item["editorial_route"] == "HOLD_RESERVE"),
        key=lambda item: (
            0 if item["prefetch_route"] == "FETCH_CANDIDATE" else 1,
            -float(item["journal_impact_prior"].get("registry_category_percentile", 50.0)),
            -item["prefetch_score"],
            str(item.get("journal") or "").casefold(),
            str(item.get("title_original") or "").casefold(),
        ),
    )
    integrity = [item for item in decisions if item["integrity_attention"]]
    plan = _plan(
        fetch,
        p,
        shortlist_binding=binding,
        impact_digest=impact_digest,
    )

    counts = Counter(item["editorial_route"] for item in decisions)
    metric_kind_counts = Counter(
        str(item["journal_impact_prior"].get("primary_metric_kind") or "UNKNOWN")
        for item in fetch
    )
    band_counts = Counter(str(item["journal_metric_capture_band"]) for item in fetch)
    path_counts = Counter(str(item["primary_path"]) for item in fetch)
    category_counts = Counter(str(item["primary_category"]) for item in fetch)
    journal_counts = Counter(str(item["journal_slug"]) for item in fetch)

    by_journal: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    by_edition: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in decisions:
        by_journal[str(item["journal_slug"])].append(item)
        by_edition[str(item.get("edition_url") or "")].append(item)

    journal_summaries: list[dict[str, Any]] = []
    for slug, values in sorted(
        by_journal.items(),
        key=lambda pair: (
            -sum(item["editorial_route"] == "FETCH_NOW" for item in pair[1]),
            -float(
                contexts[pair[0]]["impact_prior"].get(
                    "registry_category_percentile", 50.0
                )
            ),
            str(pair[1][0].get("journal") or "").casefold(),
        ),
    ):
        route_counts = Counter(item["editorial_route"] for item in values)
        context = contexts[slug]
        eligible_count = int(context["eligible_article_count"])
        journal_summaries.append(
            {
                **context,
                "fetch_now_count": route_counts["FETCH_NOW"],
                "hold_reserve_count": route_counts["HOLD_RESERVE"],
                "catalog_only_count": route_counts["CATALOG_ONLY"],
                "integrity_attention_count": sum(
                    item["integrity_attention"] for item in values
                ),
                "eligible_capture_fraction": round(
                    route_counts["FETCH_NOW"] / eligible_count, 6
                )
                if eligible_count
                else 0.0,
            }
        )

    root_keys = {item["record_key"] for item in [*fetch, *hold]}
    root_items = [*fetch, *hold]
    root_items.extend(item for item in integrity if item["record_key"] not in root_keys)
    generated = generated_at or utc_now_iso()
    known_metric_journals = sum(
        not context["impact_prior"].get("unknown_metric")
        for context in contexts.values()
    )
    known_metric_eligible = sum(
        int(context["eligible_article_count"])
        for context in contexts.values()
        if not context["impact_prior"].get("unknown_metric")
    )
    eligible_count = sum(
        record.get("route") in eligible_routes for record in records
    )
    fetchable_count = sum(
        record.get("route") in eligible_routes and _fetchable(record)
        for record in records
    )

    root = {
        "schema_version": "2.0",
        "artifact_type": "EvidenceRadar_Editions_EditorialShortlist",
        "generated_at": generated,
        "policy_id": p["policy_id"],
        "policy_file": SHORTLIST_POLICY_FILENAME,
        "policy_sha256": policy_digest,
        "impact_registry_file": IMPACT_REGISTRY_FILENAME,
        "impact_registry_sha256": impact_digest,
        "source_prefetch_digest": source_digest,
        "shortlist_binding_sha256": binding,
        "semantics": p["semantics"],
        "scientific_boundary": (
            "Journal metrics allocate abstract-fetch recall only. FETCH_NOW does "
            "not mean the article is relevant, valid, novel, clinically actionable, "
            "or supported by abstract/full text."
        ),
        "selection_algorithm": (
            "All fetchable precision-hardened FETCH_CANDIDATE records are considered "
            "before the metric prior. Reserve allocation then uses publisher-displayed "
            "JIF, CiteScore fallback, registry-category midrank percentiles, journal "
            "processing-mode damping, near-duplicate suppression, and a 300-record "
            "global monthly soft ceiling. Missing metrics receive a neutral prior."
        ),
        "counts": {
            "canonical_article_count": len(decisions),
            "eligible_article_count": eligible_count,
            "fetchable_eligible_count": fetchable_count,
            "missing_identifier_eligible_count": eligible_count - fetchable_count,
            "fetch_now_target": p["fetch_now_target"],
            "fetch_now_count": counts["FETCH_NOW"],
            "hold_reserve_policy": "ALL_REMAINING_ELIGIBLE",
            "hold_reserve_count": counts["HOLD_RESERVE"],
            "catalog_only_count": counts["CATALOG_ONLY"],
            "integrity_attention_count": len(integrity),
            "root_item_count": len(root_items),
        },
        "metric_coverage": {
            "journal_count": len(contexts),
            "known_metric_journal_count": known_metric_journals,
            "unknown_metric_journal_count": len(contexts) - known_metric_journals,
            "eligible_record_count": eligible_count,
            "known_metric_eligible_record_count": known_metric_eligible,
            "unknown_metric_eligible_record_count": eligible_count
            - known_metric_eligible,
            "unknown_metric_percentile": p["neutral_percentile"],
        },
        "fetch_now_metric_kind_counts": dict(sorted(metric_kind_counts.items())),
        "fetch_now_capture_band_counts": dict(sorted(band_counts.items())),
        "fetch_now_path_counts": dict(sorted(path_counts.items())),
        "fetch_now_category_counts": dict(sorted(category_counts.items())),
        "fetch_now_journal_counts": dict(sorted(journal_counts.items())),
        "journal_summaries": journal_summaries,
        "items": root_items,
        "abstract_fetch_plan": plan,
    }

    edition_artifacts: dict[str, dict[str, Any]] = {}
    for edition_url, values in by_edition.items():
        route_counts = Counter(item["editorial_route"] for item in values)
        edition_artifacts[edition_url] = {
            "schema_version": "2.0",
            "artifact_type": "EvidenceRadar_Editions_EditorialShortlistAudit",
            "generated_at": generated,
            "policy_id": p["policy_id"],
            "policy_sha256": policy_digest,
            "impact_registry_sha256": impact_digest,
            "source_prefetch_digest": source_digest,
            "shortlist_binding_sha256": binding,
            "journal": values[0].get("journal") if values else None,
            "journal_slug": values[0].get("journal_slug") if values else None,
            "period_key": values[0].get("period_key") if values else None,
            "revision": values[0].get("revision") if values else None,
            "journal_impact_prior": values[0].get("journal_impact_prior")
            if values
            else None,
            "semantics": p["semantics"],
            "counts": {
                "canonical_article_count": len(values),
                "fetch_now_count": route_counts["FETCH_NOW"],
                "hold_reserve_count": route_counts["HOLD_RESERVE"],
                "catalog_only_count": route_counts["CATALOG_ONLY"],
                "integrity_attention_count": sum(
                    item["integrity_attention"] for item in values
                ),
            },
            "articles": sorted(
                values,
                key=lambda item: (
                    _ROUTES.index(item["editorial_route"]),
                    item["selection_ordinal"] or 999999,
                    -item["prefetch_score"],
                    str(item.get("title_original") or "").casefold(),
                    item["record_key"],
                ),
            ),
        }
    return root, edition_artifacts

__all__ = [
    "ABSTRACT_FETCH_PLAN_FILENAME", "SHORTLIST_INDEX_FILENAME",
    "SHORTLIST_PAGE_FILENAME", "SHORTLIST_POLICY_FILENAME",
    "EditorialShortlistPolicyV2Error", "build_editorial_shortlist_v2",
    "builtin_editorial_shortlist_policy_v2",
    "load_editorial_shortlist_policy_v2",
    "validate_editorial_shortlist_policy_v2",
]
