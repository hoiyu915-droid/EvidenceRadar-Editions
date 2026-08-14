from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .journal_catalog_v2 import load_journal_registry
from .pages_search import build_projected_search_index
from .pages_v5 import _portal_page
from .pages_v7 import build_pages_site as build_v7_pages_site
from .serialization import json_text
from .store_v3 import discover_stored_publications


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
    links = build_v7_pages_site(
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
    resolved_catalog_root = Path(catalog_root)
    publications = discover_stored_publications(
        Path(editions_root),
        require_zh_tw=require_zh_tw,
    )
    search_index = build_projected_search_index(
        publications,
        catalog_root=resolved_catalog_root,
    )
    search_path = output / "search-index.json"
    search_path.write_text(json_text(search_index), encoding="utf-8")

    catalog_path = output / "index.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    projection_summary = {
        "semantics": search_index["semantics"],
        "canonical_article_count": search_index["canonical_article_count"],
        "projected_article_count": search_index["projected_article_count"],
        "omitted_article_count": search_index["omitted_article_count"],
        "processing_mode_counts": search_index["processing_mode_counts"],
        "search_index_file": "search-index.json",
    }
    catalog["search_projection"] = projection_summary
    catalog["search_index_article_count"] = search_index["article_count"]
    catalog_path.write_text(json_text(catalog), encoding="utf-8")

    registry = load_journal_registry(resolved_catalog_root)
    (output / "index.html").write_text(
        _portal_page(registry, catalog, search_index),
        encoding="utf-8",
    )

    public_base = str(links.get("base_url") or "")
    links["search_index_url"] = public_base + "search-index.json"
    links["search_projection"] = projection_summary
    links["search_index_article_count"] = search_index["article_count"]
    (output / "links.json").write_text(json_text(links), encoding="utf-8")
    return links
