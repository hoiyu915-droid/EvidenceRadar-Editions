from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from .journal_catalog import (
    get_journal as get_legacy_journal,
    journals_by_slug,
    list_journals as list_legacy_journals,
    load_journal_registry as load_legacy_registry,
    spec_defaults as legacy_spec_defaults,
)
from .processing_policy import (
    ALLOWED_PROCESSING_MODES,
    load_processing_policy_catalog,
    policy_for_slug,
    validate_policy_journal_references,
)


def _with_policy(
    journal: dict[str, Any],
    *,
    catalog_root: Path | str,
    policy_catalog: dict[str, Any],
) -> dict[str, Any]:
    item = deepcopy(journal)
    item["processing_policy"] = policy_for_slug(
        str(item["slug"]),
        catalog_root=catalog_root,
        catalog=policy_catalog,
    ).to_dict()
    return item


def load_journal_registry(
    catalog_root: Path | str = Path("catalog"),
) -> dict[str, Any]:
    registry = load_legacy_registry(catalog_root)
    policy_catalog = load_processing_policy_catalog(catalog_root)
    validate_policy_journal_references(
        (str(item["slug"]) for item in registry.get("journals") or []),
        catalog_root=catalog_root,
        catalog=policy_catalog,
    )
    enriched = deepcopy(registry)
    enriched["journals"] = [
        _with_policy(
            item,
            catalog_root=catalog_root,
            policy_catalog=policy_catalog,
        )
        for item in registry.get("journals") or []
    ]
    enriched["processing_policy_catalog"] = {
        "artifact_type": policy_catalog["artifact_type"],
        "schema_version": policy_catalog["schema_version"],
        "default_mode": policy_catalog["defaults"]["mode"],
        "journal_override_count": len(policy_catalog.get("journals") or {}),
        "file": "processing-policies.json",
    }
    return enriched


def get_journal(
    slug: str,
    *,
    catalog_root: Path | str = Path("catalog"),
    require_enabled: bool = False,
) -> dict[str, Any]:
    journal = get_legacy_journal(
        slug,
        catalog_root=catalog_root,
        require_enabled=require_enabled,
    )
    policy_catalog = load_processing_policy_catalog(catalog_root)
    validate_policy_journal_references(
        journals_by_slug(load_legacy_registry(catalog_root)),
        catalog_root=catalog_root,
        catalog=policy_catalog,
    )
    return _with_policy(
        journal,
        catalog_root=catalog_root,
        policy_catalog=policy_catalog,
    )


def list_journals(
    *,
    catalog_root: Path | str = Path("catalog"),
    status: str | None = None,
    category: str | None = None,
    publisher: str | None = None,
    enabled_only: bool = False,
    processing_mode: str | None = None,
) -> list[dict[str, Any]]:
    wanted_mode = processing_mode.upper() if processing_mode else None
    if wanted_mode and wanted_mode not in ALLOWED_PROCESSING_MODES:
        raise ValueError(
            f"processing_mode must be one of {ALLOWED_PROCESSING_MODES}"
        )
    policy_catalog = load_processing_policy_catalog(catalog_root)
    registry = load_legacy_registry(catalog_root)
    validate_policy_journal_references(
        journals_by_slug(registry),
        catalog_root=catalog_root,
        catalog=policy_catalog,
    )
    items = list_legacy_journals(
        catalog_root=catalog_root,
        status=status,
        category=category,
        publisher=publisher,
        enabled_only=enabled_only,
    )
    enriched = [
        _with_policy(
            item,
            catalog_root=catalog_root,
            policy_catalog=policy_catalog,
        )
        for item in items
    ]
    if wanted_mode:
        enriched = [
            item
            for item in enriched
            if (item.get("processing_policy") or {}).get("configured_mode")
            == wanted_mode
        ]
    return enriched


def spec_defaults(journal: dict[str, Any]) -> dict[str, Any]:
    defaults = legacy_spec_defaults(journal)
    policy = journal.get("processing_policy") or {}
    if policy.get("source_record_limit"):
        defaults["max_records"] = int(policy["source_record_limit"])
    defaults["processing_policy"] = policy
    return defaults
