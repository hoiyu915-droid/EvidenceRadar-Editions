from __future__ import annotations

import json
import re
import shutil
from collections import defaultdict
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .archive import Publication, discover_publications
from .serialization import json_text
from .utils import utc_now_iso

_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

PORTAL_STYLE = r"""
:root{--ink:#182033;--muted:#667085;--line:#d9e1ed;--panel:#fff;--brand:#2457d6;--brand2:#6f42c1;--soft:#f4f7fb;--shadow:0 10px 30px rgba(24,37,68,.08)}
*{box-sizing:border-box}body{margin:0;background:#eef2f8;color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans TC","PingFang TC",sans-serif;line-height:1.55}
a{color:var(--brand);text-underline-offset:.15em}.hero{padding:36px max(20px,calc((100vw - 1120px)/2));color:#fff;background:linear-gradient(135deg,#10275f,#2457d6 58%,#6f42c1)}
.hero h1{margin:0;font-size:clamp(2rem,5vw,3.5rem)}.hero p{max-width:850px;margin:8px 0 0;opacity:.9}.shell{width:min(1120px,calc(100% - 28px));margin:22px auto 60px}.search{display:grid;grid-template-columns:2fr 1fr 1fr auto;gap:10px;padding:14px;background:#fff;border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow)}input,select,button{font:inherit;min-height:42px;border:1px solid #bcc7d8;border-radius:9px;padding:8px 10px;background:#fff;color:var(--ink)}button{cursor:pointer}.summary{display:flex;gap:12px;flex-wrap:wrap;margin:18px 0}.metric{background:#fff;border:1px solid var(--line);border-radius:12px;padding:12px 16px;min-width:150px}.metric strong{display:block;font-size:1.35rem}.metric span{font-size:.8rem;color:var(--muted)}h2{margin:28px 0 10px}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px}.card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:16px;box-shadow:0 8px 22px rgba(24,37,68,.06)}.card[hidden]{display:none}.card h3{margin:0}.meta{color:var(--muted);font-size:.86rem;margin:8px 0}.badge{display:inline-block;border-radius:999px;background:#edf2ff;color:#2346a5;padding:3px 9px;font-size:.76rem;font-weight:700;margin:3px 4px 3px 0}.actions{display:flex;gap:12px;flex-wrap:wrap;margin-top:12px}.actions a{font-weight:700}.article-results{margin-top:14px}.result{padding:10px 0;border-bottom:1px solid var(--line)}.result strong{display:block}.empty{padding:20px;text-align:center;color:var(--muted);background:#fff;border:1px dashed #aeb9ca;border-radius:12px}.small{display:block;color:var(--muted);font-size:.82rem}.revision-list{display:grid;gap:12px}.revision{background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px}.revision.latest{border-color:#8da7ff;box-shadow:0 8px 22px rgba(36,87,214,.10)}code{overflow-wrap:anywhere}footer{text-align:center;color:var(--muted);font-size:.8rem;padding:24px}
@media(max-width:720px){.search{grid-template-columns:1fr}.hero{padding:28px 18px}}
"""

PORTAL_SCRIPT = r"""
(() => {
 const q=document.querySelector('#portal-query'), journal=document.querySelector('#portal-journal'), kind=document.querySelector('#portal-kind'), clear=document.querySelector('#portal-clear');
 const cards=Array.from(document.querySelectorAll('.edition-card')), count=document.querySelector('#edition-visible'), articleBox=document.querySelector('#article-results');
 let articleIndex=null;
 const norm=v=>String(v||'').normalize('NFKC').toLocaleLowerCase('zh-Hant');
 const escapeHtml=s=>String(s||'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
 async function loadArticles(){if(articleIndex!==null)return articleIndex;try{const response=await fetch('search-index.json',{cache:'no-store'});if(!response.ok)throw new Error(String(response.status));articleIndex=await response.json()}catch(e){articleIndex={articles:[]}}return articleIndex}
 async function apply(){const needle=norm(q.value).trim();let shown=0;for(const card of cards){const ok=(!needle||norm(card.dataset.search).includes(needle))&&(!journal.value||card.dataset.journal===journal.value)&&(!kind.value||card.dataset.kind===kind.value);card.hidden=!ok;if(ok)shown++}count.textContent=String(shown);articleBox.innerHTML='';if(needle.length>=2){const index=await loadArticles();const matches=(index.articles||[]).filter(x=>norm([x.title_zh_tw,x.title_original,x.doi,x.pmid,x.pmcid,x.journal].join(' ')).includes(needle)).slice(0,40);if(matches.length){articleBox.innerHTML='<h2>文章搜尋結果</h2>'+matches.map(x=>`<div class="result"><a href="${x.url}"><strong>${escapeHtml(x.title_zh_tw||x.title_original)}</strong></a><span class="small">${escapeHtml(x.journal)} · ${escapeHtml(x.period_key)}${x.doi?' · DOI '+escapeHtml(x.doi):''}</span></div>`).join('')}else{articleBox.innerHTML='<p class="empty">沒有文章符合這個關鍵字。</p>'}}}
 for(const control of [q,journal,kind])control.addEventListener(control===q?'input':'change',apply);
 clear.addEventListener('click',()=>{q.value='';journal.value='';kind.value='';apply();q.focus()});apply();
})();
"""


