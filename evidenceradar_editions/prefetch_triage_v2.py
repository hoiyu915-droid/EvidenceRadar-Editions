from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from .prefetch_triage import build_prefetch_triage as build_v1_prefetch_triage
from .triage_policy import load_triage_policy


def _reserve_sort_key(record: dict[str, Any]) -> tuple[Any, ...]:
    return (
        -int(record.get("score") or 0),
        -int(
            str(record.get("publication_date") or "0000-00-00").replace("-", "")
            or 0
        ),
        str(record.get("title_original") or "").casefold(),
        str(record.get("canonical_id") or ""),
    )


def build_prefetch_triage(
    publications: Iterable[Any],
    *,
    catalog_root: Path | str = Path("catalog"),
    generated_at: str | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Bound the portfolio index while preserving full per-edition triage audits."""

    index, edition_artifacts = build_v1_prefetch_triage(
        publications,
        catalog_root=catalog_root,
        generated_at=generated_at,
    )
    policy = load_triage_policy(catalog_root)
    reserve_caps = policy["reserve_index_soft_caps"]

    all_records: list[dict[str, Any]] = []
    for artifact in edition_artifacts.values():
        for record in artifact.get("articles") or []:
            if not isinstance(record, dict):
                continue
            record["published_in_portfolio_index"] = record.get("route") in {
                "INTEGRITY_REVIEW",
                "FETCH_CANDIDATE",
            }
            all_records.append(record)

    reserve_by_journal: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in all_records:
        if record.get("route") == "RESERVE":
            reserve_by_journal[str(record.get("journal_slug") or "")].append(record)

    for reserve_records in reserve_by_journal.values():
        mode = str(reserve_records[0].get("processing_mode") or "FULL")
        cap = int(reserve_caps[mode])
        reserve_records.sort(key=_reserve_sort_key)
        for record in reserve_records[:cap]:
            record["published_in_portfolio_index"] = True
        for record in reserve_records[cap:]:
            reasons = record.setdefault("reason_codes", [])
            if "RESERVE_INDEX_SOFT_CAP" not in reasons:
                reasons.append("RESERVE_INDEX_SOFT_CAP")

    published = [
        record for record in all_records if record["published_in_portfolio_index"]
    ]
    route_order = {
        "INTEGRITY_REVIEW": 0,
        "FETCH_CANDIDATE": 1,
        "RESERVE": 2,
    }
    published.sort(
        key=lambda record: (
            route_order.get(str(record.get("route")), 99),
            *_reserve_sort_key(record),
            str(record.get("journal") or "").casefold(),
        )
    )

    counts = index.setdefault("counts", {})
    total_reserve = int(counts.get("reserve_count") or 0)
    published_reserve = sum(
        1 for record in published if record.get("route") == "RESERVE"
    )
    counts["published_reserve_count"] = published_reserve
    counts["unpublished_reserve_count"] = total_reserve - published_reserve
    counts["published_index_count"] = len(published)
    index.setdefault("policy", {})["reserve_index_soft_caps"] = reserve_caps
    index["item_count"] = len(published)
    index["items"] = published
    index["portfolio_index_semantics"] = (
        "All actionable records plus a bounded reserve sample per journal. "
        "Unpublished reserve and catalog-only records remain in each edition's "
        "complete triage.json audit."
    )

    for artifact in edition_artifacts.values():
        records = [
            record
            for record in artifact.get("articles") or []
            if isinstance(record, dict)
        ]
        artifact.setdefault("counts", {})["published_in_portfolio_index"] = sum(
            1 for record in records if record["published_in_portfolio_index"]
        )
        artifact["portfolio_index_semantics"] = index[
            "portfolio_index_semantics"
        ]
    return index, edition_artifacts
