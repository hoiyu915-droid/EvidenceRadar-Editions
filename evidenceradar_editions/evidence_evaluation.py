from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

from defusedxml import ElementTree as ET

from .utils import clean_text, utc_now_iso

POLICY_FILENAME = "evidence-evaluation-policy.json"
EVALUATION_FILENAME = "evidence-evaluation.json"
EVALUATION_PAGE_FILENAME = "evidence-evaluation.html"
EDITORIAL_FILENAME = "evaluated-edition.json"
EDITORIAL_PAGE_FILENAME = "evaluated-edition.html"

MODES = ("FULL", "TRIAGE", "INDEX_ONLY", "SUSPENDED")
TEXT_FORMATS = {"JATS_XML", "PUBLISHER_XML", "text/plain"}

CHECKLISTS = {
    "RANDOMIZED_TRIAL": [
        "METHODS_SECTION", "RESULTS_SECTION", "RANDOMIZATION", "SAMPLE_SIZE",
        "PRIMARY_OUTCOME", "EFFECT_ESTIMATE", "REGISTRATION", "ALLOCATION_CONCEALMENT",
        "MASKING", "INTENTION_TO_TREAT", "ATTRITION_OR_MISSING", "LIMITATIONS",
    ],
    "EVIDENCE_SYNTHESIS": [
        "METHODS_SECTION", "RESULTS_SECTION", "SEARCH_STRATEGY", "RISK_OF_BIAS_METHOD",
        "EFFECT_ESTIMATE", "HETEROGENEITY", "REGISTRATION", "LIMITATIONS",
    ],
    "PROSPECTIVE_LONGITUDINAL": [
        "METHODS_SECTION", "RESULTS_SECTION", "SAMPLE_SIZE", "FOLLOW_UP",
        "EFFECT_ESTIMATE", "CONFOUNDING_ADJUSTMENT", "ATTRITION_OR_MISSING", "LIMITATIONS",
    ],
    "OBSERVATIONAL_DESIGN": [
        "METHODS_SECTION", "RESULTS_SECTION", "SAMPLE_SIZE", "EFFECT_ESTIMATE",
        "CONFOUNDING_ADJUSTMENT", "ATTRITION_OR_MISSING", "LIMITATIONS",
    ],
    "REPLICATION_VALIDATION": [
        "METHODS_SECTION", "RESULTS_SECTION", "SAMPLE_SIZE", "EFFECT_ESTIMATE",
        "EXTERNAL_VALIDATION", "LIMITATIONS",
    ],
    "RESOURCE_BENCHMARK": [
        "METHODS_SECTION", "RESULTS_SECTION", "DATA_OR_CODE_AVAILABILITY",
        "EXTERNAL_VALIDATION", "LIMITATIONS",
    ],
    "SAFETY_SIGNAL": [
        "METHODS_SECTION", "RESULTS_SECTION", "SAMPLE_SIZE", "EFFECT_ESTIMATE", "LIMITATIONS",
    ],
    "GUIDANCE": [
        "METHODS_SECTION", "RECOMMENDATION_LANGUAGE", "CONFLICT_OF_INTEREST", "FUNDING",
    ],
    "SURVEY": ["METHODS_SECTION", "RESULTS_SECTION", "SAMPLE_SIZE", "LIMITATIONS"],
    "PROTOCOL": ["METHODS_SECTION", "REGISTRATION", "PRIMARY_OUTCOME"],
    "CASE_REPORT": ["RESULTS_SECTION", "LIMITATIONS"],
    "DEFAULT": ["METHODS_SECTION", "RESULTS_SECTION", "SAMPLE_SIZE", "EFFECT_ESTIMATE", "LIMITATIONS"],
}

