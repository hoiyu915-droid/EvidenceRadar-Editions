from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .pages_curation import build_browse_index, render_browse_page
from .processing_policy import (
    JournalProcessingPolicy,
    apply_volume_guard,
    load_processing_policy_catalog,
    policy_for_slug,
)
from .serialization import json_text


def build_projected_browse_index(
    publication: Any,
    policy: JournalProcessingPolicy,
) -> tuple[dict[str, Any], JournalProcessingPolicy]:
    browse = build_browse_index(publication)
    article_count = int(browse.get("article_count") or 0)
    effective = apply_volume_guard(policy, observed_total=article_count)
    limit = max(0, int(effective.pages_record_limit))
    original_articles = list(browse.get("articles") or [])
    projected_articles = original_articles[:limit]
    omitted = max(0, article_count - len(projected_articles))

    browse["articles"] = projected_articles
    browse["projection"] = {
        "mode": "LIMITED" if omitted else "INLINE_ALL",
        "processing_mode_configured": effective.configured_mode,
        "processing_mode_effective": effective.effective_mode,
        "policy_source": effective.policy_source,
        "record_limit": limit,
        "canonical_article_count": article_count,
        "projected_article_count": len(projected_articles),
        "omitted_article_count": omitted,
        "volume_guard_triggered": effective.volume_guard_triggered,
        "canonical_json_complete": True,
        "selection_basis": (
            "Deterministic canonical article order. This is an operational "
            "browser projection, not a quality, evidence or relevance ranking."
        ),
    }
    browse["curation_semantics"] = (
        "Pages-only, non-destructive title-role classification plus a volume-aware "
        "browser projection. Canonical edition JSON remains complete and unchanged."
    )
    return browse, effective


def _projection_notice(browse: dict[str, Any]) -> str:
    projection = browse.get("projection") or {}
    omitted = int(projection.get("omitted_article_count") or 0)
    if omitted <= 0:
        return ""
    projected = int(projection.get("projected_article_count") or 0)
    total = int(projection.get("canonical_article_count") or 0)
    effective_mode = str(projection.get("processing_mode_effective") or "FULL")
    guard = (
        "；已觸發自動 FULL → TRIAGE 容量保護"
        if projection.get("volume_guard_triggered")
        else ""
    )
    return (
        '<p class="notice"><strong>容量感知投影：</strong>'
        f"此瀏覽頁載入 {projected} / {total} 筆書目 metadata，"
        f"其餘 {omitted} 筆保留在完整 canonical JSON；目前模式為 "
        f"{effective_mode}{guard}。截取依 deterministic canonical order，"
        "不是品質、證據力或相關性排名。</p>"
    )


def render_projected_browse_page(
    publication: Any,
    browse: dict[str, Any],
) -> str:
    html = render_browse_page(publication, browse)
    notice = _projection_notice(browse)
    if notice:
        marker = '</p><section class="summary-grid">'
        if marker not in html:
            raise ValueError("Pages browse template marker is missing")
        html = html.replace(marker, f"</p>{notice}<section class=\"summary-grid\">", 1)
    html = html.replace(
        "Pages 輕量瀏覽層；canonical edition 不因篩選或分頁而刪除。",
        "Pages 容量感知瀏覽層；canonical edition 不因投影、篩選或分頁而刪除。",
        1,
    )
    return html


def enhance_revision_pages(
    *,
    output_dir: Path,
    publications: Iterable[Any],
    catalog_root: Path | str = Path("catalog"),
) -> dict[str, int]:
    output = Path(output_dir)
    policy_catalog = load_processing_policy_catalog(catalog_root)
    revision_count = 0
    limited_revision_count = 0
    canonical_articles = 0
    projected_articles = 0
    omitted_articles = 0

    for publication in publications:
        revision_dir = output / publication.relative_path
        if not revision_dir.is_dir():
            raise ValueError(
                f"Pages revision directory is missing: {publication.relative_path}"
            )
        policy = policy_for_slug(
            publication.journal_slug,
            catalog_root=catalog_root,
            catalog=policy_catalog,
        )
        browse, _ = build_projected_browse_index(publication, policy)
        projection = browse.get("projection") or {}
        canonical = int(projection.get("canonical_article_count") or 0)
        projected = int(projection.get("projected_article_count") or 0)
        omitted = int(projection.get("omitted_article_count") or 0)

        (revision_dir / "browse.json").write_text(
            json_text(browse),
            encoding="utf-8",
        )
        (revision_dir / "index.html").write_text(
            render_projected_browse_page(publication, browse),
            encoding="utf-8",
        )

        revision_count += 1
        limited_revision_count += int(omitted > 0)
        canonical_articles += canonical
        projected_articles += projected
        omitted_articles += omitted

    return {
        "revision_count": revision_count,
        "limited_revision_count": limited_revision_count,
        "canonical_article_count": canonical_articles,
        "projected_article_count": projected_articles,
        "omitted_article_count": omitted_articles,
    }
