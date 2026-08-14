from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?$")


def load_journal_registry(catalog_root: Path | str = Path("catalog")) -> dict[str, Any]:
    path = Path(catalog_root) / "journals.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("journal registry must be a JSON object")
    journals = value.get("journals")
    if not isinstance(journals, list):
        raise ValueError("journal registry journals must be a list")
    seen: set[str] = set()
    for index, raw in enumerate(journals):
        if not isinstance(raw, dict):
            raise ValueError(f"journal registry entry {index} must be an object")
        name = str(raw.get("name") or "").strip()
        slug = str(raw.get("slug") or "").strip()
        if not name:
            raise ValueError(f"journal registry entry {index} lacks name")
        if not _SLUG_RE.fullmatch(slug):
            raise ValueError(f"journal registry entry {index} has unsafe slug: {slug!r}")
        if slug in seen:
            raise ValueError(f"journal registry contains duplicate slug: {slug}")
        seen.add(slug)
        status = str(raw.get("status") or "active")
        if status not in {"active", "planned", "retired"}:
            raise ValueError(f"journal registry entry {slug} has unsupported status: {status}")
        categories = raw.get("categories") or []
        if not isinstance(categories, list) or not all(isinstance(v, str) and v for v in categories):
            raise ValueError(f"journal registry entry {slug} has invalid categories")
        sources = raw.get("sources") or []
        if not isinstance(sources, list) or not all(isinstance(v, str) and v for v in sources):
            raise ValueError(f"journal registry entry {slug} has invalid sources")
    declared = value.get("journal_count")
    if declared is not None and int(declared) != len(journals):
        raise ValueError("journal registry journal_count does not match journals")
    return value


def journals_by_slug(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["slug"]): item for item in registry.get("journals") or []}


def get_journal(
    slug: str,
    *,
    catalog_root: Path | str = Path("catalog"),
    require_enabled: bool = False,
) -> dict[str, Any]:
    registry = load_journal_registry(catalog_root)
    journal = journals_by_slug(registry).get(slug)
    if journal is None:
        raise KeyError(f"journal is not registered: {slug}")
    if require_enabled and not bool(journal.get("enabled", True)):
        raise ValueError(f"journal is registered but not enabled: {slug}")
    return journal


def list_journals(
    *,
    catalog_root: Path | str = Path("catalog"),
    status: str | None = None,
    category: str | None = None,
    publisher: str | None = None,
    enabled_only: bool = False,
) -> list[dict[str, Any]]:
    registry = load_journal_registry(catalog_root)
    items: list[dict[str, Any]] = []
    publisher_key = publisher.casefold() if publisher else None
    for journal in registry.get("journals") or []:
        if status and str(journal.get("status") or "") != status:
            continue
        if category and category not in (journal.get("categories") or []):
            continue
        if publisher_key and str(journal.get("publisher") or "").casefold() != publisher_key:
            continue
        if enabled_only and not bool(journal.get("enabled", True)):
            continue
        items.append(journal)
    items.sort(key=lambda value: str(value.get("name") or "").casefold())
    return items


def spec_defaults(journal: dict[str, Any]) -> dict[str, Any]:
    return {
        "journal": str(journal["name"]),
        "issn": journal.get("issn"),
        "slug": str(journal["slug"]),
        "sources": [str(value) for value in (journal.get("sources") or [])],
    }
