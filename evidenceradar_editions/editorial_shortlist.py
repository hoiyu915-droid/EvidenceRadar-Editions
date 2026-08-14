from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable, Mapping

from .utils import utc_now_iso

SHORTLIST_POLICY_FILENAME = "editorial-shortlist-policy.json"
SHORTLIST_INDEX_FILENAME = "editorial-shortlist.json"
SHORTLIST_PAGE_FILENAME = "editorial-shortlist.html"
ABSTRACT_FETCH_PLAN_FILENAME = "abstract-fetch-plan.json"

_MODES = ("FULL", "TRIAGE", "INDEX_ONLY", "SUSPENDED")
_ROUTES = ("FETCH_NOW", "HOLD_RESERVE", "CATALOG_ONLY")
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


class EditorialShortlistPolicyError(ValueError):
    pass


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode()).hexdigest()


def builtin_editorial_shortlist_policy() -> dict[str, Any]:
    paths = [
        "GUIDANCE", "EVIDENCE_SYNTHESIS", "RANDOMIZED_TRIAL",
        "REPLICATION_VALIDATION", "SAFETY_SIGNAL", "RESOURCE_BENCHMARK",
        "PROSPECTIVE_LONGITUDINAL", "OBSERVATIONAL_DESIGN", "SURVEY",
        "PROTOCOL", "CASE_REPORT",
    ]
    categories = [
        "clinical_medicine", "interdisciplinary", "sport_nutrition_fitness",
        "llm_research", "human_ai", "sport_science", "chemistry",
        "physics_astronomy", "uncategorized",
    ]
    return {
        "schema_version": "1.0",
        "artifact_type": "EvidenceRadar_Editions_EditorialShortlistPolicy",
        "policy_id": "editorial-shortlist-v1",
        "semantics": (
            "Deterministic title-and-bibliographic-metadata editorial shortlisting "
            "for deciding which small set should receive abstract acquisition next. "
            "It is not evidence-quality grading, novelty assessment, scope "
            "verification, or full-text review."
        ),
        "fetch_now_target": 48,
        "hold_reserve_target": 144,
        "eligible_prefetch_routes": ["FETCH_CANDIDATE", "RESERVE"],
        "fetch_now_source_routes": ["FETCH_CANDIDATE"],
        "reserve_backfill_enabled": True,
        "journal_fetch_caps": dict(zip(_MODES, (4, 8, 2, 0))),
        "journal_hold_caps": dict(zip(_MODES, (12, 24, 4, 0))),
        "category_order": categories,
        "category_minimums": dict(zip(categories[:6], (10, 6, 6, 5, 5, 3))),
        "category_soft_caps": dict(zip(categories, (14, 10, 8, 8, 6, 4, 4, 4, 6))),
        "category_hard_caps": dict(zip(categories, (18, 12, 10, 10, 8, 5, 5, 5, 8))),
        "path_order": paths,
        "path_minimums": dict(zip(paths, (2, 6, 6, 4, 4, 4, 3, 2, 1, 0, 0))),
        "path_soft_caps": dict(zip(paths, (4, 10, 10, 6, 7, 6, 5, 3, 2, 1, 1))),
        "path_hard_caps": dict(zip(paths, (4, 14, 14, 8, 10, 10, 8, 6, 4, 2, 2))),
        "near_duplicate_jaccard_threshold": 0.72,
        "topic_signature_tokens": 4,
        "topic_soft_cap_per_journal": 2,
        "hold_topic_soft_cap_per_journal": 4,
        "source_order": {
            "pmcid": ["EUROPE_PMC_PMCID", "PUBMED_PMID", "EUROPE_PMC_PMID", "EUROPE_PMC_DOI"],
            "pmid": ["PUBMED_PMID", "EUROPE_PMC_PMID", "EUROPE_PMC_DOI"],
            "doi": ["EUROPE_PMC_DOI"],
        },
    }


