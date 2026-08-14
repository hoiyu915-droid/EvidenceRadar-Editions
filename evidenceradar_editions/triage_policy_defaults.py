from __future__ import annotations

from pathlib import Path
from typing import Any

from .triage_policy import (
    TRIAGE_POLICY_FILENAME,
    load_triage_policy as _load_file_policy,
    validate_triage_policy,
)


DEFAULT_TRIAGE_POLICY: dict[str, Any] = {
    "schema_version": "1.0",
    "artifact_type": "EvidenceRadar_Editions_PrefetchTriagePolicy",
    "semantics": (
        "Deterministic title-and-metadata triage for deciding what deserves a "
        "later fetch attempt. It is not evidence quality scoring, novelty "
        "assessment, abstract review, or full-text verification."
    ),
    "thresholds": {
        "fetch_candidate": 80,
        "reserve": 65,
        "exceptional_bypass": 92,
    },
    "journal_soft_caps": {
        "FULL": 30,
        "TRIAGE": 20,
        "INDEX_ONLY": 10,
        "SUSPENDED": 0,
    },
    "reserve_index_soft_caps": {
        "FULL": 50,
        "TRIAGE": 50,
        "INDEX_ONLY": 25,
        "SUSPENDED": 0,
    },
    "signal_saturation": {
        "minimum_matches": 20,
        "prevalence_threshold": 0.35,
        "penalty": 12,
        "paths": [
            "RESOURCE_BENCHMARK",
            "PROSPECTIVE_LONGITUDINAL",
            "OBSERVATIONAL_DESIGN",
            "SURVEY",
        ],
    },
    "identifier_bonus": {
        "pmcid": 6,
        "pmid": 2,
        "doi": 1,
    },
    "title_specificity_bonus": {
        "minimum_tokens": 12,
        "bonus": 1,
        "second_minimum_tokens": 20,
        "second_bonus": 1,
    },
    "paths": {
        "INTEGRITY_EVENT": {
            "score": 100,
            "route": "INTEGRITY_REVIEW",
            "description": (
                "Retraction, withdrawal, or expression-of-concern notice "
                "requiring record maintenance."
            ),
        },
        "CORRECTION_EVENT": {
            "score": 90,
            "route": "INTEGRITY_REVIEW",
            "description": (
                "Correction, corrigendum, or erratum requiring record maintenance."
            ),
        },
        "GUIDANCE": {
            "score": 92,
            "route": "SCORE",
            "description": (
                "Guideline, position statement, or explicit expert-consensus guidance."
            ),
        },
        "EVIDENCE_SYNTHESIS": {
            "score": 88,
            "route": "SCORE",
            "description": (
                "Systematic, meta-analytic, umbrella, scoping, or network "
                "synthesis signalled by the title."
            ),
        },
        "RANDOMIZED_TRIAL": {
            "score": 86,
            "route": "SCORE",
            "description": (
                "Randomized or cluster-randomized trial signalled by the title."
            ),
        },
        "REPLICATION_VALIDATION": {
            "score": 84,
            "route": "SCORE",
            "description": (
                "Replication, reproducibility, or explicit external/independent "
                "validation."
            ),
        },
        "SAFETY_SIGNAL": {
            "score": 82,
            "route": "SCORE",
            "description": (
                "Safety, adverse-event, toxicity, self-harm, or mortality signal."
            ),
        },
        "RESOURCE_BENCHMARK": {
            "score": 80,
            "route": "SCORE",
            "description": (
                "Dataset, corpus, benchmark, or explicit data resource."
            ),
        },
        "PROSPECTIVE_LONGITUDINAL": {
            "score": 74,
            "route": "SCORE",
            "description": (
                "Prospective, cohort, or longitudinal design signal."
            ),
        },
        "OBSERVATIONAL_DESIGN": {
            "score": 66,
            "route": "SCORE",
            "description": (
                "Retrospective, case-control, or cross-sectional design signal."
            ),
        },
        "SURVEY": {
            "score": 58,
            "route": "SCORE",
            "description": "Survey signal without a stronger path.",
        },
        "PROTOCOL": {
            "score": 38,
            "route": "SCORE",
            "description": "Explicit study or trial protocol.",
        },
        "CASE_REPORT": {
            "score": 42,
            "route": "SCORE",
            "description": "Case report or case series.",
        },
        "EDITORIAL": {
            "score": 25,
            "route": "CATALOG_ONLY",
            "description": "Editorial or preface.",
        },
        "PRIMARY_METADATA": {
            "score": 50,
            "route": "SCORE",
            "description": (
                "Primary bibliographic record with no recognised structural signal."
            ),
        },
    },
}


def load_triage_policy(
    catalog_root: Path | str = Path("catalog"),
) -> dict[str, Any]:
    """Load a catalog override or the versioned built-in policy.

    Lightweight callers may construct a self-contained temporary journal
    catalog without copying every optional executable policy file. Falling back
    here keeps those catalogs functional while applying the same validated
    policy as the repository default; it never disables triage.
    """

    path = Path(catalog_root) / TRIAGE_POLICY_FILENAME
    if path.is_file():
        return _load_file_policy(catalog_root)
    return validate_triage_policy(DEFAULT_TRIAGE_POLICY)


__all__ = ["DEFAULT_TRIAGE_POLICY", "load_triage_policy"]
