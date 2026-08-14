from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import pages_v12
from .editorial_shortlist_v2 import (
    build_editorial_shortlist_v2,
    load_editorial_shortlist_policy_v2,
)
from .journal_impact import (
    IMPACT_REGISTRY_FILENAME,
    impact_registry_sha256,
    load_journal_impact_registry,
)
from .serialization import json_text


def build_pages_site(
    *,
    output_dir: Path,
    repository: str,
    editions_root: Path | None = None,
    archive_root: Path | None = None,
    catalog_root: Path | None = None,
    base_url: str | None = None,
    require_zh_tw: bool = True,
) -> dict[str, Any]:
    """Build Pages with the public metric-aware Editorial Shortlist v2.

    ``pages_v12`` owns the established shortlist delivery surface. This wrapper
    replaces only the selector and policy loader for one build, passes the exact
    resolved impact registry into the selector, restores module globals, and
    then publishes the normalized registry plus its digest in the Pages catalog.
    """

    resolved_catalog_root = Path(catalog_root or "catalog")
    impact_registry = load_journal_impact_registry(resolved_catalog_root)

    def build_v2(audits, *, policy=None, generated_at=None):
        return build_editorial_shortlist_v2(
            audits,
            policy=policy,
            impact_registry=impact_registry,
            generated_at=generated_at,
        )

    original_builder = pages_v12.build_editorial_shortlist
    original_loader = pages_v12.load_editorial_shortlist_policy
    pages_v12.build_editorial_shortlist = build_v2
    pages_v12.load_editorial_shortlist_policy = load_editorial_shortlist_policy_v2
    try:
        links = pages_v12.build_pages_site(
            output_dir=output_dir,
            repository=repository,
            editions_root=editions_root,
            archive_root=archive_root,
            catalog_root=catalog_root,
            base_url=base_url,
            require_zh_tw=require_zh_tw,
        )
    finally:
        pages_v12.build_editorial_shortlist = original_builder
        pages_v12.load_editorial_shortlist_policy = original_loader

    if editions_root is None or archive_root is not None or catalog_root is None:
        return links

    output = Path(output_dir)
    registry_digest = impact_registry_sha256(impact_registry)
    (output / IMPACT_REGISTRY_FILENAME).write_text(
        json_text(impact_registry),
        encoding="utf-8",
    )

    shortlist_path = output / "editorial-shortlist.json"
    shortlist = json.loads(shortlist_path.read_text(encoding="utf-8"))
    if shortlist.get("impact_registry_sha256") != registry_digest:
        raise ValueError("editorial shortlist impact registry binding mismatch")

    metric_coverage = dict(shortlist.get("metric_coverage") or {})
    registry_summary = {
        "artifact_type": impact_registry.get("artifact_type"),
        "schema_version": impact_registry.get("schema_version"),
        "observed_at": impact_registry.get("observed_at"),
        "semantics": impact_registry.get("semantics"),
        "metric_preference": list(impact_registry.get("metric_preference") or []),
        "normalization": dict(impact_registry.get("normalization") or {}),
        "journal_count": len(impact_registry.get("journals") or {}),
        "verified_metric_count": sum(
            bool((item or {}).get("metrics"))
            for item in (impact_registry.get("journals") or {}).values()
        ),
        "sha256": registry_digest,
        "file": IMPACT_REGISTRY_FILENAME,
        "metric_coverage": metric_coverage,
    }

    catalog_path = output / "index.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["journal_impact_registry"] = registry_summary
    shortlist_summary = catalog.setdefault("editorial_shortlist", {})
    shortlist_summary["impact_registry_file"] = IMPACT_REGISTRY_FILENAME
    shortlist_summary["impact_registry_sha256"] = registry_digest
    shortlist_summary["metric_coverage"] = metric_coverage
    shortlist_summary["selection_algorithm"] = shortlist.get("selection_algorithm")
    catalog_path.write_text(json_text(catalog), encoding="utf-8")

    public_base = str(links.get("base_url") or "")
    links["journal_impact_registry"] = registry_summary
    links["journal_impact_registry_url"] = public_base + IMPACT_REGISTRY_FILENAME
    shortlist_link_summary = links.setdefault("editorial_shortlist", {})
    shortlist_link_summary["impact_registry_file"] = IMPACT_REGISTRY_FILENAME
    shortlist_link_summary["impact_registry_sha256"] = registry_digest
    shortlist_link_summary["metric_coverage"] = metric_coverage
    shortlist_link_summary["selection_algorithm"] = shortlist.get(
        "selection_algorithm"
    )
    (output / "links.json").write_text(json_text(links), encoding="utf-8")
    return links


__all__ = ["build_pages_site"]
