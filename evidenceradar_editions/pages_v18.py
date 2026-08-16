from __future__ import annotations

from pathlib import Path
from typing import Any

from .pages_curation_v2 import enhance_revision_pages
from .pages_v16 import build_pages_site as build_v16_pages_site
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
    """Build the current portal, then apply the reader-facing revision renderer.

    The v17 import-time override proved too weak: downstream Pages imports can
    preserve the legacy curation function. This wrapper makes the final output
    contract explicit by re-rendering revision indexes after the complete base
    site exists. Canonical edition JSON and immutable artifact HTML stay intact.
    """

    links = build_v16_pages_site(
        output_dir=output_dir,
        repository=repository,
        editions_root=editions_root,
        archive_root=archive_root,
        catalog_root=catalog_root,
        base_url=base_url,
        require_zh_tw=require_zh_tw,
    )
    if editions_root is None or archive_root is not None:
        return links

    publications = discover_stored_publications(
        Path(editions_root),
        require_zh_tw=require_zh_tw,
    )
    curated_count = enhance_revision_pages(
        output_dir=Path(output_dir),
        publications=publications,
    )
    links["curated_revision_count"] = curated_count
    links["curated_revision_renderer"] = "pages_curation_v2"
    (Path(output_dir) / "links.json").write_text(
        json_text(links),
        encoding="utf-8",
    )
    return links


__all__ = ["build_pages_site"]