def _e(value: Any) -> str:
    return escape(str(value if value is not None else ""), quote=True)


def _repository_base_url(repository: str) -> str:
    if not _REPOSITORY_RE.fullmatch(repository):
        raise ValueError("repository must use owner/name form")
    owner, name = repository.split("/", 1)
    if name.casefold() == f"{owner}.github.io".casefold():
        return f"https://{owner}.github.io/"
    return f"https://{owner}.github.io/{name}/"


def _validate_base_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("Pages base URL must be a clean HTTPS URL")
    return value.rstrip("/") + "/"


def _edition_entry(publication: Publication) -> dict[str, Any]:
    manifest = publication.manifest
    edition = publication.edition
    scope = edition.get("scope") or {}
    files = manifest.get("files") or {}
    revision_url = publication.relative_path
    period_url = f"journals/{publication.journal_slug}/{publication.period_key}/"
    return {
        "edition_id": manifest.get("edition_id"),
        "publication_id": manifest.get("publication_id"),
        "journal": manifest.get("journal"),
        "journal_slug": manifest.get("journal_slug"),
        "period_kind": manifest.get("period_kind"),
        "period_key": manifest.get("period_key"),
        "period_label_zh_tw": scope.get("period_label_zh_tw"),
        "period_start": manifest.get("period_start"),
        "period_end": manifest.get("period_end"),
        "revision": manifest.get("revision"),
        "article_count": manifest.get("article_count"),
        "translated_article_count": manifest.get("translated_article_count"),
        "created_at": manifest.get("created_at"),
        "retrieved_at": edition.get("retrieved_at"),
        "revision_url": revision_url,
        "period_url": period_url,
        "download_html": revision_url
        + str((files.get("report_html") or {}).get("name") or ""),
        "download_json": revision_url
        + str((files.get("edition_json") or {}).get("name") or ""),
        "manifest_url": revision_url + "manifest.json",
    }


def _latest_by_period(
    publications: list[Publication], entries: list[dict[str, Any]]
) -> tuple[
    dict[tuple[str, str], list[tuple[Publication, dict[str, Any]]]],
    list[dict[str, Any]],
]:
    grouped: dict[
        tuple[str, str], list[tuple[Publication, dict[str, Any]]]
    ] = defaultdict(list)
    for publication, entry in zip(publications, entries, strict=True):
        grouped[(publication.journal_slug, publication.period_key)].append(
            (publication, entry)
        )
    latest: list[dict[str, Any]] = []
    for candidates in grouped.values():
        candidates.sort(key=lambda value: value[0].revision, reverse=True)
        latest_entry = dict(candidates[0][1])
        latest_entry["revision_count"] = len(candidates)
        latest_entry["is_latest"] = True
        latest.append(latest_entry)
        for index, (_, entry) in enumerate(candidates):
            entry["is_latest"] = index == 0
            entry["revision_count"] = len(candidates)
    latest.sort(
        key=lambda item: (
            str(item.get("period_end") or ""),
            str(item.get("journal") or "").casefold(),
        ),
        reverse=True,
    )
    return grouped, latest


