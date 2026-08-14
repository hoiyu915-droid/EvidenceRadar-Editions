from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter, defaultdict
from copy import deepcopy
from typing import Any, Iterable, Mapping

from .editorial_shortlist_v2_policy import _digest

_WORD = re.compile(r"[A-Za-z0-9]+")
_STOP = set(
    """a an the of in on for to and or with without from by at as is are was were
    be been being study studies analysis analyses evaluation assessment effect
    effects impact association associations using based among between during after
    before through via towards toward new novel randomized randomised controlled
    trial trials systematic review meta umbrella scoping network cohort prospective
    retrospective longitudinal cross sectional case report series survey protocol
    dataset data benchmark resource validation external independent safety mortality
    adverse""".split()
)

def _tokens(title: str) -> list[str]:
    text = unicodedata.normalize("NFKD", str(title or "")).casefold()
    return [token for token in _WORD.findall(text) if token not in _STOP and len(token) > 2]

def _signature(title: str, size: int) -> str:
    found: list[str] = []
    for token in _tokens(title):
        if token not in found:
            found.append(token)
        if len(found) >= size:
            break
    return "|".join(found) or "untitled"

def _jaccard(left: str, right: str) -> float:
    a, b = set(_tokens(left)), set(_tokens(right))
    return len(a & b) / len(a | b) if a and b else 0.0

def _record_key(record: Mapping[str, Any]) -> str:
    canonical_id = str(record.get("canonical_id") or "").strip()
    if not canonical_id:
        canonical_id = "fallback:" + _digest(
            {
                "title": record.get("title_original"),
                "date": record.get("publication_date"),
            }
        )
    return "|".join(
        (
            str(record.get("journal_slug") or ""),
            str(record.get("period_key") or ""),
            str(record.get("revision") or ""),
            canonical_id,
        )
    )

def _date(record: Mapping[str, Any]) -> int:
    try:
        return int(str(record.get("publication_date") or "").replace("-", ""))
    except ValueError:
        return 0

def _sort_key(record: Mapping[str, Any], path_rank: Mapping[str, int]) -> tuple[Any, ...]:
    return (
        path_rank.get(str(record.get("primary_path") or ""), 999),
        -int(record.get("score") or 0),
        -_date(record),
        str(record.get("title_original") or "").casefold(),
        str(record.get("canonical_id") or ""),
    )

def _path_interleave(
    records: Iterable[dict[str, Any]],
    path_order: list[str],
) -> list[dict[str, Any]]:
    rank = {path: index for index, path in enumerate(path_order)}
    pools: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        pools[str(record.get("primary_path") or "")].append(record)
    for values in pools.values():
        values.sort(key=lambda item: _sort_key(item, rank))
    result: list[dict[str, Any]] = []
    all_paths = [*path_order, *sorted(set(pools) - set(path_order))]
    while any(pools.values()):
        for path in all_paths:
            if pools[path]:
                result.append(pools[path].pop(0))
    return result

def _primary_category(record: Mapping[str, Any], policy: Mapping[str, Any]) -> str:
    categories = [str(item) for item in record.get("categories") or [] if str(item)]
    return next(
        (item for item in policy["category_order"] if item in categories),
        categories[0] if categories else "uncategorized",
    )

def _identifiers(record: Mapping[str, Any]) -> dict[str, Any]:
    return dict(record.get("identifiers") or {})

def _fetchable(record: Mapping[str, Any]) -> bool:
    identifiers = _identifiers(record)
    return any(identifiers.get(key) for key in ("pmcid", "pmid", "doi"))

def _source_order(record: Mapping[str, Any], policy: Mapping[str, Any]) -> list[str]:
    identifiers = _identifiers(record)
    key = (
        "pmcid"
        if identifiers.get("pmcid")
        else "pmid"
        if identifiers.get("pmid")
        else "doi"
        if identifiers.get("doi")
        else None
    )
    if key is None:
        return []
    return [
        source
        for source in policy["source_order"][key]
        if not (source.endswith("PMCID") and not identifiers.get("pmcid"))
        and not (source.endswith("PMID") and not identifiers.get("pmid"))
        and not (source.endswith("DOI") and not identifiers.get("doi"))
    ]