def validate_editorial_shortlist_policy(value: Mapping[str, Any]) -> dict[str, Any]:
    p = deepcopy(dict(value))
    if p.get("artifact_type") != "EvidenceRadar_Editions_EditorialShortlistPolicy":
        raise EditorialShortlistPolicyError("unexpected editorial shortlist policy type")
    required = (
        "policy_id", "semantics", "fetch_now_target", "hold_reserve_target",
        "journal_fetch_caps", "journal_hold_caps", "category_order",
        "category_minimums", "category_soft_caps", "category_hard_caps",
        "path_order", "path_minimums", "path_soft_caps", "path_hard_caps",
        "source_order",
    )
    missing = [key for key in required if key not in p]
    if missing:
        raise EditorialShortlistPolicyError(f"missing policy fields: {missing}")
    p["fetch_now_target"] = int(p["fetch_now_target"])
    p["hold_reserve_target"] = int(p["hold_reserve_target"])
    if p["fetch_now_target"] < 1 or p["hold_reserve_target"] < p["fetch_now_target"]:
        raise EditorialShortlistPolicyError("invalid shortlist targets")
    for key in ("journal_fetch_caps", "journal_hold_caps"):
        if set(p[key]) != set(_MODES):
            raise EditorialShortlistPolicyError(f"{key} must contain {_MODES}")
        p[key] = {mode: int(p[key][mode]) for mode in _MODES}
    for key in ("category_order", "path_order"):
        if not isinstance(p[key], list) or len(p[key]) != len(set(p[key])):
            raise EditorialShortlistPolicyError(f"invalid {key}")
    for key in (
        "category_minimums", "category_soft_caps", "category_hard_caps",
        "path_minimums", "path_soft_caps", "path_hard_caps",
    ):
        p[key] = {str(k): int(v) for k, v in dict(p[key]).items()}
    for name in p["category_order"]:
        minimum = p["category_minimums"].get(name, 0)
        soft = p["category_soft_caps"].get(name, p["fetch_now_target"])
        hard = p["category_hard_caps"].get(name, p["fetch_now_target"])
        if not 0 <= minimum <= soft <= hard:
            raise EditorialShortlistPolicyError(f"invalid category caps: {name}")
    for name in p["path_order"]:
        minimum = p["path_minimums"].get(name, 0)
        soft = p["path_soft_caps"].get(name, p["fetch_now_target"])
        hard = p["path_hard_caps"].get(name, p["fetch_now_target"])
        if not 0 <= minimum <= soft <= hard:
            raise EditorialShortlistPolicyError(f"invalid path caps: {name}")
    p["near_duplicate_jaccard_threshold"] = float(p["near_duplicate_jaccard_threshold"])
    if not 0 < p["near_duplicate_jaccard_threshold"] <= 1:
        raise EditorialShortlistPolicyError("invalid duplicate threshold")
    for key in ("topic_signature_tokens", "topic_soft_cap_per_journal", "hold_topic_soft_cap_per_journal"):
        p[key] = int(p[key])
    for key in ("pmcid", "pmid", "doi"):
        if not isinstance(p["source_order"].get(key), list):
            raise EditorialShortlistPolicyError(f"invalid source_order.{key}")
    p.setdefault("eligible_prefetch_routes", ["FETCH_CANDIDATE", "RESERVE"])
    p.setdefault("fetch_now_source_routes", ["FETCH_CANDIDATE"])
    p.setdefault("reserve_backfill_enabled", True)
    return p


def load_editorial_shortlist_policy(catalog_root: Path | str = Path("catalog")) -> dict[str, Any]:
    path = Path(catalog_root) / SHORTLIST_POLICY_FILENAME
    value = (
        json.loads(path.read_text(encoding="utf-8"))
        if path.is_file()
        else builtin_editorial_shortlist_policy()
    )
    if not isinstance(value, dict):
        raise EditorialShortlistPolicyError("shortlist policy must be an object")
    return validate_editorial_shortlist_policy(value)


