from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

TRIAGE_POLICY_FILENAME = "prefetch-triage-policy.json"
ALLOWED_ROUTES = {"INTEGRITY_REVIEW", "SCORE", "CATALOG_ONLY"}
ALLOWED_PROCESSING_MODES = {"FULL", "TRIAGE", "INDEX_ONLY", "SUSPENDED"}
REQUIRED_PATHS = {
    "INTEGRITY_EVENT",
    "CORRECTION_EVENT",
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
    "EDITORIAL",
    "PRIMARY_METADATA",
}


class TriagePolicyError(ValueError):
    pass


def _object(value: Any, *, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TriagePolicyError(f"{name} must be a JSON object")
    return dict(value)


def _integer(
    value: Any,
    *,
    name: str,
    minimum: int = 0,
    maximum: int = 1_000_000,
) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise TriagePolicyError(f"{name} must be an integer") from exc
    if not (minimum <= parsed <= maximum):
        raise TriagePolicyError(
            f"{name} must be between {minimum} and {maximum}: {parsed}"
        )
    return parsed


def _mode_caps(value: Any, *, name: str) -> dict[str, int]:
    raw = _object(value, name=name)
    missing = sorted(ALLOWED_PROCESSING_MODES - set(raw))
    unknown = sorted(set(raw) - ALLOWED_PROCESSING_MODES)
    if missing or unknown:
        raise TriagePolicyError(
            f"{name} modes mismatch; missing={missing}, unknown={unknown}"
        )
    return {
        mode: _integer(raw[mode], name=f"{name}.{mode}", maximum=5000)
        for mode in sorted(ALLOWED_PROCESSING_MODES)
    }


def validate_triage_policy(value: Mapping[str, Any]) -> dict[str, Any]:
    policy = dict(value)
    if policy.get("artifact_type") != "EvidenceRadar_Editions_PrefetchTriagePolicy":
        raise TriagePolicyError("unexpected prefetch triage policy artifact_type")

    thresholds = _object(policy.get("thresholds"), name="thresholds")
    fetch_candidate = _integer(
        thresholds.get("fetch_candidate"),
        name="thresholds.fetch_candidate",
        maximum=100,
    )
    reserve = _integer(
        thresholds.get("reserve"),
        name="thresholds.reserve",
        maximum=100,
    )
    exceptional = _integer(
        thresholds.get("exceptional_bypass"),
        name="thresholds.exceptional_bypass",
        maximum=100,
    )
    if not reserve < fetch_candidate <= exceptional:
        raise TriagePolicyError(
            "thresholds must satisfy reserve < fetch_candidate <= exceptional_bypass"
        )

    journal_soft_caps = _mode_caps(
        policy.get("journal_soft_caps"), name="journal_soft_caps"
    )
    reserve_index_soft_caps = _mode_caps(
        policy.get("reserve_index_soft_caps"),
        name="reserve_index_soft_caps",
    )

    saturation = _object(policy.get("signal_saturation"), name="signal_saturation")
    saturation_paths = saturation.get("paths")
    if not isinstance(saturation_paths, list) or not all(
        isinstance(item, str) and item for item in saturation_paths
    ):
        raise TriagePolicyError("signal_saturation.paths must be a string list")
    try:
        prevalence = float(saturation.get("prevalence_threshold"))
    except (TypeError, ValueError) as exc:
        raise TriagePolicyError(
            "signal_saturation.prevalence_threshold must be numeric"
        ) from exc
    if not 0 < prevalence <= 1:
        raise TriagePolicyError(
            "signal_saturation.prevalence_threshold must be in (0, 1]"
        )

    identifier_bonus = _object(
        policy.get("identifier_bonus"), name="identifier_bonus"
    )
    title_bonus = _object(
        policy.get("title_specificity_bonus"),
        name="title_specificity_bonus",
    )
    paths = _object(policy.get("paths"), name="paths")
    if set(paths) != REQUIRED_PATHS:
        raise TriagePolicyError(
            f"triage paths mismatch: {sorted(set(paths) ^ REQUIRED_PATHS)}"
        )

    normalized_paths: dict[str, dict[str, Any]] = {}
    for path_name, raw_path in paths.items():
        item = _object(raw_path, name=f"paths.{path_name}")
        route = str(item.get("route") or "")
        if route not in ALLOWED_ROUTES:
            raise TriagePolicyError(
                f"unsupported paths.{path_name}.route: {route}"
            )
        description = str(item.get("description") or "").strip()
        if not description:
            raise TriagePolicyError(
                f"paths.{path_name}.description is empty"
            )
        normalized_paths[path_name] = {
            "score": _integer(
                item.get("score"),
                name=f"paths.{path_name}.score",
                maximum=100,
            ),
            "route": route,
            "description": description,
        }

    unknown_saturation = sorted(set(saturation_paths) - set(normalized_paths))
    if unknown_saturation:
        raise TriagePolicyError(
            f"signal_saturation references unknown paths: {unknown_saturation}"
        )

    second_minimum = _integer(
        title_bonus.get("second_minimum_tokens"),
        name="title_specificity_bonus.second_minimum_tokens",
        minimum=1,
        maximum=1000,
    )
    first_minimum = _integer(
        title_bonus.get("minimum_tokens"),
        name="title_specificity_bonus.minimum_tokens",
        minimum=1,
        maximum=1000,
    )
    if second_minimum < first_minimum:
        raise TriagePolicyError(
            "title_specificity_bonus.second_minimum_tokens must be >= minimum_tokens"
        )

    return {
        "schema_version": str(policy.get("schema_version") or "1.0"),
        "artifact_type": "EvidenceRadar_Editions_PrefetchTriagePolicy",
        "semantics": str(policy.get("semantics") or "").strip(),
        "thresholds": {
            "fetch_candidate": fetch_candidate,
            "reserve": reserve,
            "exceptional_bypass": exceptional,
        },
        "journal_soft_caps": journal_soft_caps,
        "reserve_index_soft_caps": reserve_index_soft_caps,
        "signal_saturation": {
            "minimum_matches": _integer(
                saturation.get("minimum_matches"),
                name="signal_saturation.minimum_matches",
                minimum=1,
                maximum=5000,
            ),
            "prevalence_threshold": prevalence,
            "penalty": _integer(
                saturation.get("penalty"),
                name="signal_saturation.penalty",
                maximum=100,
            ),
            "paths": list(saturation_paths),
        },
        "identifier_bonus": {
            key: _integer(
                identifier_bonus.get(key),
                name=f"identifier_bonus.{key}",
                maximum=100,
            )
            for key in ("pmcid", "pmid", "doi")
        },
        "title_specificity_bonus": {
            "minimum_tokens": first_minimum,
            "bonus": _integer(
                title_bonus.get("bonus"),
                name="title_specificity_bonus.bonus",
                maximum=100,
            ),
            "second_minimum_tokens": second_minimum,
            "second_bonus": _integer(
                title_bonus.get("second_bonus"),
                name="title_specificity_bonus.second_bonus",
                maximum=100,
            ),
        },
        "paths": normalized_paths,
    }


def load_triage_policy(
    catalog_root: Path | str = Path("catalog"),
) -> dict[str, Any]:
    path = Path(catalog_root) / TRIAGE_POLICY_FILENAME
    if not path.is_file():
        raise TriagePolicyError(f"missing triage policy: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TriagePolicyError(
            "prefetch triage policy must be a JSON object"
        )
    return validate_triage_policy(value)
