from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .journal_catalog import load_journal_registry
from .pages_v5 import _portal_page
from .pages_v15 import build_pages_site as build_v15_pages_site
from .provider_catalog import load_provider_catalogs
from .serialization import json_text

PORTAL_JOURNALS_FILENAME = "portal-journals.json"


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _published_provider_journals(
    catalogs: list[dict[str, Any]],
    root_catalog: dict[str, Any],
    *,
    core_slugs: set[str],
) -> list[dict[str, Any]]:
    latest_slugs = {
        str(item.get("journal_slug") or "")
        for item in (root_catalog.get("latest_editions") or [])
        if isinstance(item, dict) and item.get("journal_slug")
    }
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for catalog in catalogs:
        provider = str(catalog.get("provider") or "")
        publisher = str(catalog.get("publisher") or "")
        for journal in catalog.get("journals") or []:
            if not isinstance(journal, dict):
                continue
            slug = str(journal.get("slug") or "")
            if not slug or slug in core_slugs or slug in seen or slug not in latest_slugs:
                continue
            seen.add(slug)
            row = dict(journal)
            row["provider"] = provider
            row["publisher"] = str(row.get("publisher") or publisher)
            row["origin"] = f"provider:{provider}" if provider else "provider"
            row["status"] = "provider"
            row["categories"] = list(row.get("categories") or [])
            row["aliases"] = list(row.get("aliases") or [])
            rows.append(row)
    return sorted(rows, key=lambda item: str(item.get("name") or "").casefold())


def _build_portal_registry(
    core_registry: dict[str, Any],
    provider_journals: list[dict[str, Any]],
) -> dict[str, Any]:
    core_journals = [
        dict(item)
        for item in (core_registry.get("journals") or [])
        if isinstance(item, dict)
    ]
    projection = {
        "artifact_type": "EvidenceRadar_Editions_PortalJournalProjection",
        "schema_version": "1.0",
        "semantics": (
            "Reader-facing journal projection: core journal registry plus provider journals "
            "that already have a canonical published Edition. Provider discovery-only journals "
            "are excluded."
        ),
        "category_labels": dict(core_registry.get("category_labels") or {}),
        "core_registry_count": len(core_journals),
        "published_provider_journal_count": len(provider_journals),
        "journal_count": len(core_journals) + len(provider_journals),
        "journals": core_journals + provider_journals,
    }
    return projection


def _portal_counts(
    projection: dict[str, Any],
    root_catalog: dict[str, Any],
) -> dict[str, int]:
    journals = [
        item for item in (projection.get("journals") or []) if isinstance(item, dict)
    ]
    slugs = {str(item.get("slug") or "") for item in journals if item.get("slug")}
    latest = [
        item
        for item in (root_catalog.get("latest_editions") or [])
        if isinstance(item, dict) and str(item.get("journal_slug") or "") in slugs
    ]
    published = {str(item.get("journal_slug") or "") for item in latest}
    month_keys = sorted(
        {
            str(item.get("period_key") or "")
            for item in latest
            if item.get("period_kind") == "month" and item.get("period_key")
        },
        reverse=True,
    )
    latest_month = month_keys[0] if month_keys else ""
    month_slugs = {
        str(item.get("journal_slug") or "")
        for item in latest
        if latest_month
        and item.get("period_kind") == "month"
        and str(item.get("period_key") or "") == latest_month
    }
    return {
        "journal_count": len(slugs),
        "published_journal_count": len(published),
        "latest_month_journal_count": len(month_slugs),
    }


def _render_clean_homepage(
    *,
    output: Path,
    projection: dict[str, Any],
) -> None:
    root_catalog = _read_object(output / "index.json")
    search_index = _read_object(output / "search-index.json")
    page = _portal_page(projection, root_catalog, search_index)
    page = page.replace("<span>已登記期刊</span>", "<span>期刊入口</span>")
    page = page.replace("<th>Registry</th>", "<th>來源</th>")
    page = page.replace("Journal Registry JSON", "Core Registry JSON")
    page = page.replace(
        "registered journal catalog + published immutable editions",
        "journal portal + published immutable editions",
    )
    # Downstream acquisition/review/evaluation stages publish dedicated pages.
    # Their legacy homepage injectors key on the exact old main tag; keep the
    # reader portal outside that injection surface so the landing page does not
    # grow into an internal pipeline status board.
    page = page.replace(
        '<main class="shell">',
        '<main class="shell" data-reader-portal>',
        1,
    )
    (output / "index.html").write_text(page, encoding="utf-8")


def restore_clean_homepage(site_dir: Path) -> bool:
    """Restore the reader-facing portal after downstream delivery stages."""

    output = Path(site_dir)
    projection_path = output / PORTAL_JOURNALS_FILENAME
    if not projection_path.is_file():
        return False
    projection = _read_object(projection_path)
    _render_clean_homepage(output=output, projection=projection)
    return True


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
    links = build_v15_pages_site(
        output_dir=output_dir,
        repository=repository,
        editions_root=editions_root,
        archive_root=archive_root,
        catalog_root=catalog_root,
        base_url=base_url,
        require_zh_tw=require_zh_tw,
    )
    if editions_root is None or archive_root is not None or catalog_root is None:
        return links

    output = Path(output_dir)
    core_registry = load_journal_registry(Path(catalog_root))
    root_catalog = _read_object(output / "index.json")
    catalogs = load_provider_catalogs(Path(catalog_root))
    core_slugs = {
        str(item.get("slug") or "")
        for item in (core_registry.get("journals") or [])
        if isinstance(item, dict) and item.get("slug")
    }
    provider_journals = _published_provider_journals(
        catalogs,
        root_catalog,
        core_slugs=core_slugs,
    )
    projection = _build_portal_registry(core_registry, provider_journals)
    counts = _portal_counts(projection, root_catalog)
    (output / PORTAL_JOURNALS_FILENAME).write_text(
        json_text(projection), encoding="utf-8"
    )

    root_catalog["portal_journal_projection"] = {
        "file": PORTAL_JOURNALS_FILENAME,
        "core_registry_count": projection["core_registry_count"],
        "published_provider_journal_count": projection[
            "published_provider_journal_count"
        ],
        **counts,
    }
    (output / "index.json").write_text(json_text(root_catalog), encoding="utf-8")

    public_base = str(links.get("base_url") or "")
    links["portal_journal_projection"] = root_catalog["portal_journal_projection"]
    links["portal_journals_url"] = public_base + PORTAL_JOURNALS_FILENAME
    (output / "links.json").write_text(json_text(links), encoding="utf-8")

    _render_clean_homepage(output=output, projection=projection)
    return links


__all__ = [
    "PORTAL_JOURNALS_FILENAME",
    "build_pages_site",
    "restore_clean_homepage",
]