CRITICAL = {
    "RANDOMIZED_TRIAL": {"METHODS_SECTION", "RESULTS_SECTION", "RANDOMIZATION", "SAMPLE_SIZE", "PRIMARY_OUTCOME", "EFFECT_ESTIMATE"},
    "EVIDENCE_SYNTHESIS": {"METHODS_SECTION", "RESULTS_SECTION", "SEARCH_STRATEGY", "RISK_OF_BIAS_METHOD"},
    "PROSPECTIVE_LONGITUDINAL": {"METHODS_SECTION", "RESULTS_SECTION", "SAMPLE_SIZE", "FOLLOW_UP"},
    "OBSERVATIONAL_DESIGN": {"METHODS_SECTION", "RESULTS_SECTION", "SAMPLE_SIZE", "CONFOUNDING_ADJUSTMENT"},
    "REPLICATION_VALIDATION": {"METHODS_SECTION", "RESULTS_SECTION", "EXTERNAL_VALIDATION"},
    "RESOURCE_BENCHMARK": {"METHODS_SECTION", "RESULTS_SECTION", "DATA_OR_CODE_AVAILABILITY"},
    "SAFETY_SIGNAL": {"METHODS_SECTION", "RESULTS_SECTION", "SAMPLE_SIZE"},
    "GUIDANCE": {"METHODS_SECTION", "RECOMMENDATION_LANGUAGE", "CONFLICT_OF_INTEREST"},
    "SURVEY": {"METHODS_SECTION", "RESULTS_SECTION", "SAMPLE_SIZE"},
    "PROTOCOL": {"METHODS_SECTION", "REGISTRATION"},
    "CASE_REPORT": {"RESULTS_SECTION"},
    "DEFAULT": {"METHODS_SECTION", "RESULTS_SECTION"},
}

PATTERNS = {
    "RANDOMIZATION": re.compile(r"(?i)\brandomi[sz](?:ed|ation|ing)\b|random allocation|random sequence"),
    "SAMPLE_SIZE": re.compile(r"(?i)(?:\bn\s*=\s*\d{2,}\b|\b\d{2,}\s+(?:participants?|patients?|subjects?|samples?|cases?|controls?)\b|(?:included|enrolled|analysed|analyzed|randomi[sz]ed)\s+\d{2,})"),
    "PRIMARY_OUTCOME": re.compile(r"(?i)\bprimary (?:outcome|endpoint)\b|prespecified (?:outcome|endpoint)"),
    "EFFECT_ESTIMATE": re.compile(r"(?i)(?:95\s*%\s*CI|confidence interval|hazard ratio|odds ratio|risk ratio|relative risk|mean difference|standardized mean difference|\bSMD\b|\bHR\s*[=:]|\bOR\s*[=:]|\bRR\s*[=:])"),
    "REGISTRATION": re.compile(r"(?i)(?:clinicaltrials\.gov|trial registration|registered at|prospero|preregister|pre-registr|registration number)"),
    "ALLOCATION_CONCEALMENT": re.compile(r"(?i)(?:allocation conceal|concealed allocation|sealed opaque|central randomi[sz]ation)"),
    "MASKING": re.compile(r"(?i)\b(?:double|single|triple)[ -]?(?:blind|masked)\b|\bblinded\b|\bmasked\b"),
    "INTENTION_TO_TREAT": re.compile(r"(?i)intention[- ]to[- ]treat|intent[- ]to[- ]treat|modified intention[- ]to[- ]treat|\bITT\b"),
    "ATTRITION_OR_MISSING": re.compile(r"(?i)(?:lost to follow[- ]?up|dropout|withdrawal|missing data|multiple imputation|complete case)"),
    "SEARCH_STRATEGY": re.compile(r"(?i)(?:search strategy|searched (?:medline|pubmed|embase|scopus|web of science|cinahl)|electronic databases|database search)"),
    "RISK_OF_BIAS_METHOD": re.compile(r"(?i)(?:risk of bias|rob 2|robins[- ]?i|newcastle[- ]ottawa|quality assessment)"),
    "HETEROGENEITY": re.compile(r"(?i)(?:heterogeneity|\bI\s*[²2]\s*[=:]|tau[- ]?squared|random[- ]effects model)"),
    "FOLLOW_UP": re.compile(r"(?i)(?:follow[- ]?up|followed for|median follow[- ]?up|years? of follow[- ]?up)"),
    "CONFOUNDING_ADJUSTMENT": re.compile(r"(?i)(?:adjusted for|multivariable|multivariate|propensity score|inverse probability weight|covariate adjustment|confounder)"),
    "EXTERNAL_VALIDATION": re.compile(r"(?i)(?:external validation|independent validation|validation cohort|held[- ]out (?:cohort|dataset|test set)|replication cohort)"),
    "DATA_OR_CODE_AVAILABILITY": re.compile(r"(?i)(?:data availability|code availability|github\.com|code is available|data are available|publicly available dataset|open[- ]source code)"),
    "LIMITATIONS": re.compile(r"(?i)\blimitations?\b|strengths and limitations"),
    "FUNDING": re.compile(r"(?i)\bfunding\b|financial support|grant support"),
    "CONFLICT_OF_INTEREST": re.compile(r"(?i)(?:conflict(?:s)? of interest|competing interests|declaration of interests|financial disclosure)"),
    "RECOMMENDATION_LANGUAGE": re.compile(r"(?i)(?:we recommend|recommendation|should be offered|should receive|guideline recommends?)"),
}


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def builtin_policy() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "artifact_type": "EvidenceRadar_Editions_EvidenceEvaluationPolicy",
        "policy_id": "evidence-evaluation-v1",
        "semantics": (
            "Deterministic full-text evidence-reporting audit after hash-bound acquisition. "
            "It checks whether design-relevant evidence elements are reported; it does not "
            "establish causal validity, clinical importance, novelty, or a formal risk-of-bias grade."
        ),
        "featured_target": 36,
        "journal_featured_caps": {"FULL": 8, "TRIAGE": 12, "INDEX_ONLY": 2, "SUSPENDED": 0},
        "reporting_coverage_weight": 24.0,
        "critical_gap_penalty": 6.0,
        "high_information_bonus": 4.0,
        "moderate_information_bonus": 2.0,
        "checklists": CHECKLISTS,
        "critical_signals": {key: sorted(value) for key, value in CRITICAL.items()},
    }


