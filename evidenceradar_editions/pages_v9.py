from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .pages_v8 import build_pages_site as build_v8_pages_site
from .prefetch_triage import build_prefetch_triage
from .serialization import json_text
from .store_v3 import discover_stored_publications
from .triage_policy import TRIAGE_POLICY_FILENAME
from .triage_policy_defaults import load_triage_policy
from .triage_render import render_prefetch_triage_page


def _inject_portal_link(path: Path, counts: dict[str, Any]) -> None:
    html = path.read_text(encoding="utf-8")
    marker = '<main class="shell">'
    if marker not in html:
        raise ValueError("portal template marker is missing")
    banner = (
        '<main class="shell"><p style="padding:13px 15px;background:#eef4ff;'
        'border:1px solid #bfd0ff;border-radius:12px">'
        '<strong>Metadata 預抓候選：</strong>'
        f'目前從 {int(counts.get("canonical_article_count") or 0)} 筆 canonical metadata '
        f'分出 {int(counts.get("fetch_candidate_count") or 0)} 筆建議 fetch、'
        f'{int(counts.get("integrity_review_count") or 0)} 筆完整性維護與 '
        f'{int(counts.get("reserve_count") or 0)} 筆候補。'
        ' <a href="prefetch-triage.html">開啟可稽核候選頁</a></p>'
    )
    path.write_text(html.replace(marker, banner, 1), encoding="utf-8")


def _inject_revision_link(path: Path) -> None:
    html = path.read_text(encoding="utf-8")
    marker = '<a href="browse.json">browse JSON</a>'
    link = marker + '<a href="triage.json">triage audit</a>'
    if marker in html and 'href="triage.json"' not in html:
        html = html.replace(marker, link, 1)
    elif 'href="triage.json"' not in html:
        fallback = "</main>"
        if fallback not in html:
            raise ValueError(f"revision template marker is missing: {path}")
        html = html.replace(
            fallback,
            '<p><a href="triage.json">metadata pre-fetch triage audit</a></p></main>',
            1,
        )
    path.write_text(html, encoding="utf-8")


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
    links = build_v8_pages_site(
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
    triage_index, edition_artifacts = build_prefetch_triage(
        publications,
        catalog_root=resolved_catalog_root,
    )

    index_name = "prefetch-triage-index.json"
    page_name = "prefetch-triage.html"
    (output / index_name).write_text(json_text(triage_index), encoding="utf-8")
    (output / page_name).write_text(
        render_prefetch_triage_page(triage_index),
        encoding="utf-8",
    )

    # Publish the exact policy object that was actually resolved. Lightweight
    # temporary catalogs may omit the optional file and use the validated
    # built-in default; their Pages output remains self-describing instead of
    # failing or silently disabling triage.
    resolved_triage_policy = load_triage_policy(resolved_catalog_root)
    (output / TRIAGE_POLICY_FILENAME).write_text(
        json_text(resolved_triage_policy),
        encoding="utf-8",
    )

    written_editions = 0
    for relative_path, artifact in edition_artifacts.items():
        revision_dir = output / relative_path
        if not revision_dir.is_dir():
            raise ValueError(f"triage revision directory is missing: {relative_path}")
        (revision_dir / "triage.json").write_text(
            json_text(artifact),
            encoding="utf-8",
        )
        _inject_revision_link(revision_dir / "index.html")
        written_editions += 1

    counts = triage_index.get("counts") or {}
    summary = {
        "semantics": triage_index.get("semantics"),
        "canonical_article_count": counts.get("canonical_article_count"),
        "actionable_count": counts.get("actionable_count"),
        "fetch_candidate_count": counts.get("fetch_candidate_count"),
        "integrity_review_count": counts.get("integrity_review_count"),
        "reserve_count": counts.get("reserve_count"),
        "catalog_only_count": counts.get("catalog_only_count"),
        "published_index_count": counts.get("published_index_count"),
        "edition_audit_count": written_editions,
        "index_file": index_name,
        "page_file": page_name,
        "policy_file": TRIAGE_POLICY_FILENAME,
    }

    catalog_path = output / "index.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["prefetch_triage"] = summary
    catalog_path.write_text(json_text(catalog), encoding="utf-8")

    _inject_portal_link(output / "index.html", counts)

    public_base = str(links.get("base_url") or "")
    links["prefetch_triage"] = summary
    links["prefetch_triage_url"] = public_base + page_name
    links["prefetch_triage_index_url"] = public_base + index_name
    links["prefetch_triage_policy_url"] = public_base + TRIAGE_POLICY_FILENAME
    (output / "links.json").write_text(json_text(links), encoding="utf-8")
    return links