def _period_page(
    journal: str,
    period_label: str,
    entries: list[dict[str, Any]],
) -> str:
    entries = sorted(entries, key=lambda item: int(item["revision"]), reverse=True)
    latest = entries[0]
    rows: list[str] = []
    for entry in entries:
        latest_class = " latest" if entry.get("is_latest") else ""
        latest_badge = '<span class="badge">目前最新版</span>' if entry.get("is_latest") else ""
        rows.append(
            f'<article class="revision{latest_class}">'
            f'<h3>r{int(entry["revision"]):02d} {latest_badge}</h3>'
            f'<p class="meta">重建：{_e(entry.get("retrieved_at") or "—")} · manifest：{_e(entry.get("created_at") or "—")}</p>'
            f'<span class="badge">{_e(entry["article_count"])} 篇</span>'
            f'<span class="badge">繁中 {_e(entry["translated_article_count"])}/{_e(entry["article_count"])}</span>'
            '<div class="actions">'
            f'<a href="r{int(entry["revision"]):02d}/">開啟互動 HTML</a>'
            f'<a href="r{int(entry["revision"]):02d}/edition.json">JSON</a>'
            f'<a href="r{int(entry["revision"]):02d}/manifest.json">manifest</a>'
            '</div></article>'
        )
    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{_e(journal)} {_e(period_label)}｜EvidenceRadar Editions</title><style>{PORTAL_STYLE}</style></head><body><header class="hero"><h1>{_e(journal)}</h1><p>{_e(period_label)} · 保留所有 immutable revision，最新版為 r{int(latest['revision']):02d}。</p></header><main class="shell"><p><a href="../">← 返回期刊總覽</a></p><div class="summary"><div class="metric"><strong>{len(entries)}</strong><span>修訂版本</span></div><div class="metric"><strong>{_e(latest['article_count'])}</strong><span>最新版文章</span></div></div><p><a href="r{int(latest['revision']):02d}/"><strong>直接開啟最新版互動 HTML →</strong></a></p><section class="revision-list">{''.join(rows)}</section></main><footer>EvidenceRadar Editions</footer></body></html>\n"""


def _journal_page(journal: str, entries: list[dict[str, Any]]) -> str:
    cards: list[str] = []
    for entry in entries:
        cards.append(
            '<article class="card">'
            f'<h3>{_e(entry.get("period_label_zh_tw") or entry["period_key"])}</h3>'
            f'<p class="meta">{_e(entry["period_start"])} 至 {_e(entry["period_end"])} · 最新 r{int(entry["revision"]):02d}</p>'
            f'<span class="badge">{_e(entry["article_count"])} 篇</span>'
            f'<span class="badge">繁中 {_e(entry["translated_article_count"])}/{_e(entry["article_count"])}</span>'
            f'<span class="badge">{_e(entry["revision_count"])} 個 revision</span>'
            '<div class="actions">'
            f'<a href="{_e(entry["period_key"] + "/r" + format(int(entry["revision"]), "02d") + "/")}">開啟最新版</a>'
            f'<a href="{_e(entry["period_key"] + "/")}">版本紀錄</a>'
            '</div></article>'
        )
    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{_e(journal)}｜EvidenceRadar Editions</title><style>{PORTAL_STYLE}</style></head><body><header class="hero"><h1>{_e(journal)}</h1><p>期刊歷史刊物總覽。每一期都保留資料範圍、修訂版與來源 provenance。</p></header><main class="shell"><p><a href="../../">← 返回所有期刊</a></p><div class="summary"><div class="metric"><strong>{len(entries)}</strong><span>已發布期數</span></div></div><section class="grid">{''.join(cards) or '<p class="empty">尚無已發布刊物。</p>'}</section></main><footer>EvidenceRadar Editions</footer></body></html>\n"""