def _tokens(title: str) -> list[str]:
    text = unicodedata.normalize("NFKD", str(title or "")).casefold()
    return [x for x in _WORD.findall(text) if x not in _STOP and len(x) > 2]


def _signature(title: str, size: int) -> str:
    found: list[str] = []
    for token in _tokens(title):
        if token not in found:
            found.append(token)
        if len(found) >= size:
            break
    return "|".join(found) or "untitled"


def _jaccard(a: str, b: str) -> float:
    left, right = set(_tokens(a)), set(_tokens(b))
    return len(left & right) / len(left | right) if left and right else 0.0


def _record_key(record: Mapping[str, Any]) -> str:
    cid = str(record.get("canonical_id") or "").strip()
    if not cid:
        cid = "fallback:" + _digest({
            "title": record.get("title_original"),
            "date": record.get("publication_date"),
        })
    return "|".join((
        str(record.get("journal_slug") or ""),
        str(record.get("period_key") or ""),
        str(record.get("revision") or ""),
        cid,
    ))


def _date(record: Mapping[str, Any]) -> int:
    try:
        return int(str(record.get("publication_date") or "").replace("-", ""))
    except ValueError:
        return 0


def _sort(record: Mapping[str, Any], rank: Mapping[str, int] | None = None) -> tuple[Any, ...]:
    return (
        rank.get(str(record.get("primary_path") or ""), 999) if rank else 0,
        -int(record.get("score") or 0),
        -_date(record),
        str(record.get("journal") or "").casefold(),
        str(record.get("title_original") or "").casefold(),
        _record_key(record),
    )


def _round_robin(records: Iterable[dict[str, Any]], rank: Mapping[str, int] | None = None) -> list[dict[str, Any]]:
    groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[str(record.get("journal_slug") or "")].append(record)
    for values in groups.values():
        values.sort(key=lambda r: _sort(r, rank))
    order = sorted(groups, key=lambda slug: _sort(groups[slug][0], rank))
    result: list[dict[str, Any]] = []
    while any(groups.values()):
        for slug in order:
            if groups[slug]:
                result.append(groups[slug].pop(0))
    return result


def _category(record: Mapping[str, Any], policy: Mapping[str, Any]) -> str:
    categories = [str(x) for x in record.get("categories") or [] if str(x)]
    return next((x for x in policy["category_order"] if x in categories), categories[0] if categories else "uncategorized")


def _identifiers(record: Mapping[str, Any]) -> dict[str, Any]:
    return dict(record.get("identifiers") or {})


def _fetchable(record: Mapping[str, Any]) -> bool:
    ids = _identifiers(record)
    return any(ids.get(key) for key in ("pmcid", "pmid", "doi"))


def _source_order(record: Mapping[str, Any], policy: Mapping[str, Any]) -> list[str]:
    ids = _identifiers(record)
    key = "pmcid" if ids.get("pmcid") else "pmid" if ids.get("pmid") else "doi" if ids.get("doi") else None
    if key is None:
        return []
    return [
        source for source in policy["source_order"][key]
        if not (source.endswith("PMCID") and not ids.get("pmcid"))
        and not (source.endswith("PMID") and not ids.get("pmid"))
        and not (source.endswith("DOI") and not ids.get("doi"))
    ]