def validate_policy(raw: Mapping[str, Any]) -> dict[str, Any]:
    policy = dict(raw)
    if policy.get("artifact_type") != "EvidenceRadar_Editions_EvidenceEvaluationPolicy":
        raise ValueError("unexpected evidence evaluation policy")
    policy["featured_target"] = int(policy.get("featured_target") or 0)
    if not 1 <= policy["featured_target"] <= 500:
        raise ValueError("invalid evidence featured target")
    caps = {str(k): int(v) for k, v in dict(policy.get("journal_featured_caps") or {}).items()}
    if set(caps) != set(MODES) or any(value < 0 for value in caps.values()):
        raise ValueError("invalid evidence journal caps")
    policy["journal_featured_caps"] = caps
    for key in ("reporting_coverage_weight", "critical_gap_penalty", "high_information_bonus", "moderate_information_bonus"):
        policy[key] = float(policy.get(key) or 0)
    checklists = {str(k): [str(x) for x in v] for k, v in dict(policy.get("checklists") or {}).items()}
    if "DEFAULT" not in checklists:
        raise ValueError("evidence policy requires DEFAULT checklist")
    policy["checklists"] = checklists
    critical = {str(k): [str(x) for x in v] for k, v in dict(policy.get("critical_signals") or {}).items()}
    if "DEFAULT" not in critical:
        raise ValueError("evidence policy requires DEFAULT critical signals")
    policy["critical_signals"] = critical
    return policy


def load_policy(catalog_root: Path = Path("catalog")) -> dict[str, Any]:
    path = Path(catalog_root) / POLICY_FILENAME
    if not path.is_file():
        return validate_policy(builtin_policy())
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("evidence evaluation policy must be an object")
    return validate_policy(value)


def _local(tag: Any) -> str:
    return str(tag or "").rsplit("}", 1)[-1].casefold()


def _read_payload(receipt: Mapping[str, Any], payload_dir: Path) -> tuple[bytes, str]:
    name = str(receipt.get("payload_object_name") or "").strip()
    if not name or Path(name).name != name or "/" in name or "\\" in name:
        raise ValueError("unsafe full-text payload object name")
    path = Path(payload_dir) / name
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"full-text payload missing: {name}")
    data = path.read_bytes()
    expected = str(receipt.get("fulltext_sha256") or "")
    if len(expected) != 64 or hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("full-text payload hash mismatch")
    if len(data) != int(receipt.get("fulltext_bytes") or -1):
        raise ValueError("full-text payload byte count mismatch")
    return data, name


def _xml_text(data: bytes) -> tuple[str, list[str]]:
    root = ET.fromstring(data)
    section_titles: list[str] = []
    for node in root.iter():
        if _local(node.tag) != "sec":
            continue
        title = next((child for child in list(node) if _local(child.tag) == "title"), None)
        if title is not None:
            value = clean_text(" ".join(title.itertext()))
            if value:
                section_titles.append(value)
    return clean_text(" ".join(root.itertext())), section_titles


def _extract_text(receipt: Mapping[str, Any], data: bytes) -> tuple[str | None, str, list[str]]:
    audit = dict(receipt.get("fulltext_structural_audit") or {})
    fmt = str(audit.get("format") or "")
    content_type = str(receipt.get("content_type") or "").casefold()
    if fmt in {"JATS_XML", "PUBLISHER_XML"} or content_type in {"application/xml", "text/xml"}:
        text, sections = _xml_text(data)
        return text or None, fmt or "XML", sections
    if fmt == "PDF" or content_type == "application/pdf":
        return None, "PDF", []
    if content_type == "text/plain" or fmt == "text/plain":
        text = clean_text(data.decode("utf-8", errors="replace"))
        return text or None, "text/plain", []
    return None, fmt or content_type or "UNKNOWN", []


