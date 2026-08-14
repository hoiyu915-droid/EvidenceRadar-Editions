from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .editorial_shortlist import (
    ABSTRACT_FETCH_PLAN_FILENAME,
    SHORTLIST_INDEX_FILENAME,
    SHORTLIST_PAGE_FILENAME,
    SHORTLIST_POLICY_FILENAME,
    build_editorial_shortlist,
    load_editorial_shortlist_policy,
)
from .editorial_shortlist_render import render_editorial_shortlist_page
from .pages_v11 import build_pages_site as build_v11_pages_site
from .serialization import json_text


def _load_prefetch_audits(output: Path) -> list[dict[str, Any]]:
    audits: list[dict[str, Any]] = []
    for path in sorted((output / "journals").glob("**/triage.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"prefetch triage audit must be a JSON object: {path}")
        audits.append(value)
    return audits


def _inject_portal_banner(path: Path, counts: dict[str, Any]) -> None:
    html = path.read_text(encoding="utf-8")
    if 'href="editorial-shortlist.html"' in html:
        return
    marker = '<main class="shell">'
    if marker not in html:
        raise ValueError("portal template marker is missing")
    banner = (
        '<main class="shell"><p style="padding:13px 15px;background:#edf8ef;'
        'border:1px solid #b8d8bf;border-radius:12px">'
        '<strong>Editorial Shortlist：</strong>'
        f'從 {int(counts.get("canonical_article_count") or 0)} 筆 canonical metadata '
        f'選出 {int(counts.get("fetch_now_count") or 0)} 筆 FETCH_NOW、'
        f'{int(counts.get("hold_reserve_count") or 0)} 筆 HOLD_RESERVE；'
        '只有 FETCH_NOW 進入 bounded abstract fetch plan。'
        ' <a href="editorial-shortlist.html">開啟 shortlist</a></p>'
    )
    path.write_text(html.replace(marker, banner, 1), encoding="utf-8")


def _inject_revision_link(path: Path) -> None:
    html = path.read_text(encoding="utf-8")
    if 'href="shortlist.json"' in html:
        return
    marker = '<a href="triage.json">triage audit</a>'
    if marker in html:
        html = html.replace(
            marker,
            marker + '<a href="shortlist.json">editorial shortlist audit</a>',
            1,
        )
    else:
        fallback = "</main>"
        if fallback not in html:
            raise ValueError(f"revision template marker is missing: {path}")
        html = html.replace(
            fallback,
            '<p><a href="shortlist.json">editorial shortlist audit</a></p></main>',
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
    links = build_v11_pages_site(
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
    policy = load_editorial_shortlist_policy(Path(catalog_root))
    audits = _load_prefetch_audits(output)
    shortlist, edition_artifacts = build_editorial_shortlist(
        audits,
        policy=policy,
    )

    (output / SHORTLIST_INDEX_FILENAME).write_text(
        json_text(shortlist),
        encoding="utf-8",
    )
    (output / SHORTLIST_PAGE_FILENAME).write_text(
        render_editorial_shortlist_page(shortlist),
        encoding="utf-8",
    )
    (output / ABSTRACT_FETCH_PLAN_FILENAME).write_text(
        json_text(shortlist["abstract_fetch_plan"]),
        encoding="utf-8",
    )
    (output / SHORTLIST_POLICY_FILENAME).write_text(
        json_text(policy),
        encoding="utf-8",
    )

    written_editions = 0
    for relative_path, artifact in edition_artifacts.items():
        revision_dir = output / relative_path
        if not revision_dir.is_dir():
            raise ValueError(
                f"editorial shortlist revision directory is missing: {relative_path}"
            )
        (revision_dir / "shortlist.json").write_text(
            json_text(artifact),
            encoding="utf-8",
        )
        _inject_revision_link(revision_dir / "index.html")
        written_editions += 1

    counts = shortlist.get("counts") or {}
    summary = {
        "semantics": shortlist.get("semantics"),
        "scientific_boundary": shortlist.get("scientific_boundary"),
        "policy_id": shortlist.get("policy_id"),
        "policy_sha256": shortlist.get("policy_sha256"),
        "source_prefetch_digest": shortlist.get("source_prefetch_digest"),
        "shortlist_binding_sha256": shortlist.get("shortlist_binding_sha256"),
        "canonical_article_count": counts.get("canonical_article_count"),
        "fetch_now_target": counts.get("fetch_now_target"),
        "fetch_now_count": counts.get("fetch_now_count"),
        "hold_reserve_target": counts.get("hold_reserve_target"),
        "hold_reserve_count": counts.get("hold_reserve_count"),
        "catalog_only_count": counts.get("catalog_only_count"),
        "integrity_attention_count": counts.get("integrity_attention_count"),
        "edition_audit_count": written_editions,
        "index_file": SHORTLIST_INDEX_FILENAME,
        "page_file": SHORTLIST_PAGE_FILENAME,
        "policy_file": SHORTLIST_POLICY_FILENAME,
        "abstract_fetch_plan_file": ABSTRACT_FETCH_PLAN_FILENAME,
    }

    catalog_path = output / "index.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["editorial_shortlist"] = summary
    catalog_path.write_text(json_text(catalog), encoding="utf-8")

    _inject_portal_banner(output / "index.html", counts)

    public_base = str(links.get("base_url") or "")
    links["editorial_shortlist"] = summary
    links["editorial_shortlist_url"] = public_base + SHORTLIST_PAGE_FILENAME
    links["editorial_shortlist_index_url"] = (
        public_base + SHORTLIST_INDEX_FILENAME
    )
    links["editorial_shortlist_policy_url"] = (
        public_base + SHORTLIST_POLICY_FILENAME
    )
    links["abstract_fetch_plan_url"] = (
        public_base + ABSTRACT_FETCH_PLAN_FILENAME
    )
    (output / "links.json").write_text(json_text(links), encoding="utf-8")
    return links


__all__ = ["build_pages_site"]
