from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_PROVIDER_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?$")


class ProviderCatalogError(ValueError):
    """Raised when a provider snapshot is malformed."""


def _nonempty(value: Any, *, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ProviderCatalogError(f"provider catalog field is required: {field}")
    return text


def validate_provider_catalog(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProviderCatalogError("provider catalog must be a JSON object")
    if value.get("artifact_type") != "EvidenceRadar_Editions_ProviderCatalog":
        raise ProviderCatalogError("unexpected provider catalog artifact_type")

    provider = _nonempty(value.get("provider"), field="provider").casefold()
    if not _PROVIDER_RE.fullmatch(provider):
        raise ProviderCatalogError(f"unsafe provider id: {provider!r}")
    publisher = _nonempty(value.get("publisher"), field="publisher")
    scope = _nonempty(value.get("scope"), field="scope")
    source_url = _nonempty(value.get("source_url"), field="source_url")
    observed_at = _nonempty(value.get("observed_at"), field="observed_at")

    raw_journals = value.get("journals")
    if not isinstance(raw_journals, list):
        raise ProviderCatalogError("provider catalog journals must be a list")

    journals: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_journals):
        if not isinstance(raw, dict):
            raise ProviderCatalogError(f"provider journal {index} must be an object")
        slug = _nonempty(raw.get("slug"), field=f"journals[{index}].slug").casefold()
        if not _SLUG_RE.fullmatch(slug):
            raise ProviderCatalogError(f"unsafe provider journal slug: {slug!r}")
        if slug in seen:
            raise ProviderCatalogError(f"duplicate provider journal slug: {slug}")
        seen.add(slug)
        name = _nonempty(raw.get("name"), field=f"journals[{index}].name")
        journal_provider = str(raw.get("provider") or provider).strip().casefold()
        if journal_provider != provider:
            raise ProviderCatalogError(
                f"provider journal {slug} belongs to {journal_provider!r}, expected {provider!r}"
            )
        sources = raw.get("sources") or []
        if not isinstance(sources, list) or not all(
            isinstance(item, str) and item.strip() for item in sources
        ):
            raise ProviderCatalogError(f"provider journal {slug} has invalid sources")
        journals.append(
            {
                **raw,
                "provider": provider,
                "publisher": str(raw.get("publisher") or publisher).strip(),
                "name": name,
                "slug": slug,
                "sources": [str(item).strip() for item in sources],
            }
        )

    declared = value.get("journal_count")
    if declared is not None:
        try:
            declared_count = int(declared)
        except (TypeError, ValueError) as exc:
            raise ProviderCatalogError("provider catalog journal_count must be an integer") from exc
        if declared_count != len(journals):
            raise ProviderCatalogError(
                "provider catalog journal_count does not match journals"
            )

    journals.sort(key=lambda item: str(item["name"]).casefold())
    return {
        **value,
        "schema_version": str(value.get("schema_version") or "1.0"),
        "provider": provider,
        "publisher": publisher,
        "scope": scope,
        "source_url": source_url,
        "observed_at": observed_at,
        "journal_count": len(journals),
        "journals": journals,
    }


def load_provider_catalog(path: Path | str) -> dict[str, Any]:
    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProviderCatalogError(f"cannot load provider catalog {source}: {exc}") from exc
    return validate_provider_catalog(value)


def load_provider_catalogs(
    catalog_root: Path | str = Path("catalog"),
) -> list[dict[str, Any]]:
    root = Path(catalog_root) / "providers"
    if not root.is_dir():
        return []
    catalogs = [load_provider_catalog(path) for path in sorted(root.glob("*.json"))]
    providers = [str(item["provider"]) for item in catalogs]
    if len(providers) != len(set(providers)):
        raise ProviderCatalogError("duplicate provider ids across provider catalog files")
    catalogs.sort(key=lambda item: str(item["publisher"]).casefold())
    return catalogs


__all__ = [
    "ProviderCatalogError",
    "load_provider_catalog",
    "load_provider_catalogs",
    "validate_provider_catalog",
]
