from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .pages_v14 import build_pages_site as build_v14_pages_site
from .provider_catalog import load_provider_catalogs
from .serialization import json_text


def _escape(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _collect_published_provider_editions(
    catalogs: list[dict[str, Any]],
    root_catalog: dict[str, Any],
) -> list[dict[str, Any]]:
    latest_by_slug = {
        str(item.get("journal_slug") or ""): item
        for item in (root_catalog.get("latest_editions") or [])
        if isinstance(item, dict) and item.get("journal_slug")
    }
    published: list[dict[str, Any]] = []
    for catalog in catalogs:
        provider = str(catalog["provider"])
        publisher = str(catalog["publisher"])
        for journal in catalog.get("journals") or []:
            slug = str(journal.get("slug") or "")
            edition = latest_by_slug.get(slug)
            if not slug or edition is None:
                continue
            published.append(
                {
                    "provider": provider,
                    "publisher": publisher,
                    "journal": str(journal.get("name") or edition.get("journal") or slug),
                    "journal_slug": slug,
                    "period_key": edition.get("period_key"),
                    "period_label_zh_tw": edition.get("period_label_zh_tw"),
                    "period_status": edition.get("period_status"),
                    "article_count": edition.get("article_count"),
                    "created_at": edition.get("created_at"),
                    "journal_page": f"journals/{slug}/",
                    "period_page": edition.get("period_url") or f"journals/{slug}/",
                    "revision_page": edition.get("revision_url"),
                }
            )
    return sorted(
        published,
        key=lambda item: (
            str(item.get("publisher") or "").casefold(),
            str(item.get("journal") or "").casefold(),
        ),
    )


def _inject_published_provider_editions(
    path: Path,
    published: list[dict[str, Any]],
) -> None:
    if not published:
        return
    page = path.read_text(encoding="utf-8")
    if "data-provider-editions" in page:
        return
    marker = '<main class="shell">'
    if marker not in page:
        raise ValueError("portal template marker is missing for published provider editions")

    publishers = sorted({str(item["publisher"]) for item in published})
    label = (
        f"已出版 {publishers[0]} Editions"
        if len(publishers) == 1
        else "已出版 provider Editions"
    )
    links = " · ".join(
        f'<a href="{_escape(item["period_page"])}">{_escape(item["journal"])}</a>'
        for item in published
    )
    banner = (
        '<main class="shell"><p data-provider-editions '
        'style="padding:13px 15px;background:#fff8e8;'
        'border:1px solid #e7cf96;border-radius:12px;line-height:1.65">'
        f'<strong>{_escape(label)}（{len(published)}）：</strong> '
        f'{links} '
        '<span style="white-space:nowrap">· <a href="providers/">provider 目錄</a></span>'
        '</p>'
    )
    path.write_text(page.replace(marker, banner, 1), encoding="utf-8")


def _publish_provider_edition_surface(
    *,
    output: Path,
    catalogs: list[dict[str, Any]],
    links: dict[str, Any],
) -> list[dict[str, Any]]:
    if not catalogs:
        return []

    catalog_path = output / "index.json"
    root_catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    published = _collect_published_provider_editions(catalogs, root_catalog)

    provider_index = dict(root_catalog.get("publisher_providers") or {})
    provider_index["published_edition_count"] = len(published)
    provider_index["published_editions"] = published
    root_catalog["publisher_providers"] = provider_index
    catalog_path.write_text(json_text(root_catalog), encoding="utf-8")
    (output / "providers.json").write_text(json_text(provider_index), encoding="utf-8")

    _inject_published_provider_editions(output / "index.html", published)

    links["publisher_providers"] = provider_index
    links["published_provider_edition_count"] = len(published)
    return published


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
    links = build_v14_pages_site(
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

    catalogs = load_provider_catalogs(Path(catalog_root))
    if not catalogs:
        return links

    output = Path(output_dir)
    _publish_provider_edition_surface(
        output=output,
        catalogs=catalogs,
        links=links,
    )
    (output / "links.json").write_text(json_text(links), encoding="utf-8")
    return links


__all__ = ["build_pages_site"]
