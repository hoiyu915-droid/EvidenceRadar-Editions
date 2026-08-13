from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .bundle import artifact_names
from .pages_v3 import build_pages_site as build_legacy_pages_site
from .render import render_html
from .serialization import json_text
from .store_v3 import discover_stored_publications


def _materialize_legacy_bundle(publication: Any, archive_root: Path) -> None:
    """Materialize a validated v0.2-style archive only inside the build workspace."""

    target = (
        archive_root
        / "journals"
        / publication.journal_slug
        / publication.period_key
        / f"r{publication.revision:02d}"
    )
    target.mkdir(parents=True, exist_ok=False)
    edition = publication.edition
    manifest = publication.manifest
    names = artifact_names(edition)
    html_text = render_html(edition)

    source_json = publication.directory / "edition.json"
    source_manifest = publication.directory / "manifest.json"
    shutil.copyfile(source_json, target / names["edition_json"])
    shutil.copyfile(source_manifest, target / names["manifest_json"])
    (target / names["report_html"]).write_text(html_text, encoding="utf-8")
    shutil.copyfile(source_json, target / "edition.json")
    shutil.copyfile(source_manifest, target / "manifest.json")
    (target / "index.html").write_text(html_text, encoding="utf-8")
    (target / "publication.json").write_text(
        json_text(
            {
                "schema_version": "3.0",
                "artifact_type": "EvidenceRadar_Editions_EphemeralPagesEntry",
                "publication_id": manifest.get("publication_id"),
                "journal_slug": publication.journal_slug,
                "period_key": publication.period_key,
                "revision": publication.revision,
                "generated_from": "canonical_editions_store",
                "files": {
                    "index_html": "index.html",
                    "edition_json": "edition.json",
                    "manifest_json": "manifest.json",
                    "download_html": names["report_html"],
                    "download_json": names["edition_json"],
                    "download_manifest": names["manifest_json"],
                },
            }
        ),
        encoding="utf-8",
    )


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
    """Build Pages from v3 canonical storage.

    `archive_root` is retained only for v0.2 compatibility. Production uses
    `editions_root`; HTML is rendered into a temporary workspace and never
    stored in the canonical Git tree.
    """

    if editions_root is not None and archive_root is not None:
        raise ValueError("pass editions_root or archive_root, not both")
    if editions_root is None and archive_root is not None:
        return build_legacy_pages_site(
            archive_root=archive_root,
            output_dir=output_dir,
            repository=repository,
            base_url=base_url,
            require_zh_tw=require_zh_tw,
        )

    source = Path(editions_root or "editions")
    publications = discover_stored_publications(source, require_zh_tw=require_zh_tw)
    with tempfile.TemporaryDirectory(prefix="evidenceradar-editions-pages-") as tmp:
        temp_archive = Path(tmp) / "archive"
        temp_archive.mkdir()
        for publication in publications:
            _materialize_legacy_bundle(publication, temp_archive)
        links = build_legacy_pages_site(
            archive_root=temp_archive,
            output_dir=output_dir,
            repository=repository,
            base_url=base_url,
            require_zh_tw=require_zh_tw,
        )

    catalog_path = Path(output_dir) / "index.json"
    if catalog_path.is_file():
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        catalog["storage_semantics"] = "sharded_canonical_json_store_v3"
        if catalog_root is not None:
            registry_path = Path(catalog_root) / "journals.json"
            if registry_path.is_file():
                registry = json.loads(registry_path.read_text(encoding="utf-8"))
                catalog["journal_registry"] = registry
        catalog_path.write_text(json_text(catalog), encoding="utf-8")
    return links
