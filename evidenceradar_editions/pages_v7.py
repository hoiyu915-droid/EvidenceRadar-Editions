from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .journal_catalog_v2 import load_journal_registry
from .pages_v6 import build_pages_site as build_v6_pages_site
from .pages_volume import enhance_revision_pages
from .processing_policy import POLICY_FILENAME
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
    links = build_v6_pages_site(
        output_dir=output_dir,
        repository=repository,
        editions_root=editions_root,
        archive_root=archive_root,
        catalog_root=catalog_root,
        base_url=base_url,
        require_zh_tw=require_zh_tw,
    )

    # v0.2 archive compatibility does not expose canonical v3 publications to
    # the volume-aware projection layer.
    if editions_root is None or archive_root is not None:
        return links

    publications = discover_stored_publications(
        Path(editions_root),
        require_zh_tw=require_zh_tw,
    )
    resolved_catalog_root = Path(catalog_root or "catalog")
    projection = enhance_revision_pages(
        output_dir=Path(output_dir),
        publications=publications,
        catalog_root=resolved_catalog_root,
    )
    links["volume_projection"] = projection

    output = Path(output_dir)
    policy_source = resolved_catalog_root / POLICY_FILENAME
    enriched_registry = load_journal_registry(resolved_catalog_root)
    (output / "journals.json").write_text(
        json_text(enriched_registry),
        encoding="utf-8",
    )
    links["resolved_processing_policy_count"] = len(
        enriched_registry.get("journals") or []
    )
    if policy_source.is_file():
        shutil.copyfile(policy_source, output / POLICY_FILENAME)
        public_base = str(links.get("base_url") or "")
        links["processing_policies_url"] = public_base + POLICY_FILENAME

    index_path = output / "index.json"
    if index_path.is_file():
        catalog = json.loads(index_path.read_text(encoding="utf-8"))
        catalog["volume_projection"] = projection
        catalog["journal_registry"] = enriched_registry
        if policy_source.is_file():
            catalog["processing_policy_file"] = POLICY_FILENAME
        index_path.write_text(json_text(catalog), encoding="utf-8")

    links_path = output / "links.json"
    links_path.write_text(json_text(links), encoding="utf-8")
    return links
