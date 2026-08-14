from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from .journal_catalog_v2 import load_journal_registry
from .metadata_triage import (
    POLICY_FILENAME as TRIAGE_POLICY_FILENAME,
    load_metadata_triage_policy,
)
from .pages_v8 import build_pages_site as build_base_pages_site
from .processing_policy import load_processing_policy_catalog
from .serialization import json_text
from .store_v3 import discover_stored_publications
from .triage_index import build_metadata_triage_indices
from .triage_pages import write_triaged_revision_pages
from .triage_render import render_metadata_triage_dashboard
from .utils import utc_now_iso


def _patch_portal_home(html: str, summary: dict[str, Any]) -> str:
    marker = '<main class="shell">'
    if marker not in html:
        raise ValueError("Pages portal main marker is missing")
    canonical = int(summary.get("canonical_article_count") or 0)
    priority = int(summary.get("priority_candidate_count") or 0)
    projected = int(summary.get("default_projected_article_count") or 0)
    omitted = int(summary.get("default_omitted_article_count") or 0)
    panel = (
        '<section style="margin:0 0 16px;padding:15px 17px;background:#fff8db;'
        'border:1px solid #ecd887;border-radius:14px;color:#5d4a00">'
        '<strong>Metadata triage 已套用：</strong>'
        f'目前 {canonical:,} 筆 canonical records 全部完成 title／bibliographic '
        f'metadata 分流；{priority:,} 筆為 ALERT／HIGH。'
        f'預設 browse/search 載入 {projected:,} 筆，另有 {omitted:,} 筆只從'
        '預設 payload 省略、未從 canonical archive 刪除。'
        ' <a href="metadata-triage/"><strong>開啟全站 triage dashboard →</strong></a>'
        '</section>'
    )
    return html.replace(marker, marker + panel, 1)


def build_triage_delivery(
    *,
    output_dir: Path,
    repository: str,
    editions_root: Path = Path("editions"),
    catalog_root: Path = Path("catalog"),
    base_url: str | None = None,
    require_zh_tw: bool = True,
) -> dict[str, Any]:
    """Build normal Pages, then replace its browsing layer with metadata triage.

    Canonical editions are read-only inputs. The post-processing layer rewrites
    only the generated Pages workspace: per-revision browse JSON/HTML, global
    search, the on-demand all-record triage index, and public provenance links.
    """

    links = build_base_pages_site(
        output_dir=output_dir,
        repository=repository,
        editions_root=editions_root,
        catalog_root=catalog_root,
        base_url=base_url,
        require_zh_tw=require_zh_tw,
    )
    publications = discover_stored_publications(
        editions_root,
        require_zh_tw=require_zh_tw,
    )
    processing_catalog = load_processing_policy_catalog(catalog_root)
    triage_policy = load_metadata_triage_policy(catalog_root)
    registry = load_journal_registry(catalog_root)
    registry_by_slug = {
        str(item.get("slug")): item
        for item in (registry.get("journals") or [])
        if isinstance(item, dict) and item.get("slug")
    }

    revision_stats, triage_results = write_triaged_revision_pages(
        output_dir=output_dir,
        publications=publications,
        catalog_root=catalog_root,
        processing_catalog=processing_catalog,
        triage_policy=triage_policy,
    )
    generated_at = utc_now_iso()
    triage_index, search_index = build_metadata_triage_indices(
        publications,
        triage_results=triage_results,
        registry_by_slug=registry_by_slug,
        policy_id=str(triage_policy["policy_id"]),
        generated_at=generated_at,
    )

    output = Path(output_dir)
    (output / "metadata-triage.json").write_text(
        json_text(triage_index), encoding="utf-8"
    )
    (output / "search-index.json").write_text(
        json_text(search_index), encoding="utf-8"
    )
    shutil.copyfile(
        Path(catalog_root) / TRIAGE_POLICY_FILENAME,
        output / TRIAGE_POLICY_FILENAME,
    )
    triage_dir = output / "metadata-triage"
    triage_dir.mkdir(parents=True, exist_ok=True)
    (triage_dir / "index.html").write_text(
        render_metadata_triage_dashboard(triage_index),
        encoding="utf-8",
    )

    summary = {
        "policy_id": triage_index["policy_id"],
        "basis": triage_index["basis"],
        "canonical_article_count": triage_index["canonical_article_count"],
        "priority_candidate_count": triage_index["priority_candidate_count"],
        "default_projected_article_count": triage_index[
            "default_projected_article_count"
        ],
        "default_omitted_article_count": triage_index[
            "default_omitted_article_count"
        ],
        "processing_mode_counts": triage_index["processing_mode_counts"],
        "canonical_triage_counts": triage_index["canonical_triage_counts"],
        "projected_triage_counts": triage_index["projected_triage_counts"],
        "metadata_triage_file": "metadata-triage.json",
        "metadata_triage_dashboard": "metadata-triage/",
        "metadata_triage_policy_file": TRIAGE_POLICY_FILENAME,
        "revision_projection": revision_stats,
        "semantics": (
            "All latest-revision canonical records are triaged from title and "
            "bibliographic metadata. The default payload is bounded, but canonical "
            "edition JSON remains complete and immutable."
        ),
    }
    search_projection = {
        "semantics": search_index["semantics"],
        "canonical_article_count": search_index["canonical_article_count"],
        "priority_candidate_count": search_index["priority_candidate_count"],
        "projected_article_count": search_index["projected_article_count"],
        "omitted_article_count": search_index["omitted_article_count"],
        "processing_mode_counts": search_index["processing_mode_counts"],
        "metadata_triage_policy_id": search_index[
            "metadata_triage_policy_id"
        ],
        "search_index_file": "search-index.json",
    }

    catalog_path = output / "index.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["metadata_triage_summary"] = summary
    catalog["search_index_article_count"] = search_index["article_count"]
    catalog["search_projection"] = search_projection
    catalog_path.write_text(json_text(catalog), encoding="utf-8")

    home_path = output / "index.html"
    home_path.write_text(
        _patch_portal_home(
            home_path.read_text(encoding="utf-8"),
            summary,
        ),
        encoding="utf-8",
    )

    public_base = str(links.get("base_url") or "")
    links["metadata_triage_url"] = public_base + "metadata-triage/"
    links["metadata_triage_index_url"] = public_base + "metadata-triage.json"
    links["metadata_triage_policy_url"] = (
        public_base + TRIAGE_POLICY_FILENAME
    )
    links["metadata_triage_summary"] = summary
    links["search_projection"] = search_projection
    links["search_index_article_count"] = search_index["article_count"]
    links["triage_delivery_generated_at"] = generated_at
    (output / "links.json").write_text(json_text(links), encoding="utf-8")
    return links


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evidenceradar_editions.triage_delivery"
    )
    parser.add_argument("--editions-root", type=Path, default=Path("editions"))
    parser.add_argument("--catalog-root", type=Path, default=Path("catalog"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--base-url")
    parser.add_argument("--allow-untranslated", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        links = build_triage_delivery(
            output_dir=args.output_dir,
            repository=args.repository,
            editions_root=args.editions_root,
            catalog_root=args.catalog_root,
            base_url=args.base_url,
            require_zh_tw=not args.allow_untranslated,
        )
        print(json.dumps(links, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
