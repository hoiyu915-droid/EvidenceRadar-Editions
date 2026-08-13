from __future__ import annotations

import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

from .archive import discover_publications
from .pages_v2 import (
    SCRIPT,
    STYLE,
    _e,
    _entry,
    _group_latest,
    _journal_page,
    _period_page,
    _repository_base_url,
    _status_badge,
    _validate_base_url,
)
from .serialization import json_text
from .utils import utc_now_iso


def _portal_page(latest_entries: list[dict[str, Any]], revision_count: int, article_count: int) -> str:
    by_journal: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in latest_entries:
        by_journal[str(entry["journal_slug"])].append(entry)
    rows: list[str] = []
    for slug, items in sorted(
        by_journal.items(),
        key=lambda kv: str(kv[1][0].get("journal") or "").casefold(),
    ):
        months = sorted(
            [x for x in items if x.get("period_kind") == "month"],
            key=lambda x: str(x.get("period_key") or ""),
            reverse=True,
        )
        latest = months[0] if months else sorted(
            items, key=lambda x: str(x.get("period_end") or ""), reverse=True
        )[0]
        search = " ".join(
            [
                str(latest.get("journal") or ""),
                slug,
                str(latest.get("period_key") or ""),
            ]
        )
        rows.append(
            f'<tr data-search="{_e(search)}" data-kind="{_e(latest.get("period_kind") or "")}">'
            f'<td class="journal"><a href="journals/{_e(slug)}/">{_e(latest.get("journal"))}</a></td>'
            f'<td>{_e(latest.get("period_key"))}</td>'
            f'<td>{_status_badge(latest)}<div class="small">至 {_e(latest.get("period_end"))}</div></td>'
            f'<td>{_e(latest.get("article_count"))}</td>'
            f'<td>{_e(latest.get("translated_article_count"))}/{_e(latest.get("article_count"))}</td>'
            f'<td>{len(months)}</td>'
            f'<td>{sum(int(x.get("revision_count") or 1) for x in items)}</td>'
            f'<td class="actions"><a href="journals/{_e(slug)}/">月份表</a>'
            f'<a href="{_e(latest.get("revision_url"))}">開啟互動 HTML</a></td></tr>'
        )
    return f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="EvidenceRadar Editions 期刊與月份總表"><title>EvidenceRadar Editions</title><style>{STYLE}</style></head><body><header class="hero"><h1>EvidenceRadar Editions</h1><p>期刊總表 → 各期刊月份表 → immutable revision。可搜尋期刊、文章題名或 DOI。</p></header><main class="shell"><section class="search"><input id="portal-query" type="search" placeholder="搜尋期刊、文章題名或 DOI…"><select id="portal-kind"><option value="">全部期別</option><option value="month">月刊</option><option value="week">週刊</option><option value="day">日刊</option><option value="range">範圍</option></select><button id="portal-clear" type="button">清除</button></section><div class="summary"><div class="metric"><strong>{len(by_journal)}</strong><span>期刊</span></div><div class="metric"><strong>{len(latest_entries)}</strong><span>期別</span></div><div class="metric"><strong>{revision_count}</strong><span>revisions</span></div><div class="metric"><strong>{article_count}</strong><span>最新版文章索引</span></div><div class="metric"><strong id="journal-visible">{len(by_journal)}</strong><span>目前顯示期刊</span></div></div><h2>期刊總表</h2><div class="table-wrap"><table id="journal-table"><thead><tr><th>期刊</th><th>最新月份／期別</th><th>狀態</th><th>文獻</th><th>繁中</th><th>月份數</th><th>rev 數</th><th>入口</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div><section id="article-results" class="article-results"></section></main><footer>EvidenceRadar Editions · published archive, not live monitoring</footer><script>{SCRIPT}</script></body></html>\n'''


def build_pages_site(
    *,
    archive_root: Path,
    output_dir: Path,
    repository: str,
    base_url: str | None = None,
    require_zh_tw: bool = True,
) -> dict[str, Any]:
    archive_root = Path(archive_root).resolve()
    output_dir = Path(output_dir).resolve()
    if output_dir == archive_root or archive_root in output_dir.parents:
        raise ValueError("Pages output cannot be inside the archive")
    if output_dir.is_symlink():
        raise ValueError("Pages output directory must not be a symlink")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"Pages output directory must be empty: {output_dir}")

    publications = discover_publications(
        archive_root, require_zh_tw=require_zh_tw
    )
    entries = [_entry(p) for p in publications]
    grouped, latest_entries = _group_latest(publications, entries)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / ".nojekyll").write_text("", encoding="utf-8")

    publication_by_id = {
        str(e["publication_id"]): p
        for p, e in zip(publications, entries, strict=True)
    }
    for publication in publications:
        destination = output_dir / publication.relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(publication.directory, destination)

    search_articles: list[dict[str, Any]] = []
    by_journal: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for latest in latest_entries:
        by_journal[str(latest["journal_slug"])].append(latest)
        publication = publication_by_id[str(latest["publication_id"])]
        for article in publication.edition.get("articles") or []:
            if not isinstance(article, dict):
                continue
            search_articles.append(
                {
                    "canonical_id": article.get("canonical_id"),
                    "title_zh_tw": article.get("title_zh_tw"),
                    "title_original": article.get("title_original") or article.get("title"),
                    "doi": article.get("doi"),
                    "pmid": article.get("pmid"),
                    "pmcid": article.get("pmcid"),
                    "journal": latest.get("journal"),
                    "journal_slug": latest.get("journal_slug"),
                    "period_key": latest.get("period_key"),
                    "revision": latest.get("revision"),
                    "url": latest.get("revision_url"),
                }
            )

    for (slug, period), candidates in grouped.items():
        candidate_entries = [e for _, e in candidates]
        latest = candidate_entries[0]
        period_dir = output_dir / "journals" / slug / period
        period_dir.mkdir(parents=True, exist_ok=True)
        (period_dir / "index.html").write_text(
            _period_page(
                str(latest.get("journal") or slug),
                str(latest.get("period_label_zh_tw") or period),
                candidate_entries,
            ),
            encoding="utf-8",
        )
        (period_dir / "index.json").write_text(
            json_text(
                {
                    "schema_version": "1.2",
                    "artifact_type": "EvidenceRadar_Editions_PeriodIndex",
                    "journal_slug": slug,
                    "period_key": period,
                    "latest_revision": latest.get("revision"),
                    "revisions": candidate_entries,
                }
            ),
            encoding="utf-8",
        )

    for slug, items in by_journal.items():
        ordered = sorted(
            items,
            key=lambda x: str(x.get("period_end") or ""),
            reverse=True,
        )
        journal_name = str(ordered[0].get("journal") or slug)
        journal_dir = output_dir / "journals" / slug
        journal_dir.mkdir(parents=True, exist_ok=True)
        (journal_dir / "index.html").write_text(
            _journal_page(journal_name, ordered), encoding="utf-8"
        )
        (journal_dir / "index.json").write_text(
            json_text(
                {
                    "schema_version": "1.2",
                    "artifact_type": "EvidenceRadar_Editions_JournalIndex",
                    "journal": journal_name,
                    "journal_slug": slug,
                    "periods": ordered,
                }
            ),
            encoding="utf-8",
        )

    generated_at = utc_now_iso()
    catalog = {
        "schema_version": "1.2",
        "artifact_type": "EvidenceRadar_Editions_Catalog",
        "generated_at": generated_at,
        "repository": repository,
        "journal_count": len(by_journal),
        "period_count": len(latest_entries),
        "revision_count": len(entries),
        "latest_editions": latest_entries,
        "editions": entries,
    }
    search_index = {
        "schema_version": "1.2",
        "artifact_type": "EvidenceRadar_Editions_SearchIndex",
        "generated_at": generated_at,
        "semantics": "latest_revision_per_journal_period",
        "article_count": len(search_articles),
        "articles": search_articles,
    }
    (output_dir / "index.html").write_text(
        _portal_page(latest_entries, len(entries), len(search_articles)),
        encoding="utf-8",
    )
    (output_dir / "index.json").write_text(
        json_text(catalog), encoding="utf-8"
    )
    (output_dir / "search-index.json").write_text(
        json_text(search_index), encoding="utf-8"
    )

    public_base = _validate_base_url(
        base_url if base_url is not None else _repository_base_url(repository)
    )
    links = {
        "schema_version": "1.2",
        "artifact_type": "EvidenceRadar_Editions_PublicLinks",
        "repository": repository,
        "generated_at": generated_at,
        "base_url": public_base,
        "portal_url": public_base,
        "catalog_url": public_base + "index.json",
        "search_index_url": public_base + "search-index.json",
        "journal_count": len(by_journal),
        "period_count": len(latest_entries),
        "revision_count": len(entries),
        "publication_semantics": "published_archive_not_live_monitoring",
    }
    (output_dir / "links.json").write_text(
        json_text(links), encoding="utf-8"
    )
    return links
