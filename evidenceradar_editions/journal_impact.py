from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit

IMPACT_REGISTRY_FILENAME = "journal-impact-metrics.json"
_ALLOWED_METRICS = ("JIF", "CITESCORE")
_ALLOWED_STATUSES = {
    "VERIFIED_PUBLISHER_DISPLAY",
    "NO_PUBLIC_VERIFIED_METRIC",
    "NOT_YET_METRIC_ELIGIBLE",
}


class JournalImpactRegistryError(ValueError):
    pass


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def impact_registry_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def builtin_journal_impact_registry() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "artifact_type": "EvidenceRadar_Editions_JournalImpactRegistry",
        "observed_at": None,
        "observation_note": None,
        "semantics": (
            "Publisher-displayed journal metrics used only as an operational "
            "abstract-acquisition prior. Missing metrics receive a neutral prior."
        ),
        "metric_preference": ["JIF", "CITESCORE"],
        "normalization": {
            "peer_group": "registry_category_and_metric_kind",
            "percentile_method": "midrank",
            "multi_category_aggregation": "arithmetic_mean",
            "unknown_percentile": 50.0,
        },
        "journals": {},
    }


def _safe_url(value: Any, *, name: str) -> str | None:
    if value in {None, ""}:
        return None
    raw = str(value).strip()
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise JournalImpactRegistryError(f"{name} must be a public HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise JournalImpactRegistryError(f"{name} must not contain credentials")
    return raw


def validate_journal_impact_registry(value: Mapping[str, Any]) -> dict[str, Any]:
    registry = deepcopy(dict(value))
    if registry.get("artifact_type") != "EvidenceRadar_Editions_JournalImpactRegistry":
        raise JournalImpactRegistryError("unexpected journal impact registry type")
    preference = list(registry.get("metric_preference") or _ALLOWED_METRICS)
    if not preference or len(preference) != len(set(preference)):
        raise JournalImpactRegistryError("metric_preference must be a unique non-empty list")
    if any(metric not in _ALLOWED_METRICS for metric in preference):
        raise JournalImpactRegistryError("unsupported metric in metric_preference")

    normalization = dict(registry.get("normalization") or {})
    unknown = float(normalization.get("unknown_percentile", 50.0))
    if not 0 <= unknown <= 100:
        raise JournalImpactRegistryError("unknown_percentile must be between 0 and 100")

    raw_journals = registry.get("journals") or {}
    if not isinstance(raw_journals, dict):
        raise JournalImpactRegistryError("journals must be a JSON object")
    journals: dict[str, dict[str, Any]] = {}
    for slug, raw in raw_journals.items():
        if not isinstance(slug, str) or not slug:
            raise JournalImpactRegistryError("journal slug must be a non-empty string")
        if not isinstance(raw, dict):
            raise JournalImpactRegistryError(f"journals.{slug} must be an object")
        status = str(raw.get("status") or "")
        if status not in _ALLOWED_STATUSES:
            raise JournalImpactRegistryError(f"unsupported journals.{slug}.status: {status}")
        categories = [str(item) for item in raw.get("categories") or [] if str(item)]
        if not categories or len(categories) != len(set(categories)):
            raise JournalImpactRegistryError(
                f"journals.{slug}.categories must be a unique non-empty list"
            )
        metrics_raw = raw.get("metrics") or {}
        if not isinstance(metrics_raw, dict):
            raise JournalImpactRegistryError(f"journals.{slug}.metrics must be an object")
        metrics: dict[str, dict[str, Any]] = {}
        for kind, metric_raw in metrics_raw.items():
            if kind not in _ALLOWED_METRICS:
                raise JournalImpactRegistryError(
                    f"unsupported journals.{slug}.metrics kind: {kind}"
                )
            if not isinstance(metric_raw, dict):
                raise JournalImpactRegistryError(
                    f"journals.{slug}.metrics.{kind} must be an object"
                )
            metric_value = float(metric_raw.get("value"))
            if metric_value <= 0:
                raise JournalImpactRegistryError(
                    f"journals.{slug}.metrics.{kind}.value must be positive"
                )
            year_raw = metric_raw.get("year")
            year = int(year_raw) if year_raw is not None else None
            if year is not None and not 2000 <= year <= 2100:
                raise JournalImpactRegistryError(
                    f"journals.{slug}.metrics.{kind}.year is invalid"
                )
            metrics[kind] = {"value": metric_value, "year": year}
        if status == "VERIFIED_PUBLISHER_DISPLAY" and not metrics:
            raise JournalImpactRegistryError(
                f"verified journal metric entry has no metric: {slug}"
            )
        journals[slug] = {
            "name": str(raw.get("name") or slug),
            "publisher": str(raw.get("publisher") or ""),
            "categories": categories,
            "status": status,
            "metrics": metrics,
            "source_url": _safe_url(raw.get("source_url"), name=f"journals.{slug}.source_url"),
            "source_note": str(raw.get("source_note") or "").strip() or None,
        }

    return {
        "schema_version": str(registry.get("schema_version") or "1.0"),
        "artifact_type": "EvidenceRadar_Editions_JournalImpactRegistry",
        "observed_at": registry.get("observed_at"),
        "observation_note": str(registry.get("observation_note") or "").strip() or None,
        "semantics": str(registry.get("semantics") or "").strip(),
        "metric_preference": preference,
        "normalization": {
            "peer_group": str(
                normalization.get("peer_group")
                or "registry_category_and_metric_kind"
            ),
            "percentile_method": str(
                normalization.get("percentile_method") or "midrank"
            ),
            "multi_category_aggregation": str(
                normalization.get("multi_category_aggregation")
                or "arithmetic_mean"
            ),
            "unknown_percentile": unknown,
        },
        "journals": journals,
    }


def _enrich_registry_identity(
    value: Mapping[str, Any],
    *,
    catalog_root: Path,
) -> dict[str, Any]:
    enriched = deepcopy(dict(value))
    raw_journals = enriched.get("journals") or {}
    if not isinstance(raw_journals, dict):
        return enriched
    identity_path = catalog_root / "journals.json"
    identities: dict[str, dict[str, Any]] = {}
    if identity_path.is_file():
        identity_value = json.loads(identity_path.read_text(encoding="utf-8"))
        if isinstance(identity_value, dict):
            identities = {
                str(item.get("slug") or ""): item
                for item in identity_value.get("journals") or []
                if isinstance(item, dict) and item.get("slug")
            }
    default_note = str(enriched.get("observation_note") or "").strip() or None
    merged: dict[str, Any] = {}
    for slug, raw in raw_journals.items():
        item = deepcopy(dict(raw))
        identity = identities.get(str(slug), {})
        item.setdefault("name", identity.get("name") or slug)
        item.setdefault("publisher", identity.get("publisher") or "")
        item.setdefault("categories", list(identity.get("categories") or []))
        if not item.get("source_note") and default_note and item.get("metrics"):
            item["source_note"] = default_note
        merged[str(slug)] = item
    enriched["journals"] = merged
    return enriched


def load_journal_impact_registry(
    catalog_root: Path | str = Path("catalog"),
) -> dict[str, Any]:
    root = Path(catalog_root)
    path = root / IMPACT_REGISTRY_FILENAME
    if not path.is_file():
        return validate_journal_impact_registry(builtin_journal_impact_registry())
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise JournalImpactRegistryError("journal impact registry must be a JSON object")
    return validate_journal_impact_registry(
        _enrich_registry_identity(value, catalog_root=root)
    )


def _primary_metric(
    entry: Mapping[str, Any],
    preference: Iterable[str],
) -> tuple[str | None, float | None, int | None]:
    metrics = entry.get("metrics") or {}
    for kind in preference:
        raw = metrics.get(kind)
        if raw:
            return kind, float(raw["value"]), raw.get("year")
    return None, None, None


def _midrank_percentile(value: float, peers: list[float]) -> float:
    if not peers:
        return 50.0
    less = sum(item < value for item in peers)
    equal = sum(item == value for item in peers)
    return 100.0 * (less + 0.5 * equal) / len(peers)


def resolve_journal_impact_priors(
    registry: Mapping[str, Any],
    *,
    journal_slugs: Iterable[str] | None = None,
    neutral_percentile: float | None = None,
) -> dict[str, dict[str, Any]]:
    normalized = validate_journal_impact_registry(registry)
    preference = normalized["metric_preference"]
    neutral = (
        float(neutral_percentile)
        if neutral_percentile is not None
        else float(normalized["normalization"]["unknown_percentile"])
    )
    if not 0 <= neutral <= 100:
        raise JournalImpactRegistryError("neutral_percentile must be between 0 and 100")

    # Build one peer pool per registry category and metric kind from every
    # publisher-displayed metric. A CiteScore-only journal is therefore compared
    # with other journals' CiteScores rather than becoming a one-item peer group
    # merely because JIF is preferred when both metrics exist.
    peers: dict[tuple[str, str], list[float]] = {}
    for entry in normalized["journals"].values():
        for kind, metric in (entry.get("metrics") or {}).items():
            metric_value = float(metric["value"])
            for category in entry["categories"]:
                peers.setdefault((category, kind), []).append(metric_value)

    wanted = set(journal_slugs or normalized["journals"].keys())
    priors: dict[str, dict[str, Any]] = {}
    for slug in sorted(wanted):
        entry = normalized["journals"].get(slug)
        if entry is None:
            priors[slug] = {
                "metric_status": "NOT_IN_REGISTRY",
                "primary_metric_kind": None,
                "primary_metric_value": None,
                "metric_year": None,
                "category_percentiles": {},
                "registry_category_percentile": round(neutral, 6),
                "unknown_metric": True,
                "source_url": None,
                "source_note": "Journal is not present in the impact registry.",
            }
            continue
        kind, metric_value, metric_year = _primary_metric(entry, preference)
        if kind is None or metric_value is None:
            percentiles: dict[str, float] = {}
            aggregate = neutral
            unknown_metric = True
        else:
            percentiles = {
                category: round(
                    _midrank_percentile(
                        metric_value,
                        peers.get((category, kind), []),
                    ),
                    6,
                )
                for category in entry["categories"]
            }
            aggregate = (
                sum(percentiles.values()) / len(percentiles)
                if percentiles
                else neutral
            )
            unknown_metric = False
        priors[slug] = {
            "metric_status": entry["status"],
            "primary_metric_kind": kind,
            "primary_metric_value": metric_value,
            "metric_year": metric_year,
            "category_percentiles": percentiles,
            "registry_category_percentile": round(aggregate, 6),
            "unknown_metric": unknown_metric,
            "source_url": entry.get("source_url"),
            "source_note": entry.get("source_note"),
        }
    return priors


__all__ = [
    "IMPACT_REGISTRY_FILENAME",
    "JournalImpactRegistryError",
    "builtin_journal_impact_registry",
    "impact_registry_sha256",
    "load_journal_impact_registry",
    "resolve_journal_impact_priors",
    "validate_journal_impact_registry",
]
