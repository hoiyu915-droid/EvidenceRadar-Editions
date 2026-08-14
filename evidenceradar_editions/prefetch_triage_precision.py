from __future__ import annotations

import re
from typing import Any, Mapping

from . import prefetch_triage as base
from .pages_curation import classify_publication_role

_CORRESPONDENCE_RE = re.compile(
    r"^\s*(?:"
    r"re\s*:|"
    r"comment(?:ary)?\s+(?:on|regarding)\b|"
    r"reply\b|"
    r"response\s+to\b|"
    r"author\s+response\b|"
    r"letter\s+to\b|"
    r"concerns?\s+about\b"
    r")",
    re.IGNORECASE,
)
_GUIDANCE_RE = re.compile(
    r"^\s*(?:clinical\s+practice\s+|practice\s+|reporting\s+|"
    r"management\s+|treatment\s+|diagnostic\s+)?guidelines?\b|"
    r":\s*(?:an?\s+)?(?:[A-Za-z0-9-]+\s+){0,4}guidelines?\b|"
    r"\b(?:position|consensus)\s+statement\b|"
    r"\bexpert\s+consensus\s+(?:recommendations?|guidelines?|report|statement)\b",
    re.IGNORECASE,
)
_EVIDENCE_SYNTHESIS_RE = re.compile(
    r"\bsystematic review\b|"
    r"\bmeta[- ]analysis\b|"
    r"\bumbrella review\b|"
    r"\bscoping review\b|"
    r"\bnetwork meta[- ]analysis\b",
    re.IGNORECASE,
)
_RANDOMIZED_TRIAL_RE = re.compile(
    r"(?<!non-)(?<!non )\brandomi[sz]ed(?: controlled| clinical)? trial\b|"
    r"(?<!non-)(?<!non )\bcluster[- ]randomi[sz]ed\b|"
    r"\brandomly assigned\b",
    re.IGNORECASE,
)
_REPLICATION_VALIDATION_RE = re.compile(
    r"\breplication (?:study|attempt|analysis|experiment|report)\b|"
    r"\breproducibility(?: study| analysis| assessment| evaluation)?\b|"
    r"\bexternal validation\b|"
    r"\bindependent validation\b|"
    r"\bmulticent(?:re|er) validation\b|"
    r"\bvalidation study\b",
    re.IGNORECASE,
)
_SAFETY_RE = re.compile(
    r"\b(?:drug|treatment|clinical|patient|model|system|vaccine|device|"
    r"surgical|medication) safety\b|"
    r"\badverse (?:event|effect|outcome|reaction)s?\b|"
    r"\btoxicit(?:y|ies)\b|"
    r"\bself-harm\b|"
    r"\bmortality\b",
    re.IGNORECASE,
)
_RESOURCE_RE = re.compile(
    r"\bbenchmark(?:ing)?\b|"
    r"\b(?:new|novel|open|public|large-scale|multimodal|curated|reference|"
    r"synthetic|clinical)\s+(?:benchmark\s+)?dataset\b|"
    r"\bdataset\s+(?:for|of|to|with|containing)\b|"
    r"\bcorpus\b|"
    r"\bopen database\b|"
    r"\breference database\b|"
    r"\bdata resource\b",
    re.IGNORECASE,
)
_PROSPECTIVE_RE = re.compile(
    r"\bprospective\b|"
    r"\blongitudinal\s+(?:study|analysis|cohort|data|follow-up|survey)\b",
    re.IGNORECASE,
)
_OBSERVATIONAL_RE = re.compile(
    r"\bretrospective\b|"
    r"\bcase-control\b|"
    r"\bcross[- ]sectional\b|"
    r"\b(?:population-based\s+|register-based\s+|nationwide\s+)?"
    r"cohort\s+(?:study|analysis|follow-up)\b",
    re.IGNORECASE,
)
_SURVEY_RE = re.compile(r"\bsurvey\b", re.IGNORECASE)
_PROTOCOL_RE = re.compile(
    r"\b(?:study |trial )?protocol(?:\s+for|\s*:|\s*$)|^\s*protocol\b",
    re.IGNORECASE,
)
_CASE_RE = re.compile(r"\bcase report\b|\bcase series\b", re.IGNORECASE)

_SIGNAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("GUIDANCE", _GUIDANCE_RE),
    ("EVIDENCE_SYNTHESIS", _EVIDENCE_SYNTHESIS_RE),
    ("RANDOMIZED_TRIAL", _RANDOMIZED_TRIAL_RE),
    ("REPLICATION_VALIDATION", _REPLICATION_VALIDATION_RE),
    ("SAFETY_SIGNAL", _SAFETY_RE),
    ("RESOURCE_BENCHMARK", _RESOURCE_RE),
    ("PROSPECTIVE_LONGITUDINAL", _PROSPECTIVE_RE),
    ("OBSERVATIONAL_DESIGN", _OBSERVATIONAL_RE),
)


def extract_paths(
    article: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> tuple[str, list[str], str]:
    """Extract high-precision structural paths from title metadata.

    Prefix-level correspondence is classified before embedded study-language,
    preventing a reply about a systematic review or mortality study from
    entering the fetch queue. Study terms require structural contexts rather
    than bare lexical overlap (for example, DNA replication is not a
    reproducibility study and ``guidelines-aligned`` is not a guideline).
    """

    title = base._title(article)
    role = classify_publication_role(title)
    if role == "concern":
        return role, ["INTEGRITY_EVENT"], "INTEGRITY_EVENT"
    if role == "correction":
        return role, ["CORRECTION_EVENT"], "CORRECTION_EVENT"
    if role == "editorial":
        return role, ["EDITORIAL"], "EDITORIAL"
    if _CORRESPONDENCE_RE.search(title):
        return "correspondence", ["EDITORIAL"], "EDITORIAL"

    paths = [name for name, pattern in _SIGNAL_PATTERNS if pattern.search(title)]
    if _SURVEY_RE.search(title):
        paths.append("SURVEY")
    if _PROTOCOL_RE.search(title):
        paths.append("PROTOCOL")
    if _CASE_RE.search(title):
        paths.append("CASE_REPORT")
    if not paths:
        paths = ["PRIMARY_METADATA"]
    unique_paths = sorted(set(paths))
    primary = max(
        unique_paths,
        key=lambda name: (base._path_score(policy, name), name),
    )
    return role, unique_paths, primary


# The v1 builder resolves this name at run time. Patch it once when the precision
# layer is imported so v2/v3 wrappers and Pages all use the same classifier.
base.extract_paths = extract_paths

__all__ = ["extract_paths"]
