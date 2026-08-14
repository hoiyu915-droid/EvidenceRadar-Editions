from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from .journal_impact import IMPACT_REGISTRY_FILENAME

SHORTLIST_POLICY_FILENAME = "editorial-shortlist-policy.json"
SHORTLIST_INDEX_FILENAME = "editorial-shortlist.json"
SHORTLIST_PAGE_FILENAME = "editorial-shortlist.html"
ABSTRACT_FETCH_PLAN_FILENAME = "abstract-fetch-plan.json"

_MODES = ("FULL", "TRIAGE", "INDEX_ONLY", "SUSPENDED")
_ROUTES = ("FETCH_NOW", "HOLD_RESERVE", "CATALOG_ONLY")

class EditorialShortlistPolicyV2Error(ValueError):
    pass

def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def _digest(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()

def builtin_editorial_shortlist_policy_v2() -> dict[str, Any]:
    paths = [
        "GUIDANCE",
        "EVIDENCE_SYNTHESIS",
        "RANDOMIZED_TRIAL",
        "REPLICATION_VALIDATION",
        "SAFETY_SIGNAL",
        "RESOURCE_BENCHMARK",
        "PROSPECTIVE_LONGITUDINAL",
        "OBSERVATIONAL_DESIGN",
        "SURVEY",
        "PROTOCOL",
        "CASE_REPORT",
    ]
    categories = [
        "chemistry",
        "clinical_medicine",
        "human_ai",
        "interdisciplinary",
        "llm_research",
        "physics_astronomy",
        "sport_nutrition_fitness",
        "sport_science",
        "uncategorized",
    ]
    return {
        "schema_version": "2.0",
        "artifact_type": "EvidenceRadar_Editions_EditorialShortlistPolicy",
        "policy_id": "editorial-shortlist-v2-impact-prior",
        "semantics": (
            "Public, deterministic title-and-bibliographic-metadata shortlisting. "
            "Publisher-displayed JIF, with CiteScore fallback, changes only the "
            "share of reserve records allocated abstract-fetch capacity. It is not "
            "article evidence grading, novelty assessment, or scope verification."
        ),
        "fetch_now_target": 300,
        # Retained for backward-compatible validation. V2 holds every remaining
        # eligible record, so the observed hold count may be lower than this ceiling.
        "hold_reserve_target": 300,
        "eligible_prefetch_routes": ["FETCH_CANDIDATE", "RESERVE"],
        "metric_independent_prefetch_routes": ["FETCH_CANDIDATE"],
        "reserve_backfill_enabled": True,
        "hold_all_remaining_eligible": True,
        "impact_registry_file": IMPACT_REGISTRY_FILENAME,
        "neutral_percentile": 50.0,
        "unknown_capture_rate": 0.75,
        "capture_bands": [
            {"minimum_percentile": 90.0, "capture_rate": 1.0, "label": "TOP_DECILE"},
            {"minimum_percentile": 75.0, "capture_rate": 0.9, "label": "TOP_QUARTILE"},
            {"minimum_percentile": 50.0, "capture_rate": 0.8, "label": "UPPER_HALF"},
            {"minimum_percentile": 0.0, "capture_rate": 0.7, "label": "LOWER_HALF"},
        ],
        "mode_capture_modifiers": {
            "FULL": 1.0,
            "TRIAGE": 0.45,
            "INDEX_ONLY": 0.2,
            "SUSPENDED": 0.0,
        },
        "journal_fetch_caps": {
            "FULL": 40,
            "TRIAGE": 60,
            "INDEX_ONLY": 8,
            "SUSPENDED": 0,
        },
        "journal_hold_caps": {
            "FULL": 5000,
            "TRIAGE": 5000,
            "INDEX_ONLY": 5000,
            "SUSPENDED": 5000,
        },
        "topic_soft_caps_by_mode": {
            "FULL": 6,
            "TRIAGE": 12,
            "INDEX_ONLY": 2,
            "SUSPENDED": 0,
        },
        "topic_hard_caps_by_mode": {
            "FULL": 12,
            "TRIAGE": 24,
            "INDEX_ONLY": 4,
            "SUSPENDED": 0,
        },
        "near_duplicate_jaccard_threshold": 0.82,
        "topic_signature_tokens": 4,
        "source_order": {
            "pmcid": [
                "EUROPE_PMC_PMCID",
                "PUBMED_PMID",
                "EUROPE_PMC_PMID",
                "EUROPE_PMC_DOI",
            ],
            "pmid": ["PUBMED_PMID", "EUROPE_PMC_PMID", "EUROPE_PMC_DOI"],
            "doi": ["EUROPE_PMC_DOI"],
        },
        # Legacy V1 fields remain neutral so older tooling can parse this file.
        "category_order": categories,
        "category_minimums": {},
        "category_soft_caps": {name: 300 for name in categories},
        "category_hard_caps": {name: 300 for name in categories},
        "path_order": paths,
        "path_minimums": {name: 0 for name in paths},
        "path_soft_caps": {name: 300 for name in paths},
        "path_hard_caps": {name: 300 for name in paths},
        "topic_soft_cap_per_journal": 12,
        "hold_topic_soft_cap_per_journal": 5000,
        "fetch_now_source_routes": ["FETCH_CANDIDATE"],
    }

def _mode_numbers(value: Any, *, name: str, maximum: float) -> dict[str, float]:
    if not isinstance(value, dict) or set(value) != set(_MODES):
        raise EditorialShortlistPolicyV2Error(f"{name} must contain {_MODES}")
    result: dict[str, float] = {}
    for mode in _MODES:
        number = float(value[mode])
        if not 0 <= number <= maximum:
            raise EditorialShortlistPolicyV2Error(f"invalid {name}.{mode}: {number}")
        result[mode] = number
    return result

def validate_editorial_shortlist_policy_v2(value: Mapping[str, Any]) -> dict[str, Any]:
    p = deepcopy(dict(value))
    if p.get("artifact_type") != "EvidenceRadar_Editions_EditorialShortlistPolicy":
        raise EditorialShortlistPolicyV2Error("unexpected editorial shortlist policy type")
    required = (
        "policy_id",
        "semantics",
        "fetch_now_target",
        "hold_reserve_target",
        "eligible_prefetch_routes",
        "metric_independent_prefetch_routes",
        "impact_registry_file",
        "capture_bands",
        "mode_capture_modifiers",
        "journal_fetch_caps",
        "topic_soft_caps_by_mode",
        "topic_hard_caps_by_mode",
        "near_duplicate_jaccard_threshold",
        "topic_signature_tokens",
        "source_order",
        "category_order",
        "path_order",
    )
    missing = [key for key in required if key not in p]
    if missing:
        raise EditorialShortlistPolicyV2Error(f"missing policy fields: {missing}")
    p["fetch_now_target"] = int(p["fetch_now_target"])
    p["hold_reserve_target"] = int(p["hold_reserve_target"])
    if not 1 <= p["fetch_now_target"] <= 5000:
        raise EditorialShortlistPolicyV2Error("invalid fetch_now_target")
    if p["hold_reserve_target"] < 0:
        raise EditorialShortlistPolicyV2Error("invalid hold_reserve_target")
    p["neutral_percentile"] = float(p.get("neutral_percentile", 50.0))
    p["unknown_capture_rate"] = float(p.get("unknown_capture_rate", 0.75))
    if not 0 <= p["neutral_percentile"] <= 100:
        raise EditorialShortlistPolicyV2Error("invalid neutral_percentile")
    if not 0 <= p["unknown_capture_rate"] <= 1:
        raise EditorialShortlistPolicyV2Error("invalid unknown_capture_rate")

    bands = []
    for raw in p["capture_bands"]:
        if not isinstance(raw, dict):
            raise EditorialShortlistPolicyV2Error("capture_bands entries must be objects")
        minimum = float(raw["minimum_percentile"])
        rate = float(raw["capture_rate"])
        if not 0 <= minimum <= 100 or not 0 <= rate <= 1:
            raise EditorialShortlistPolicyV2Error("invalid capture band")
        bands.append(
            {
                "minimum_percentile": minimum,
                "capture_rate": rate,
                "label": str(raw.get("label") or f"P{minimum:g}"),
            }
        )
    bands.sort(key=lambda item: item["minimum_percentile"], reverse=True)
    if not bands or bands[-1]["minimum_percentile"] != 0:
        raise EditorialShortlistPolicyV2Error("capture_bands must include a zero floor")
    p["capture_bands"] = bands

    p["mode_capture_modifiers"] = _mode_numbers(
        p["mode_capture_modifiers"], name="mode_capture_modifiers", maximum=1.0
    )
    p["journal_fetch_caps"] = {
        key: int(value)
        for key, value in _mode_numbers(
            p["journal_fetch_caps"], name="journal_fetch_caps", maximum=5000
        ).items()
    }
    p["journal_hold_caps"] = {
        key: int(value)
        for key, value in _mode_numbers(
            p.get("journal_hold_caps", {mode: 5000 for mode in _MODES}),
            name="journal_hold_caps",
            maximum=5000,
        ).items()
    }
    p["topic_soft_caps_by_mode"] = {
        key: int(value)
        for key, value in _mode_numbers(
            p["topic_soft_caps_by_mode"],
            name="topic_soft_caps_by_mode",
            maximum=5000,
        ).items()
    }
    p["topic_hard_caps_by_mode"] = {
        key: int(value)
        for key, value in _mode_numbers(
            p["topic_hard_caps_by_mode"],
            name="topic_hard_caps_by_mode",
            maximum=5000,
        ).items()
    }
    for mode in _MODES:
        if p["topic_soft_caps_by_mode"][mode] > p["topic_hard_caps_by_mode"][mode]:
            raise EditorialShortlistPolicyV2Error(
                f"topic soft cap exceeds hard cap for {mode}"
            )

    p["near_duplicate_jaccard_threshold"] = float(
        p["near_duplicate_jaccard_threshold"]
    )
    if not 0 < p["near_duplicate_jaccard_threshold"] <= 1:
        raise EditorialShortlistPolicyV2Error("invalid duplicate threshold")
    p["topic_signature_tokens"] = int(p["topic_signature_tokens"])
    if p["topic_signature_tokens"] < 1:
        raise EditorialShortlistPolicyV2Error("invalid topic_signature_tokens")
    p["eligible_prefetch_routes"] = [str(item) for item in p["eligible_prefetch_routes"]]
    p["metric_independent_prefetch_routes"] = [
        str(item) for item in p["metric_independent_prefetch_routes"]
    ]
    if not set(p["metric_independent_prefetch_routes"]).issubset(
        set(p["eligible_prefetch_routes"])
    ):
        raise EditorialShortlistPolicyV2Error(
            "metric-independent routes must be eligible routes"
        )
    p["hold_all_remaining_eligible"] = bool(
        p.get("hold_all_remaining_eligible", True)
    )
    p["reserve_backfill_enabled"] = bool(p.get("reserve_backfill_enabled", True))
    p["impact_registry_file"] = str(p["impact_registry_file"])
    if p["impact_registry_file"] != IMPACT_REGISTRY_FILENAME:
        raise EditorialShortlistPolicyV2Error(
            f"impact_registry_file must be {IMPACT_REGISTRY_FILENAME}"
        )
    for key in ("category_order", "path_order"):
        if not isinstance(p[key], list) or len(p[key]) != len(set(p[key])):
            raise EditorialShortlistPolicyV2Error(f"invalid {key}")
        p[key] = [str(item) for item in p[key]]
    source_order = p["source_order"]
    if not isinstance(source_order, dict):
        raise EditorialShortlistPolicyV2Error("source_order must be an object")
    for key in ("pmcid", "pmid", "doi"):
        if not isinstance(source_order.get(key), list):
            raise EditorialShortlistPolicyV2Error(f"invalid source_order.{key}")
    return p

def load_editorial_shortlist_policy_v2(
    catalog_root: Path | str = Path("catalog"),
) -> dict[str, Any]:
    path = Path(catalog_root) / SHORTLIST_POLICY_FILENAME
    value = (
        json.loads(path.read_text(encoding="utf-8"))
        if path.is_file()
        else builtin_editorial_shortlist_policy_v2()
    )
    if not isinstance(value, dict):
        raise EditorialShortlistPolicyV2Error("shortlist policy must be an object")
    return validate_editorial_shortlist_policy_v2(value)

__all__ = [
    "ABSTRACT_FETCH_PLAN_FILENAME", "SHORTLIST_INDEX_FILENAME",
    "SHORTLIST_PAGE_FILENAME", "SHORTLIST_POLICY_FILENAME",
    "EditorialShortlistPolicyV2Error", "builtin_editorial_shortlist_policy_v2",
    "load_editorial_shortlist_policy_v2", "validate_editorial_shortlist_policy_v2",
]