def _portal_page(
    latest_entries: list[dict[str, Any]],
    *,
    journal_count: int,
    revision_count: int,
    article_count: int,
) -> str:
    journals = sorted(
        {
            (str(entry["journal_slug"]), str(entry["journal"]))
            for entry in latest_entries
        },
        key=lambda value: value[1].casefold(),
    )
    journal_options = "".join(
        f'<option value="{_e(slug)}">{_e(name)}</option>'
        for slug, name in journals
    )
    cards: list[str] = []
    for entry in latest_entries:
        search = " ".join(
            str(entry.get(key) or "")
            for key in (
                "journal",
                "period_key",
                "period_label_zh_tw",
                "period_start",
                "period_end",
            )
        )
        cards.append(
            f'<article class="card edition-card" data-journal="{_e(entry["journal_slug"])}" data-kind="{_e(entry["period_kind"])}" data-search="{_e(search)}">'
            f'<h3>{_e(entry["journal"])}</h3>'
            f'<p class="meta">{_e(entry.get("period_label_zh_tw") or entry["period_key"])} · 最新 r{int(entry["revision"]):02d}</p>'
            f'<span class="badge">{_e(entry["article_count"])} 篇</span>'
            f'<span class="badge">繁中 {_e(entry["translated_article_count"])}/{_e(entry["article_count"])}</span>'
            f'<span class="badge">{_e(entry["revision_count"])} 個 revision</span>'
            '<div class="actions">'
            f'<a href="{_e(entry["revision_url"])}">開啟互動 HTML</a>'
            f'<a href="{_e(entry["period_url"])}">版本紀錄</a>'
            f'<a href="{_e("journals/" + str(entry["journal_slug"]) + "/")}">期刊總覽</a>'
            '</div></article>'
        )
    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="EvidenceRadar Editions 期刊刊物總覽"><title>EvidenceRadar Editions</title><style>{PORTAL_STYLE}</style></head><body><header class="hero"><h1>EvidenceRadar Editions</h1><p>按期刊與時間瀏覽已發布文獻刊物。每一期可直接開啟繁中互動 HTML，也保留原文題名、來源、永久識別碼與 immutable revision。</p></header><main class="shell"><section class="search" aria-label="刊物與文章搜尋"><input id="portal-query" type="search" placeholder="搜尋期刊、期數、文章題名或 DOI…"><select id="portal-journal"><option value="">全部期刊</option>{journal_options}</select><select id="portal-kind"><option value="">全部期間</option><option value="day">日刊</option><option value="week">週刊</option><option value="month">月刊</option><option value="range">自訂範圍</option></select><button id="portal-clear" type="button">清除</button></section><div class="summary"><div class="metric"><strong>{journal_count}</strong><span>期刊</span></div><div class="metric"><strong>{len(latest_entries)}</strong><span>獨立期數</span></div><div class="metric"><strong>{revision_count}</strong><span>immutable revisions</span></div><div class="metric"><strong>{article_count}</strong><span>最新版文章索引</span></div><div class="metric"><strong id="edition-visible">{len(latest_entries)}</strong><span>目前顯示</span></div></div><h2>已發布刊物</h2><section class="grid">{''.join(cards) or '<p class="empty">尚無已發布刊物。</p>'}</section><section class="article-results" id="article-results"></section></main><footer>EvidenceRadar Editions · latest 只代表目前已發布的最新版，不代表即時監測。</footer><script>{PORTAL_SCRIPT}</script></body></html>\n"""


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
    entries = [_edition_entry(publication) for publication in publications]
    grouped, latest_entries = _latest_by_period(publications, entries)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / ".nojekyll").write_text("", encoding="utf-8")

    by_journal: dict[str, list[dict[str, Any]]] = defaultdict(list)
    search_articles: list[dict[str, Any]] = []
    publication_by_id = {
        str(entry["publication_id"]): publication
        for publication, entry in zip(publications, entries, strict=True)
    }
    for publication in publications:
        destination = output_dir / publication.relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(publication.directory, destination)

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
                    "title_original": article.get("title_original")
                    or article.get("title"),
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
        candidate_entries = [entry for _, entry in candidates]
        latest = candidate_entries[0]
        period_dir = output_dir / "journals" / slug / period
        period_dir.mkdir(parents=True, exist_ok=True)
        period_label = str(latest.get("period_label_zh_tw") or period)
        (period_dir / "index.html").write_text(
            _period_page(str(latest.get("journal") or slug), period_label, candidate_entries),
            encoding="utf-8",
        )
        (period_dir / "index.json").write_text(
            json_text(
                {
                    "schema_version": "1.0",
                    "artifact_type": "EvidenceRadar_Editions_PeriodIndex",
                    "journal_slug": slug,
                    "period_key": period,
                    "latest_revision": latest.get("revision"),
                    "revisions": candidate_entries,
                }
            ),
            encoding="utf-8",
        )

    for slug, journal_entries in by_journal.items():
        ordered = sorted(
            journal_entries,
            key=lambda item: str(item.get("period_end") or ""),
            reverse=True,
        )
        journal_name = str(ordered[0]["journal"]) if ordered else slug
        journal_dir = output_dir / "journals" / slug
        journal_dir.mkdir(parents=True, exist_ok=True)
        (journal_dir / "index.html").write_text(
            _journal_page(journal_name, ordered), encoding="utf-8"
        )
        (journal_dir / "index.json").write_text(
            json_text(
                {
                    "schema_version": "1.0",
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
        "schema_version": "1.0",
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
        "schema_version": "1.0",
        "artifact_type": "EvidenceRadar_Editions_SearchIndex",
        "generated_at": generated_at,
        "semantics": "latest_revision_per_journal_period",
        "article_count": len(search_articles),
        "articles": search_articles,
    }
    (output_dir / "index.html").write_text(
        _portal_page(
            latest_entries,
            journal_count=len(by_journal),
            revision_count=len(entries),
            article_count=len(search_articles),
        ),
        encoding="utf-8",
    )
    (output_dir / "index.json").write_text(json_text(catalog), encoding="utf-8")
    (output_dir / "search-index.json").write_text(
        json_text(search_index), encoding="utf-8"
    )

    public_base = _validate_base_url(
        base_url if base_url is not None else _repository_base_url(repository)
    )
    links = {
        "schema_version": "1.0",
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
    (output_dir / "links.json").write_text(json_text(links), encoding="utf-8")
    return links