def _flatten(audits: Iterable[Mapping[str, Any]], policy: Mapping[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
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
            record["_primary_category"] = _category(record, policy)
            record["_topic_signature"] = _signature(
                str(record.get("title_original") or ""),
                int(policy["topic_signature_tokens"]),
            )
            records.append(record)
    return sorted(records, key=_sort)


class _State:
    def __init__(self, policy: Mapping[str, Any]) -> None:
        self.p = policy
        self.selected: list[dict[str, Any]] = []
        self.keys: set[str] = set()
        self.journal: Counter[str] = Counter()
        self.path: Counter[str] = Counter()
        self.category: Counter[str] = Counter()
        self.topic: Counter[tuple[str, str]] = Counter()
        self.titles: defaultdict[str, list[str]] = defaultdict(list)
        self.reasons: dict[str, list[str]] = {}
        self.blocks: defaultdict[str, set[str]] = defaultdict(set)

    def check(self, record: dict[str, Any], phase: str) -> tuple[bool, str | None]:
        key = record["_record_key"]
        if key in self.keys:
            return False, "ALREADY_SELECTED"
        if not _fetchable(record):
            return False, "NO_FETCHABLE_IDENTIFIER"
        journal = str(record.get("journal_slug") or "")
        title = str(record.get("title_original") or "")
        if any(
            _jaccard(title, selected) >= self.p["near_duplicate_jaccard_threshold"]
            for selected in self.titles[journal]
        ):
            return False, "NEAR_DUPLICATE_TITLE"
        topic = (journal, record["_topic_signature"])
        if self.topic[topic] >= self.p["topic_soft_cap_per_journal"]:
            return False, "TOPIC_SOFT_CAP"
        mode = str(record.get("processing_mode") or "FULL")
        if self.journal[journal] >= self.p["journal_fetch_caps"].get(mode, 0):
            return False, "JOURNAL_FETCH_CAP"
        path = str(record.get("primary_path") or "")
        if self.path[path] >= self.p[f"path_{phase}_caps"].get(path, self.p["fetch_now_target"]):
            return False, f"PATH_{phase.upper()}_CAP"
        category = record["_primary_category"]
        if self.category[category] >= self.p[f"category_{phase}_caps"].get(category, self.p["fetch_now_target"]):
            return False, f"CATEGORY_{phase.upper()}_CAP"
        return True, None

    def take(self, record: dict[str, Any], phase: str, reason: str) -> bool:
        ok, block = self.check(record, phase)
        key = record["_record_key"]
        if not ok:
            if block and block != "ALREADY_SELECTED":
                self.blocks[key].add(block)
            return False
        self.selected.append(record)
        self.keys.add(key)
        journal = str(record.get("journal_slug") or "")
        self.journal[journal] += 1
        self.path[str(record.get("primary_path") or "")] += 1
        self.category[record["_primary_category"]] += 1
        self.topic[(journal, record["_topic_signature"])] += 1
        self.titles[journal].append(str(record.get("title_original") or ""))
        self.reasons[key] = [reason, "IDENTIFIER_AVAILABLE"]
        return True


def _fill(state: _State, pools: Mapping[str, list[dict[str, Any]]], policy: Mapping[str, Any], target: int, phase: str, reason: str) -> None:
    while len(state.selected) < target:
        progressed = False
        for path in policy["path_order"]:
            for record in pools.get(path, []):
                if state.take(record, phase, reason):
                    progressed = True
                    break
            if len(state.selected) >= target:
                return
        if not progressed:
            return


def _select(records: list[dict[str, Any]], policy: Mapping[str, Any]) -> _State:
    rank = {path: i for i, path in enumerate(policy["path_order"])}
    candidates = [
        r for r in records
        if r.get("route") in set(policy["fetch_now_source_routes"])
        and r.get("primary_path") in rank
    ]
    pools = {
        path: _round_robin([r for r in candidates if r.get("primary_path") == path])
        for path in policy["path_order"]
    }
    state = _State(policy)
    for category in policy["category_order"]:
        target = policy["category_minimums"].get(category, 0)
        ordered = _round_robin(
            [r for r in candidates if r["_primary_category"] == category],
            rank,
        )
        while state.category[category] < target:
            if not any(state.take(r, "soft", f"CATEGORY_FLOOR:{category}") for r in ordered):
                break
    for path in policy["path_order"]:
        target = policy["path_minimums"].get(path, 0)
        while state.path[path] < target:
            if not any(state.take(r, "soft", f"PATH_FLOOR:{path}") for r in pools[path]):
                break
    _fill(state, pools, policy, policy["fetch_now_target"], "soft", "BALANCED_SOFT_FILL")
    _fill(state, pools, policy, policy["fetch_now_target"], "hard", "BALANCED_HARD_FILL")
    if len(state.selected) < policy["fetch_now_target"] and policy["reserve_backfill_enabled"]:
        reserve = [r for r in records if r.get("route") == "RESERVE" and r.get("primary_path") in rank]
        reserve_pools = {
            path: _round_robin([r for r in reserve if r.get("primary_path") == path])
            for path in policy["path_order"]
        }
        _fill(state, reserve_pools, policy, policy["fetch_now_target"], "hard", "PREFETCH_RESERVE_BACKFILL")
    for record in records:
        if record["_record_key"] in state.keys or record.get("route") not in {"FETCH_CANDIDATE", "RESERVE"}:
            continue
        ok, block = state.check(record, "hard")
        state.blocks[record["_record_key"]].add(
            block if not ok and block else "FETCH_NOW_GLOBAL_TARGET"
        )
    return state


def _ordered(records: list[dict[str, Any]], policy: Mapping[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    known = set(policy["path_order"])
    for path in policy["path_order"]:
        result.extend(_round_robin([r for r in records if r.get("primary_path") == path]))
    result.extend(_round_robin([r for r in records if r.get("primary_path") not in known]))
    return result


def _hold(records: list[dict[str, Any]], selected: set[str], policy: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    result: list[dict[str, Any]] = []
    reasons: dict[str, list[str]] = {}
    journal: Counter[str] = Counter()
    topic: Counter[tuple[str, str]] = Counter()
    for label, route in (("UNSELECTED_FETCH_CANDIDATE", "FETCH_CANDIDATE"), ("PREFETCH_RESERVE", "RESERVE")):
        pool = _ordered([r for r in records if r["_record_key"] not in selected and r.get("route") == route], policy)
        for record in pool:
            if len(result) >= policy["hold_reserve_target"]:
                return result, reasons
            slug = str(record.get("journal_slug") or "")
            mode = str(record.get("processing_mode") or "FULL")
            tkey = (slug, record["_topic_signature"])
            if journal[slug] >= policy["journal_hold_caps"].get(mode, 0):
                continue
            if topic[tkey] >= policy["hold_topic_soft_cap_per_journal"]:
                continue
            result.append(record)
            journal[slug] += 1
            topic[tkey] += 1
            reasons[record["_record_key"]] = [label, "HOLD_BUDGET_INCLUDED"]
    return result, reasons


def _decision(record: Mapping[str, Any], route: str, reasons: list[str]) -> dict[str, Any]:
    if route not in _ROUTES:
        raise ValueError(f"unsupported route: {route}")
    integrity = record.get("route") == "INTEGRITY_REVIEW"
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
        "decision_reasons": list(dict.fromkeys(reasons)),
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


def _plan(fetch: list[dict[str, Any]], policy: Mapping[str, Any], binding: str) -> dict[str, Any]:
    items = []
    for ordinal, item in enumerate(fetch, 1):
        items.append({
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
            "status": "PLANNED",
            "abstract_fetch_requested": False,
            "abstract_acquired": False,
            "abstract_reviewed": False,
            "full_text_fetched": False,
            "evidence_evaluated": False,
        })
    plan_binding = _digest({
        "shortlist_binding_sha256": binding,
        "items": [
            {"record_key": x["record_key"], "identifiers": x["identifiers"], "source_order": x["source_order"]}
            for x in items
        ],
    })
    return {
        "schema_version": "1.0",
        "artifact_type": "EvidenceRadar_Editions_AbstractFetchPlan",
        "semantics": (
            "Bounded handoff containing only FETCH_NOW records. It performs no "
            "network request and contains no abstract text."
        ),
        "shortlist_binding_sha256": binding,
        "plan_binding_sha256": plan_binding,
        "item_count": len(items),
        "items": items,
    }


def build_editorial_shortlist(
    audits: Iterable[Mapping[str, Any]],
    *,
    policy: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    p = validate_editorial_shortlist_policy(policy or builtin_editorial_shortlist_policy())
    records = _flatten(audits, p)
    policy_sha = _digest(p)
    source_rows = [
        {
            "record_key": r["_record_key"],
            "prefetch_route": r.get("route"),
            "primary_path": r.get("primary_path"),
            "score": int(r.get("score") or 0),
            "reason_codes": list(r.get("reason_codes") or []),
            "processing_mode": r.get("processing_mode"),
            "identifiers": _identifiers(r),
        }
        for r in records
    ]
    source_digest = _digest(source_rows)
    state = _select(records, p)
    held, hold_reasons = _hold(records, state.keys, p)
    held_keys = {r["_record_key"] for r in held}
    decisions: list[dict[str, Any]] = []
    for record in records:
        key = record["_record_key"]
        if key in state.keys:
            route, reasons = "FETCH_NOW", state.reasons.get(key, ["BALANCED_SELECTION"])
        elif key in held_keys:
            route = "HOLD_RESERVE"
            reasons = [*hold_reasons.get(key, []), *sorted(state.blocks.get(key, set()))]
        else:
            route = "CATALOG_ONLY"
            if record.get("route") == "INTEGRITY_REVIEW":
                reasons = ["INTEGRITY_MAINTENANCE_NOT_ABSTRACT_FETCH"]
            elif not _fetchable(record) and record.get("route") in {"FETCH_CANDIDATE", "RESERVE"}:
                reasons = ["NO_FETCHABLE_IDENTIFIER"]
            elif record.get("route") == "CATALOG_ONLY":
                reasons = ["PREFETCH_CATALOG_ONLY"]
            elif record.get("route") == "RESERVE":
                reasons = ["HOLD_RESERVE_BUDGET"]
            else:
                reasons = ["FETCH_NOW_BUDGET", *sorted(state.blocks.get(key, set()))]
        decisions.append(_decision(record, route, reasons or ["CATALOG_ONLY"]))
    decisions.sort(key=lambda x: (_ROUTES.index(x["editorial_route"]), -x["prefetch_score"], str(x.get("journal") or "").casefold(), str(x.get("title_original") or "").casefold(), x["record_key"]))
    decision_rows = [
        {"record_key": x["record_key"], "editorial_route": x["editorial_route"], "decision_reasons": x["decision_reasons"]}
        for x in sorted(decisions, key=lambda x: x["record_key"])
    ]
    binding = _digest({
        "policy_sha256": policy_sha,
        "source_prefetch_digest": source_digest,
        "decisions": decision_rows,
    })
    fetch = [x for x in decisions if x["editorial_route"] == "FETCH_NOW"]
    hold = [x for x in decisions if x["editorial_route"] == "HOLD_RESERVE"]
    integrity = [x for x in decisions if x["integrity_attention"]]
    plan = _plan(fetch, p, binding)
    counts = Counter(x["editorial_route"] for x in decisions)
    path_counts = Counter(str(x["primary_path"]) for x in fetch)
    category_counts = Counter(str(x["primary_category"]) for x in fetch)
    journal_counts = Counter(str(x["journal_slug"]) for x in fetch)
    by_journal: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    by_edition: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in decisions:
        by_journal[str(item["journal_slug"])].append(item)
        by_edition[str(item.get("edition_url") or "")].append(item)
    journal_summaries = []
    for slug, values in sorted(by_journal.items(), key=lambda pair: (-sum(v["editorial_route"] == "FETCH_NOW" for v in pair[1]), str(pair[1][0].get("journal") or "").casefold())):
        c = Counter(v["editorial_route"] for v in values)
        journal_summaries.append({
            "journal": values[0].get("journal"),
            "journal_slug": slug,
            "processing_mode": values[0].get("processing_mode"),
            "canonical_article_count": len(values),
            "fetch_now_count": c["FETCH_NOW"],
            "hold_reserve_count": c["HOLD_RESERVE"],
            "catalog_only_count": c["CATALOG_ONLY"],
            "integrity_attention_count": sum(v["integrity_attention"] for v in values),
        })
    root_items = [*fetch, *hold]
    root_keys = {x["record_key"] for x in root_items}
    root_items.extend(x for x in integrity if x["record_key"] not in root_keys)
    generated = generated_at or utc_now_iso()
    root = {
        "schema_version": "1.0",
        "artifact_type": "EvidenceRadar_Editions_EditorialShortlist",
        "generated_at": generated,
        "policy_id": p["policy_id"],
        "policy_file": SHORTLIST_POLICY_FILENAME,
        "policy_sha256": policy_sha,
        "source_prefetch_digest": source_digest,
        "shortlist_binding_sha256": binding,
        "semantics": p["semantics"],
        "scientific_boundary": (
            "FETCH_NOW means only earlier bounded abstract acquisition. It does "
            "not mean relevant, valid, novel, clinically actionable, or full-text supported."
        ),
        "counts": {
            "canonical_article_count": len(decisions),
            "fetch_now_target": p["fetch_now_target"],
            "fetch_now_count": counts["FETCH_NOW"],
            "hold_reserve_target": p["hold_reserve_target"],
            "hold_reserve_count": counts["HOLD_RESERVE"],
            "catalog_only_count": counts["CATALOG_ONLY"],
            "integrity_attention_count": len(integrity),
            "root_item_count": len(root_items),
        },
        "fetch_now_path_counts": dict(sorted(path_counts.items())),
        "fetch_now_category_counts": dict(sorted(category_counts.items())),
        "fetch_now_journal_counts": dict(sorted(journal_counts.items())),
        "journal_summaries": journal_summaries,
        "items": root_items,
        "abstract_fetch_plan": plan,
    }
    edition_artifacts = {}
    for edition_url, values in by_edition.items():
        c = Counter(v["editorial_route"] for v in values)
        edition_artifacts[edition_url] = {
            "schema_version": "1.0",
            "artifact_type": "EvidenceRadar_Editions_EditorialShortlistAudit",
            "generated_at": generated,
            "policy_id": p["policy_id"],
            "policy_sha256": policy_sha,
            "source_prefetch_digest": source_digest,
            "shortlist_binding_sha256": binding,
            "journal": values[0].get("journal") if values else None,
            "journal_slug": values[0].get("journal_slug") if values else None,
            "period_key": values[0].get("period_key") if values else None,
            "revision": values[0].get("revision") if values else None,
            "semantics": p["semantics"],
            "counts": {
                "canonical_article_count": len(values),
                "fetch_now_count": c["FETCH_NOW"],
                "hold_reserve_count": c["HOLD_RESERVE"],
                "catalog_only_count": c["CATALOG_ONLY"],
                "integrity_attention_count": sum(v["integrity_attention"] for v in values),
            },
            "articles": sorted(values, key=lambda x: (_ROUTES.index(x["editorial_route"]), -x["prefetch_score"], str(x.get("title_original") or "").casefold(), x["record_key"])),
        }
    return root, edition_artifacts


__all__ = [
    "ABSTRACT_FETCH_PLAN_FILENAME", "SHORTLIST_INDEX_FILENAME",
    "SHORTLIST_PAGE_FILENAME", "SHORTLIST_POLICY_FILENAME",
    "EditorialShortlistPolicyError", "build_editorial_shortlist",
    "builtin_editorial_shortlist_policy", "load_editorial_shortlist_policy",
    "validate_editorial_shortlist_policy",
]