def _flatten(
    audits: Iterable[Mapping[str, Any]],
    policy: Mapping[str, Any],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    rank = {path: index for index, path in enumerate(policy["path_order"])}
    for audit in audits:
        for raw in audit.get("articles") or []:
            if not isinstance(raw, Mapping):
                continue
            record = deepcopy(dict(raw))
            key = _record_key(record)
            if key in seen:
                raise ValueError(f"duplicate triage record: {key}")
            seen.add(key)
            record["_record_key"] = key
            record["_primary_category"] = _primary_category(record, policy)
            record["_topic_signature"] = _signature(
                str(record.get("title_original") or ""),
                int(policy["topic_signature_tokens"]),
            )
            records.append(record)
    return sorted(records, key=lambda item: _sort_key(item, rank))

def _capture_band(prior: Mapping[str, Any], policy: Mapping[str, Any]) -> tuple[float, str]:
    if prior.get("unknown_metric"):
        return float(policy["unknown_capture_rate"]), "UNKNOWN_NEUTRAL"
    percentile = float(prior["registry_category_percentile"])
    for band in policy["capture_bands"]:
        if percentile >= float(band["minimum_percentile"]):
            return float(band["capture_rate"]), str(band["label"])
    raise AssertionError("validated capture bands always include a zero floor")

def _journal_contexts(
    records: list[dict[str, Any]],
    priors: Mapping[str, Mapping[str, Any]],
    policy: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[str(record.get("journal_slug") or "")].append(record)
    contexts: dict[str, dict[str, Any]] = {}
    eligible_routes = set(policy["eligible_prefetch_routes"])
    for slug, values in grouped.items():
        eligible = [record for record in values if record.get("route") in eligible_routes]
        fetchable = [record for record in eligible if _fetchable(record)]
        candidates = [
            record
            for record in fetchable
            if record.get("route") in set(policy["metric_independent_prefetch_routes"])
        ]
        mode = str(values[0].get("processing_mode") or "FULL")
        prior = dict(priors.get(slug) or {})
        capture_rate, band = _capture_band(prior, policy)
        modifier = float(policy["mode_capture_modifiers"][mode])
        hard_cap = int(policy["journal_fetch_caps"][mode])
        adaptive = math.ceil(len(fetchable) * capture_rate * modifier)
        adaptive = min(len(fetchable), hard_cap, max(len(candidates), adaptive))
        contexts[slug] = {
            "journal": values[0].get("journal"),
            "journal_slug": slug,
            "processing_mode": mode,
            "canonical_article_count": len(values),
            "eligible_article_count": len(eligible),
            "fetchable_eligible_count": len(fetchable),
            "missing_identifier_count": len(eligible) - len(fetchable),
            "metric_independent_candidate_count": len(candidates),
            "reserve_count": sum(record.get("route") == "RESERVE" for record in eligible),
            "impact_prior": prior,
            "capture_band": band,
            "metric_capture_rate": capture_rate,
            "mode_capture_modifier": modifier,
            "adaptive_fetch_target": adaptive,
            "journal_fetch_hard_cap": hard_cap,
        }
    return contexts

class _SelectionState:
    def __init__(
        self,
        policy: Mapping[str, Any],
        contexts: Mapping[str, Mapping[str, Any]],
    ) -> None:
        self.policy = policy
        self.contexts = contexts
        self.selected: list[dict[str, Any]] = []
        self.selected_keys: set[str] = set()
        self.by_journal: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
        self.topic_counts: Counter[tuple[str, str]] = Counter()
        self.reasons: dict[str, list[str]] = {}
        self.blocks: defaultdict[str, set[str]] = defaultdict(set)

    def _check(
        self,
        record: dict[str, Any],
        *,
        topic_cap_kind: str,
    ) -> tuple[bool, str | None]:
        key = record["_record_key"]
        if key in self.selected_keys:
            return False, "ALREADY_SELECTED"
        if not _fetchable(record):
            return False, "NO_FETCHABLE_IDENTIFIER"
        slug = str(record.get("journal_slug") or "")
        context = self.contexts[slug]
        if len(self.by_journal[slug]) >= int(context["journal_fetch_hard_cap"]):
            return False, "JOURNAL_FETCH_HARD_CAP"
        title = str(record.get("title_original") or "")
        if any(
            _jaccard(title, str(existing.get("title_original") or ""))
            >= float(self.policy["near_duplicate_jaccard_threshold"])
            for existing in self.by_journal[slug]
        ):
            return False, "NEAR_DUPLICATE_TITLE"
        mode = str(record.get("processing_mode") or "FULL")
        topic_cap = int(self.policy[topic_cap_kind][mode])
        topic_key = (slug, record["_topic_signature"])
        if self.topic_counts[topic_key] >= topic_cap:
            return False, "TOPIC_HARD_CAP" if "hard" in topic_cap_kind else "TOPIC_SOFT_CAP"
        return True, None

    def take(
        self,
        record: dict[str, Any],
        *,
        reason: str,
        topic_cap_kind: str,
    ) -> bool:
        ok, block = self._check(record, topic_cap_kind=topic_cap_kind)
        key = record["_record_key"]
        if not ok:
            if block and block != "ALREADY_SELECTED":
                self.blocks[key].add(block)
            return False
        slug = str(record.get("journal_slug") or "")
        self.selected.append(record)
        self.selected_keys.add(key)
        self.by_journal[slug].append(record)
        self.topic_counts[(slug, record["_topic_signature"])] += 1
        self.reasons[key] = [reason, "IDENTIFIER_AVAILABLE"]
        return True

def _selection(
    records: list[dict[str, Any]],
    contexts: Mapping[str, Mapping[str, Any]],
    policy: Mapping[str, Any],
) -> _SelectionState:
    eligible_routes = set(policy["eligible_prefetch_routes"])
    independent_routes = set(policy["metric_independent_prefetch_routes"])
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record.get("route") in eligible_routes:
            grouped[str(record.get("journal_slug") or "")].append(record)
    state = _SelectionState(policy, contexts)

    # Strong title/metadata structural signals are admitted before the impact prior.
    # Use journal round-robin rather than slug-order bulk admission so a future month
    # with more than 300 explicit candidates still respects the global ceiling without
    # letting an alphabetically early or high-volume journal monopolize it. Impact
    # metrics therefore improve reserve recall but cannot erase a low-metric journal's
    # explicit guideline/RCT/synthesis/replication signal.
    independent_remaining = {
        slug: _path_interleave(
            [
                record
                for record in values
                if record.get("route") in independent_routes
            ],
            policy["path_order"],
        )
        for slug, values in grouped.items()
    }
    while len(state.selected) < int(policy["fetch_now_target"]):
        progressed = False
        order = sorted(
            (slug for slug, pool in independent_remaining.items() if pool),
            key=lambda slug: (
                len(state.by_journal[slug])
                / max(1, int(contexts[slug]["metric_independent_candidate_count"])),
                slug,
            ),
        )
        for slug in order:
            while independent_remaining[slug]:
                candidate = independent_remaining[slug].pop(0)
                if state.take(
                    candidate,
                    reason="METRIC_INDEPENDENT_PREFETCH_CANDIDATE",
                    topic_cap_kind="topic_soft_caps_by_mode",
                ):
                    progressed = True
                    break
            if len(state.selected) >= int(policy["fetch_now_target"]):
                break
        if not progressed:
            break

    # First allocate each journal its transparent percentile- and mode-adjusted
    # share. Allocate one record per journal per pass so high-percentile journals
    # receive earlier access without bulk-consuming the global 300-record ceiling.
    adaptive_remaining = {
        slug: _path_interleave(
            [record for record in values if record.get("route") == "RESERVE"],
            policy["path_order"],
        )
        for slug, values in grouped.items()
    }
    while len(state.selected) < int(policy["fetch_now_target"]):
        progressed = False
        order = sorted(
            (
                slug
                for slug, pool in adaptive_remaining.items()
                if pool
                and len(state.by_journal[slug])
                < int(contexts[slug]["adaptive_fetch_target"])
            ),
            key=lambda slug: (
                -float(
                    contexts[slug]["impact_prior"].get(
                        "registry_category_percentile", 50.0
                    )
                ),
                len(state.by_journal[slug])
                / max(1, int(contexts[slug]["adaptive_fetch_target"])),
                slug,
            ),
        )
        for slug in order:
            while adaptive_remaining[slug]:
                candidate = adaptive_remaining[slug].pop(0)
                if state.take(
                    candidate,
                    reason="IMPACT_ADAPTIVE_TARGET",
                    topic_cap_kind="topic_soft_caps_by_mode",
                ):
                    progressed = True
                    break
            if len(state.selected) >= int(policy["fetch_now_target"]):
                break
        if not progressed:
            break

    # If capacity remains, perform an impact-prior round robin. One journal can add
    # at most one record per pass, which retains cross-journal diversity while still
    # giving higher normalized journal percentiles first access to each pass.
    remaining: dict[str, list[dict[str, Any]]] = {}
    for slug, values in grouped.items():
        pool = [record for record in values if record["_record_key"] not in state.selected_keys]
        pool.sort(
            key=lambda record: (
                0 if record.get("route") in independent_routes else 1,
                *_sort_key(record, {path: index for index, path in enumerate(policy["path_order"])}),
            )
        )
        remaining[slug] = pool

    while len(state.selected) < int(policy["fetch_now_target"]):
        progressed = False
        order = sorted(
            (slug for slug, pool in remaining.items() if pool),
            key=lambda slug: (
                -float(contexts[slug]["impact_prior"].get("registry_category_percentile", 50.0)),
                len(state.by_journal[slug])
                / max(1, int(contexts[slug]["fetchable_eligible_count"])),
                -len(remaining[slug]),
                slug,
            ),
        )
        for slug in order:
            chosen = None
            while remaining[slug]:
                candidate = remaining[slug].pop(0)
                if state.take(
                    candidate,
                    reason="IMPACT_GLOBAL_BUDGET_FILL",
                    topic_cap_kind="topic_hard_caps_by_mode",
                ):
                    chosen = candidate
                    break
            if chosen is not None:
                progressed = True
                if len(state.selected) >= int(policy["fetch_now_target"]):
                    break
        if not progressed:
            break

    for record in records:
        if record["_record_key"] in state.selected_keys:
            continue
        if record.get("route") not in eligible_routes:
            continue
        ok, block = state._check(record, topic_cap_kind="topic_hard_caps_by_mode")
        state.blocks[record["_record_key"]].add(
            block if not ok and block else "GLOBAL_MONTHLY_SOFT_CEILING"
        )
    return state

__all__ = [
    "_fetchable", "_flatten", "_identifiers", "_journal_contexts",
    "_record_key", "_selection", "_source_order",
]