def _structural_signals(receipt: Mapping[str, Any], text: str | None) -> dict[str, bool]:
    audit = dict(receipt.get("fulltext_structural_audit") or {})
    signals = {
        "METHODS_SECTION": bool(audit.get("has_methods_section")),
        "RESULTS_SECTION": bool(audit.get("has_results_section")),
        "LIMITATIONS": bool(audit.get("has_limitations_section")),
        "DATA_OR_CODE_AVAILABILITY": bool(audit.get("has_data_availability_section")),
        "FUNDING": bool(audit.get("has_funding_section")),
        "CONFLICT_OF_INTEREST": bool(audit.get("has_conflict_of_interest_section")),
    }
    if text:
        for code, pattern in PATTERNS.items():
            signals[code] = bool(signals.get(code) or pattern.search(text))
    else:
        for code in PATTERNS:
            signals.setdefault(code, False)
    return signals


def _path_for(record_key: str, abstract_review: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    for row in abstract_review.get("items") or []:
        if str(row.get("record_key") or "") == record_key:
            return str(row.get("primary_path") or "DEFAULT"), dict(row)
    return "DEFAULT", {}


def _audit_item(
    receipt: Mapping[str, Any],
    *,
    payload_dir: Path,
    abstract_review: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    key = str(receipt.get("record_key") or "")
    primary_path, abstract_row = _path_for(key, abstract_review)
    item = {
        "record_key": key,
        "canonical_id": receipt.get("canonical_id"),
        "journal": receipt.get("journal"),
        "journal_slug": receipt.get("journal_slug"),
        "period_key": receipt.get("period_key"),
        "revision": receipt.get("revision"),
        "title_original": receipt.get("title_original"),
        "identifiers": dict(receipt.get("identifiers") or {}),
        "primary_path": primary_path,
        "abstract_sha256": receipt.get("abstract_sha256"),
        "fulltext_sha256": receipt.get("fulltext_sha256"),
        "fulltext_bytes": int(receipt.get("fulltext_bytes") or 0),
        "fulltext_source": receipt.get("acquired_source"),
        "fulltext_content_type": receipt.get("content_type"),
        "fulltext_structural_audit": dict(receipt.get("fulltext_structural_audit") or {}),
        "abstract_information_class": abstract_row.get("abstract_information_class"),
        "fulltext_priority_score": abstract_row.get("fulltext_priority_score"),
        "processing_mode": abstract_row.get("processing_mode") or "FULL",
        "evaluation_status": None,
        "evidence_evaluated": False,
        "risk_of_bias_evaluated": False,
        "effect_magnitude_evaluated": False,
        "reporting_checklist": [],
        "reported_signals": [],
        "critical_reporting_gaps": [],
        "reporting_coverage_fraction": 0.0,
        "reporting_coverage_class": "NOT_EVALUATED",
    }
    if receipt.get("status") != "FULLTEXT_ACQUIRED":
        item["evaluation_status"] = "NO_FULLTEXT"
        return item
    data, _ = _read_payload(receipt, payload_dir)
    text, fmt, section_titles = _extract_text(receipt, data)
    item["payload_format"] = fmt
    item["section_title_count_observed"] = len(section_titles)
    if not text:
        item["evaluation_status"] = "LIMITED_PDF_OR_UNPARSEABLE_TEXT"
        item["reporting_coverage_class"] = "LIMITED_NO_MACHINE_TEXT"
        return item
    signals = _structural_signals(receipt, text)
    checklist = list(policy["checklists"].get(primary_path) or policy["checklists"]["DEFAULT"])
    critical = set(policy["critical_signals"].get(primary_path) or policy["critical_signals"]["DEFAULT"])
    rows = []
    for code in checklist:
        present = bool(signals.get(code))
        rows.append({"code": code, "status": "PRESENT" if present else "NOT_DETECTED", "critical": code in critical})
    present_count = sum(row["status"] == "PRESENT" for row in rows)
    coverage = present_count / len(rows) if rows else 0.0
    critical_gaps = [row["code"] for row in rows if row["critical"] and row["status"] != "PRESENT"]
    item.update(
        {
            "evaluation_status": "EVALUATED_TEXT_FULLTEXT",
            "evidence_evaluated": True,
            "reporting_checklist": rows,
            "reported_signals": sorted(code for code, present in signals.items() if present),
            "critical_reporting_gaps": critical_gaps,
            "reporting_coverage_fraction": round(coverage, 6),
            "reporting_coverage_class": (
                "HIGH_REPORTING_COVERAGE" if coverage >= 0.75 and not critical_gaps
                else "MODERATE_REPORTING_COVERAGE" if coverage >= 0.5
                else "LOW_REPORTING_COVERAGE"
            ),
            "text_characters_reviewed": len(text),
        }
    )
    return item


def evaluate_fulltext(
    fulltext_receipts: Mapping[str, Any],
    abstract_review: Mapping[str, Any],
    *,
    payload_dir: Path,
    policy: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    p = validate_policy(policy or builtin_policy())
    if fulltext_receipts.get("artifact_type") != "EvidenceRadar_Editions_FulltextAcquisitionReceipts":
        raise ValueError("unexpected full-text receipt artifact")
    items = [
        _audit_item(receipt, payload_dir=payload_dir, abstract_review=abstract_review, policy=p)
        for receipt in fulltext_receipts.get("items") or []
    ]
    acquired = [row for row in items if row.get("fulltext_sha256")]
    evaluated = [row for row in items if row["evidence_evaluated"]]
    limited = [row for row in items if row["evaluation_status"] == "LIMITED_PDF_OR_UNPARSEABLE_TEXT"]
    policy_sha = _digest(p)
    binding = _digest(
        {
            "policy_sha256": policy_sha,
            "fulltext_receipt_binding_sha256": fulltext_receipts.get("receipt_binding_sha256"),
            "items": [
                {
                    "record_key": row["record_key"],
                    "fulltext_sha256": row.get("fulltext_sha256"),
                    "evaluation_status": row["evaluation_status"],
                    "evidence_evaluated": row["evidence_evaluated"],
                    "reporting_checklist": row["reporting_checklist"],
                    "critical_reporting_gaps": row["critical_reporting_gaps"],
                    "reporting_coverage_fraction": row["reporting_coverage_fraction"],
                }
                for row in sorted(items, key=lambda value: value["record_key"])
            ],
        }
    )
    classes = Counter(row["reporting_coverage_class"] for row in items)
    return {
        "schema_version": "1.0",
        "artifact_type": "EvidenceRadar_Editions_EvidenceEvaluation",
        "generated_at": generated_at or utc_now_iso(),
        "policy_id": p["policy_id"],
        "policy_sha256": policy_sha,
        "fulltext_receipt_binding_sha256": fulltext_receipts.get("receipt_binding_sha256"),
        "evidence_evaluation_binding_sha256": binding,
        "scientific_boundary": (
            "evidence_evaluated=true means a deterministic full-text evidence-reporting checklist was executed on hash-verified text. "
            "It does not mean formal risk of bias, causal validity, effect magnitude, clinical importance, or recommendation strength was established."
        ),
        "counts": {
            "fulltext_receipt_count": len(items),
            "fulltext_acquired": len(acquired),
            "no_fulltext": len(items) - len(acquired),
            "evidence_evaluated": len(evaluated),
            "limited_no_machine_text": len(limited),
            "by_reporting_coverage_class": dict(sorted(classes.items())),
        },
        "items": items,
    }


def _score(row: Mapping[str, Any], policy: Mapping[str, Any]) -> tuple[float, dict[str, float]]:
    try:
        base = float(row.get("fulltext_priority_score") or 0)
    except Exception:
        base = 0.0
    coverage = float(row.get("reporting_coverage_fraction") or 0)
    coverage_component = coverage * float(policy["reporting_coverage_weight"])
    gap_component = -len(row.get("critical_reporting_gaps") or []) * float(policy["critical_gap_penalty"])
    info = str(row.get("abstract_information_class") or "")
    info_component = float(policy["high_information_bonus"] if info == "HIGH_INFORMATION" else policy["moderate_information_bonus"] if info == "MODERATE_INFORMATION" else 0)
    total = base + coverage_component + gap_component + info_component
    return total, {"abstract_fulltext_priority": base, "reporting_coverage": round(coverage_component, 6), "critical_gap_penalty": gap_component, "abstract_information_bonus": info_component}


def _round_robin_paths(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row.get("primary_path") or "DEFAULT")].append(row)
    for values in groups.values():
        values.sort(key=lambda row: (-row["editorial_priority_score"], str(row.get("journal") or "").casefold(), str(row.get("title_original") or "").casefold()))
    order = sorted(groups, key=lambda path: (-groups[path][0]["editorial_priority_score"], path))
    result: list[dict[str, Any]] = []
    while any(groups.values()):
        for path in order:
            if groups[path]:
                result.append(groups[path].pop(0))
    return result


def build_evaluated_edition(
    evaluation: Mapping[str, Any],
    *,
    policy: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    p = validate_policy(policy or builtin_policy())
    if evaluation.get("artifact_type") != "EvidenceRadar_Editions_EvidenceEvaluation":
        raise ValueError("unexpected evidence evaluation artifact")
    candidates: list[dict[str, Any]] = []
    limited: list[dict[str, Any]] = []
    for raw in evaluation.get("items") or []:
        row = dict(raw)
        if not row.get("evidence_evaluated"):
            row["editorial_route"] = "LIMITED_REVIEW"
            limited.append(row)
            continue
        score, components = _score(row, p)
        row["editorial_priority_score"] = round(score, 6)
        row["editorial_score_components"] = components
        candidates.append(row)
    ordered = _round_robin_paths(candidates)
    selected: list[dict[str, Any]] = []
    reserve: list[dict[str, Any]] = []
    journal_counts: Counter[str] = Counter()
    for row in ordered:
        mode = str(row.get("processing_mode") or "FULL")
        cap = int(p["journal_featured_caps"].get(mode, 0))
        slug = str(row.get("journal_slug") or "")
        if len(selected) >= p["featured_target"]:
            row["editorial_route"] = "EVIDENCE_RESERVE"
            row["decision_reasons"] = ["GLOBAL_FEATURED_TARGET"]
            reserve.append(row)
        elif journal_counts[slug] >= cap:
            row["editorial_route"] = "EVIDENCE_RESERVE"
            row["decision_reasons"] = ["JOURNAL_FEATURED_CAP"]
            reserve.append(row)
        else:
            row["editorial_route"] = "FEATURED"
            row["selection_ordinal"] = len(selected) + 1
            row["decision_reasons"] = [
                "FULLTEXT_EVIDENCE_AUDIT",
                f"REPORTING_CLASS:{row['reporting_coverage_class']}",
                f"PRIMARY_PATH:{row.get('primary_path') or 'DEFAULT'}",
            ]
            selected.append(row)
            journal_counts[slug] += 1
    for row in limited:
        row["decision_reasons"] = ["MACHINE_TEXT_UNAVAILABLE"]
    items = [*selected, *reserve, *limited]
    binding = _digest(
        {
            "policy_sha256": _digest(p),
            "evidence_evaluation_binding_sha256": evaluation.get("evidence_evaluation_binding_sha256"),
            "items": [
                {
                    "record_key": row["record_key"],
                    "editorial_route": row["editorial_route"],
                    "selection_ordinal": row.get("selection_ordinal"),
                    "editorial_priority_score": row.get("editorial_priority_score"),
                    "decision_reasons": row.get("decision_reasons"),
                }
                for row in sorted(items, key=lambda value: value["record_key"])
            ],
        }
    )
    path_counts = Counter(str(row.get("primary_path") or "DEFAULT") for row in selected)
    return {
        "schema_version": "1.0",
        "artifact_type": "EvidenceRadar_Editions_EvaluatedEdition",
        "generated_at": generated_at or utc_now_iso(),
        "policy_id": p["policy_id"],
        "policy_sha256": _digest(p),
        "evidence_evaluation_binding_sha256": evaluation.get("evidence_evaluation_binding_sha256"),
        "evaluated_edition_binding_sha256": binding,
        "semantics": (
            "Public deterministic editorial projection after full-text evidence-reporting audit. FEATURED is an attention route, not endorsement or a claim that the evidence is valid or clinically important."
        ),
        "counts": {
            "featured": len(selected),
            "evidence_reserve": len(reserve),
            "limited_review": len(limited),
            "evidence_evaluated": len(candidates),
            "by_featured_primary_path": dict(sorted(path_counts.items())),
        },
        "items": items,
    }


__all__ = [
    "EDITORIAL_FILENAME", "EDITORIAL_PAGE_FILENAME", "EVALUATION_FILENAME", "EVALUATION_PAGE_FILENAME",
    "POLICY_FILENAME", "build_evaluated_edition", "builtin_policy", "evaluate_fulltext", "load_policy", "validate_policy",
]
