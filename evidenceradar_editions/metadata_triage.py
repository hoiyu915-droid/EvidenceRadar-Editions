from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping

POLICY_FILENAME = "metadata-triage-policy.json"
ALLOWED_TIERS = ("ALERT", "HIGH", "MEDIUM", "LOW")
ALLOWED_RECOMMENDATIONS = (
    "VERIFY_IMMEDIATELY",
    "FETCH_PRIORITY",
    "FETCH_IF_CAPACITY",
    "METADATA_ONLY",
)

_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_SPACE_RE = re.compile(r"[^a-z0-9]+", re.IGNORECASE)
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "in", "is", "it", "of", "on", "or", "the", "to", "using", "via",
    "with", "without", "study", "analysis", "research", "effects", "effect",
}


class MetadataTriagePolicyError(ValueError):
    pass


@dataclass(frozen=True)
class MetadataTriageDecision:
    policy_id: str
    tier: str
    attention_class: str
    fetch_recommendation: str
    label_zh_tw: str
    reason_codes: tuple[str, ...]
    signal_order: int
    identifier_count: int
    source_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "basis": "TITLE_AND_BIBLIOGRAPHIC_METADATA",
            "tier": self.tier,
            "attention_class": self.attention_class,
            "fetch_recommendation": self.fetch_recommendation,
            "label_zh_tw": self.label_zh_tw,
            "reason_codes": list(self.reason_codes),
            "signal_order": self.signal_order,
            "identifier_count": self.identifier_count,
            "source_count": self.source_count,
            "requires_abstract_or_full_text_for_scientific_judgment": True,
            "semantics": (
                "Operational metadata priority only; not evidence-quality grading, "
                "claim verification, novelty judgment, or clinical recommendation."
            ),
        }


def _normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return " ".join(_SPACE_RE.sub(" ", text).split())


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized = _normalize(phrase)
    return bool(normalized and f" {normalized} " in f" {text} ")


def _starts_with(text: str, prefix: str) -> bool:
    normalized = _normalize(prefix)
    return bool(normalized and (text == normalized or text.startswith(normalized + " ")))


def _object(value: Any, *, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MetadataTriagePolicyError(f"{name} must be a JSON object")
    return dict(value)


def _string_list(value: Any, *, name: str, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise MetadataTriagePolicyError(f"{name} must be an array of strings")
    items = [item.strip() for item in value if item.strip()]
    if not allow_empty and not items:
        raise MetadataTriagePolicyError(f"{name} must not be empty")
    return items


def validate_metadata_triage_policy(value: Mapping[str, Any]) -> dict[str, Any]:
    policy = dict(value)
    if policy.get("artifact_type") != "EvidenceRadar_Editions_MetadataTriagePolicy":
        raise MetadataTriagePolicyError("unexpected metadata triage artifact_type")
    policy_id = str(policy.get("policy_id") or "").strip()
    if not policy_id:
        raise MetadataTriagePolicyError("metadata triage policy_id is required")

    tier_order = [
        item.upper()
        for item in _string_list(
            policy.get("tier_order"), name="tier_order", allow_empty=False
        )
    ]
    if tier_order != list(ALLOWED_TIERS):
        raise MetadataTriagePolicyError(
            f"tier_order must be exactly {list(ALLOWED_TIERS)}"
        )

    default = _object(policy.get("default"), name="default")
    if str(default.get("tier") or "").upper() not in ALLOWED_TIERS:
        raise MetadataTriagePolicyError("default tier is invalid")
    if (
        str(default.get("fetch_recommendation") or "").upper()
        not in ALLOWED_RECOMMENDATIONS
    ):
        raise MetadataTriagePolicyError("default fetch_recommendation is invalid")
    for key in ("attention_class", "reason_code", "label_zh_tw"):
        if not str(default.get(key) or "").strip():
            raise MetadataTriagePolicyError(f"default.{key} is required")

    selection = _object(policy.get("selection"), name="selection")
    try:
        threshold = float(selection.get("near_duplicate_jaccard_threshold"))
    except (TypeError, ValueError) as exc:
        raise MetadataTriagePolicyError(
            "selection.near_duplicate_jaccard_threshold must be numeric"
        ) from exc
    if not 0.5 <= threshold <= 1.0:
        raise MetadataTriagePolicyError(
            "selection.near_duplicate_jaccard_threshold must be between 0.5 and 1.0"
        )
    bucket_order = _string_list(
        selection.get("bucket_order"),
        name="selection.bucket_order",
        allow_empty=False,
    )
    if len(bucket_order) != len(set(bucket_order)):
        raise MetadataTriagePolicyError("selection.bucket_order contains duplicates")

    raw_signals = policy.get("signals")
    if not isinstance(raw_signals, list) or not raw_signals:
        raise MetadataTriagePolicyError("signals must be a non-empty array")
    signals: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for index, raw in enumerate(raw_signals):
        signal = _object(raw, name=f"signals[{index}]")
        code = str(signal.get("code") or "").strip().upper()
        if not code or code in seen_codes:
            raise MetadataTriagePolicyError(
                f"invalid or duplicate signal code: {code!r}"
            )
        seen_codes.add(code)
        tier = str(signal.get("tier") or "").strip().upper()
        recommendation = (
            str(signal.get("fetch_recommendation") or "").strip().upper()
        )
        attention = str(signal.get("attention_class") or "").strip().upper()
        label = str(signal.get("label_zh_tw") or "").strip()
        if tier not in ALLOWED_TIERS:
            raise MetadataTriagePolicyError(f"invalid signal tier: {code}")
        if recommendation not in ALLOWED_RECOMMENDATIONS:
            raise MetadataTriagePolicyError(
                f"invalid signal fetch recommendation: {code}"
            )
        if not attention or not label:
            raise MetadataTriagePolicyError(
                f"signal lacks attention class or label: {code}"
            )
        prefixes = _string_list(
            signal.get("title_prefixes") or [],
            name=f"signals[{index}].title_prefixes",
        )
        phrases = _string_list(
            signal.get("title_phrases") or [],
            name=f"signals[{index}].title_phrases",
        )
        types = _string_list(
            signal.get("article_type_phrases") or [],
            name=f"signals[{index}].article_type_phrases",
        )
        if not prefixes and not phrases and not types:
            raise MetadataTriagePolicyError(
                f"signal has no match clauses: {code}"
            )
        signals.append(
            {
                "code": code,
                "tier": tier,
                "attention_class": attention,
                "fetch_recommendation": recommendation,
                "label_zh_tw": label,
                "terminal": bool(signal.get("terminal")),
                "title_prefixes": prefixes,
                "title_phrases": phrases,
                "article_type_phrases": types,
            }
        )

    return {
        "_validated": True,
        "schema_version": str(policy.get("schema_version") or "1.0"),
        "artifact_type": "EvidenceRadar_Editions_MetadataTriagePolicy",
        "policy_id": policy_id,
        "basis": _string_list(policy.get("basis") or [], name="basis"),
        "semantics": str(policy.get("semantics") or "").strip(),
        "tier_order": list(ALLOWED_TIERS),
        "default": {
            "tier": str(default["tier"]).upper(),
            "attention_class": str(default["attention_class"]).upper(),
            "fetch_recommendation": str(
                default["fetch_recommendation"]
            ).upper(),
            "reason_code": str(default["reason_code"]).upper(),
            "label_zh_tw": str(default["label_zh_tw"]),
        },
        "selection": {
            "near_duplicate_jaccard_threshold": threshold,
            "bucket_order": bucket_order,
        },
        "signals": signals,
    }


def load_metadata_triage_policy(
    catalog_root: Path | str = Path("catalog"),
) -> dict[str, Any]:
    path = Path(catalog_root) / POLICY_FILENAME
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise MetadataTriagePolicyError(
            "metadata triage policy must be a JSON object"
        )
    return validate_metadata_triage_policy(value)


def _validated(policy: Mapping[str, Any]) -> Mapping[str, Any]:
    return policy if policy.get("_validated") is True else validate_metadata_triage_policy(policy)


def _article_sources(article: Mapping[str, Any]) -> set[str]:
    values = article.get("sources")
    if isinstance(values, list):
        return {str(item) for item in values if item}
    records = article.get("source_records") or []
    return {
        str(record.get("source"))
        for record in records
        if isinstance(record, dict) and record.get("source")
    }


def triage_article(
    article: Mapping[str, Any],
    *,
    policy: Mapping[str, Any],
) -> MetadataTriageDecision:
    rules = _validated(policy)
    title = _normalize(
        article.get("title_original") or article.get("title") or ""
    )
    article_type = _normalize(article.get("article_type") or "")
    matched: list[tuple[int, Mapping[str, Any]]] = []
    for index, signal in enumerate(rules["signals"]):
        hit = any(
            _starts_with(title, value) for value in signal["title_prefixes"]
        )
        hit = hit or any(
            _contains_phrase(title, value) for value in signal["title_phrases"]
        )
        hit = hit or any(
            _contains_phrase(article_type, value)
            for value in signal["article_type_phrases"]
        )
        if hit:
            matched.append((index, signal))
            if signal["terminal"]:
                break

    default = rules["default"]
    if matched:
        tier_rank = {
            tier: index for index, tier in enumerate(ALLOWED_TIERS)
        }
        primary_index, primary = min(
            matched,
            key=lambda item: (tier_rank[item[1]["tier"]], item[0]),
        )
        reason_codes = tuple(signal["code"] for _, signal in matched)
    else:
        primary_index = len(rules["signals"])
        primary = {
            "tier": default["tier"],
            "attention_class": default["attention_class"],
            "fetch_recommendation": default["fetch_recommendation"],
            "label_zh_tw": default["label_zh_tw"],
        }
        reason_codes = (default["reason_code"],)

    identifiers = sum(
        1
        for key in ("doi", "pmid", "pmcid")
        if str(article.get(key) or "").strip()
    )
    sources = _article_sources(article)
    extra_reasons: list[str] = []
    if article.get("doi"):
        extra_reasons.append("HAS_DOI")
    if article.get("pmid"):
        extra_reasons.append("HAS_PMID")
    if article.get("pmcid"):
        extra_reasons.append("HAS_PMCID")
    if len(sources) > 1:
        extra_reasons.append("MULTI_SOURCE_METADATA")

    return MetadataTriageDecision(
        policy_id=str(rules["policy_id"]),
        tier=str(primary["tier"]),
        attention_class=str(primary["attention_class"]),
        fetch_recommendation=str(primary["fetch_recommendation"]),
        label_zh_tw=str(primary["label_zh_tw"]),
        reason_codes=tuple([*reason_codes, *extra_reasons]),
        signal_order=primary_index,
        identifier_count=identifiers,
        source_count=len(sources),
    )


def enrich_article_with_triage(
    article: Mapping[str, Any],
    *,
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    value = dict(article)
    value["metadata_triage"] = triage_article(
        article, policy=policy
    ).to_dict()
    return value


def _date_sort_value(value: Any) -> tuple[int, int, int]:
    try:
        parsed = date.fromisoformat(str(value or ""))
    except ValueError:
        return (0, 0, 0)
    return (-parsed.year, -parsed.month, -parsed.day)


def _int_or(value: Any, fallback: int) -> int:
    return fallback if value is None else int(value)


def triage_sort_key(article: Mapping[str, Any]) -> tuple[Any, ...]:
    triage = article.get("metadata_triage") or {}
    tier_rank = {tier: index for index, tier in enumerate(ALLOWED_TIERS)}
    title = _normalize(
        article.get("title_original") or article.get("title") or ""
    )
    return (
        tier_rank.get(
            str(triage.get("tier") or "MEDIUM"), len(ALLOWED_TIERS)
        ),
        _int_or(triage.get("signal_order"), 9999),
        -_int_or(triage.get("identifier_count"), 0),
        -_int_or(triage.get("source_count"), 0),
        _date_sort_value(article.get("publication_date")),
        title,
        str(article.get("canonical_id") or ""),
    )


def _title_tokens(article: Mapping[str, Any]) -> frozenset[str]:
    title = _normalize(
        article.get("title_original") or article.get("title") or ""
    )
    return frozenset(
        token
        for token in _TOKEN_RE.findall(title)
        if len(token) > 2 and token not in _STOPWORDS
    )


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _select_one_tier(
    grouped: Mapping[tuple[int, int, str], deque[dict[str, Any]]],
    keys: list[tuple[int, int, str]],
    *,
    limit: int,
    threshold: float,
    selected_tokens: list[frozenset[str]],
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    while len(selected) < limit and any(grouped[key] for key in keys):
        progressed = False
        for key in keys:
            queue = grouped[key]
            if not queue or len(selected) >= limit:
                continue
            attempts = len(queue)
            chosen: dict[str, Any] | None = None
            while attempts and queue:
                candidate = queue.popleft()
                tokens = _title_tokens(candidate)
                near_duplicate = any(
                    _jaccard(tokens, prior) >= threshold
                    for prior in selected_tokens
                    if tokens and prior
                )
                if near_duplicate:
                    deferred.append(candidate)
                    attempts -= 1
                    continue
                chosen = candidate
                break
            if chosen is not None:
                selected.append(chosen)
                selected_tokens.append(_title_tokens(chosen))
                progressed = True
        if not progressed:
            break

    if len(selected) < limit:
        remaining = [*deferred]
        for key in keys:
            remaining.extend(grouped[key])
        remaining.sort(key=triage_sort_key)
        fill = remaining[: limit - len(selected)]
        selected.extend(fill)
        selected_tokens.extend(_title_tokens(item) for item in fill)
    return selected


def select_triaged_projection(
    articles: Iterable[Mapping[str, Any]],
    *,
    limit: int,
    policy: Mapping[str, Any],
) -> list[dict[str, Any]]:
    rules = _validated(policy)
    enriched = [
        dict(article)
        if "metadata_triage" in article
        else enrich_article_with_triage(article, policy=rules)
        for article in articles
    ]
    if limit <= 0:
        return []
    enriched.sort(key=triage_sort_key)
    if len(enriched) <= limit:
        return enriched

    threshold = float(
        rules["selection"]["near_duplicate_jaccard_threshold"]
    )
    bucket_order = list(rules["selection"]["bucket_order"])
    bucket_rank = {value: index for index, value in enumerate(bucket_order)}
    tier_rank = {tier: index for index, tier in enumerate(ALLOWED_TIERS)}
    grouped: defaultdict[
        tuple[int, int, str], deque[dict[str, Any]]
    ] = defaultdict(deque)
    for article in enriched:
        triage = article.get("metadata_triage") or {}
        tier = str(triage.get("tier") or "MEDIUM")
        attention = str(
            triage.get("attention_class") or "PRIMARY_RESEARCH"
        )
        grouped[
            (
                tier_rank.get(tier, len(ALLOWED_TIERS)),
                bucket_rank.get(attention, len(bucket_order)),
                attention,
            )
        ].append(article)

    selected: list[dict[str, Any]] = []
    selected_tokens: list[frozenset[str]] = []
    for tier_index in range(len(ALLOWED_TIERS)):
        if len(selected) >= limit:
            break
        tier_keys = sorted(
            key for key in grouped if key[0] == tier_index
        )
        if not tier_keys:
            continue
        selected.extend(
            _select_one_tier(
                grouped,
                tier_keys,
                limit=limit - len(selected),
                threshold=threshold,
                selected_tokens=selected_tokens,
            )
        )
    return selected[:limit]


def triage_counts(
    articles: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, int]]:
    tiers: defaultdict[str, int] = defaultdict(int)
    classes: defaultdict[str, int] = defaultdict(int)
    recommendations: defaultdict[str, int] = defaultdict(int)
    for article in articles:
        triage = article.get("metadata_triage") or {}
        tiers[str(triage.get("tier") or "UNKNOWN")] += 1
        classes[str(triage.get("attention_class") or "UNKNOWN")] += 1
        recommendations[
            str(triage.get("fetch_recommendation") or "UNKNOWN")
        ] += 1
    return {
        "by_tier": dict(sorted(tiers.items())),
        "by_attention_class": dict(sorted(classes.items())),
        "by_fetch_recommendation": dict(sorted(recommendations.items())),
    }
