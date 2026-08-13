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

STYLE = r"""
:root{--ink:#182033;--muted:#667085;--line:#d9e1ed;--brand:#2457d6;--brand2:#6f42c1;--soft:#f4f7fb;--shadow:0 10px 30px rgba(24,37,68,.08)}
*{box-sizing:border-box}body{margin:0;background:#eef2f8;color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans TC","PingFang TC",sans-serif;line-height:1.55}
a{color:var(--brand);text-underline-offset:.15em}.hero{padding:36px max(20px,calc((100vw - 1160px)/2));color:#fff;background:linear-gradient(135deg,#10275f,#2457d6 58%,#6f42c1)}
.hero h1{margin:0;font-size:clamp(2rem,5vw,3.4rem)}.hero p{max-width:900px;margin:8px 0 0;opacity:.92}.shell{width:min(1160px,calc(100% - 28px));margin:22px auto 60px}
.search{display:grid;grid-template-columns:2fr 1fr auto;gap:10px;padding:14px;background:#fff;border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow)}input,select,button{font:inherit;min-height:42px;border:1px solid #bcc7d8;border-radius:9px;padding:8px 10px;background:#fff;color:var(--ink)}button{cursor:pointer}
.summary{display:flex;gap:12px;flex-wrap:wrap;margin:18px 0}.metric{background:#fff;border:1px solid var(--line);border-radius:12px;padding:12px 16px;min-width:150px}.metric strong{display:block;font-size:1.35rem}.metric span{font-size:.8rem;color:var(--muted)}
.table-wrap{overflow:auto;background:#fff;border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow)}table{border-collapse:collapse;width:100%;min-width:780px}th,td{padding:12px 14px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{background:#f7f9fc;color:#475467;font-size:.78rem}tr:last-child td{border-bottom:0}tr[hidden]{display:none}.journal{font-weight:800}
.badge{display:inline-block;border-radius:999px;background:#edf2ff;color:#2346a5;padding:3px 9px;font-size:.75rem;font-weight:700;margin:2px 4px 2px 0}.badge.mtd{background:#fff1dc;color:#934b00}.actions a{font-weight:700;margin-right:10px}.small{font-size:.8rem;color:var(--muted)}
.article-results{margin-top:18px}.result{padding:10px 0;border-bottom:1px solid var(--line)}.result strong{display:block}.empty{padding:20px;text-align:center;color:var(--muted);background:#fff;border:1px dashed #aeb9ca;border-radius:12px}.section-note{background:#fff;border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin:14px 0}footer{text-align:center;color:var(--muted);font-size:.8rem;padding:24px}
@media(max-width:720px){.search{grid-template-columns:1fr}.hero{padding:28px 18px}}
"""

SCRIPT = r"""
(() => {
 const q=document.querySelector('#portal-query'), kind=document.querySelector('#portal-kind'), clear=document.querySelector('#portal-clear');
 const rows=Array.from(document.querySelectorAll('#journal-table tbody tr')), count=document.querySelector('#journal-visible'), articleBox=document.querySelector('#article-results');
 let articleIndex=null; const norm=v=>String(v||'').normalize('NFKC').toLocaleLowerCase('zh-Hant');
 const esc=s=>String(s||'').replace(/[&<>'\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','\"':'&quot;'}[c]));
 async function load(){if(articleIndex!==null)return articleIndex;try{const r=await fetch('search-index.json',{cache:'no-store'});if(!r.ok)throw new Error(String(r.status));articleIndex=await r.json()}catch(e){articleIndex={articles:[]}}return articleIndex}
 async function apply(){const needle=norm(q.value).trim();let shown=0;for(const row of rows){const ok=(!needle||norm(row.dataset.search).includes(needle))&&(!kind.value||row.dataset.kind===kind.value);row.hidden=!ok;if(ok)shown++}count.textContent=String(shown);articleBox.innerHTML='';if(needle.length>=2){const idx=await load();const matches=(idx.articles||[]).filter(x=>norm([x.title_zh_tw,x.title_original,x.doi,x.pmid,x.journal].join(' ')).includes(needle)).slice(0,50);articleBox.innerHTML=matches.length?'<h2>文章搜尋結果</h2>'+matches.map(x=>`<div class="result"><a href="${x.url}"><strong>${esc(x.title_zh_tw||x.title_original)}</strong></a><span class="small">${esc(x.journal)} · ${esc(x.period_key)}${x.doi?' · DOI '+esc(x.doi):''}</span></div>`).join(''):'<p class="empty">沒有文章符合這個關鍵字。</p>'}}
 for(const el of [q,kind])el.addEventListener(el===q?'input':'change',apply);clear.addEventListener('click',()=>{q.value='';kind.value='';apply();q.focus()});apply();
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


def _entry(publication: Publication) -> dict[str, Any]:
    manifest = publication.manifest
    edition = publication.edition
    scope = edition.get("scope") or {}
    return {
        "edition_id": manifest.get("edition_id"),
        "publication_id": manifest.get("publication_id"),
        "journal": manifest.get("journal"),
        "journal_slug": publication.journal_slug,
        "period_kind": manifest.get("period_kind"),
        "period_key": manifest.get("period_key"),
        "period_label_zh_tw": scope.get("period_label_zh_tw") or manifest.get("period_key"),
        "period_status": scope.get("period_status") or "FINAL",
        "period_complete": scope.get("period_complete", True),
        "period_start": manifest.get("period_start"),
        "period_end": manifest.get("period_end"),
        "revision": publication.revision,
        "article_count": manifest.get("article_count"),
        "translated_article_count": manifest.get("translated_article_count"),
        "created_at": manifest.get("created_at"),
        "retrieved_at": edition.get("retrieved_at"),
        "revision_url": publication.relative_path,
        "period_url": f"journals/{publication.journal_slug}/{publication.period_key}/",
    }


def _group_latest(publications: list[Publication], entries: list[dict[str, Any]]):
    grouped: dict[tuple[str, str], list[tuple[Publication, dict[str, Any]]]] = defaultdict(list)
    for publication, entry in zip(publications, entries, strict=True):
        grouped[(publication.journal_slug, publication.period_key)].append((publication, entry))
    latest=[]
    for candidates in grouped.values():
        candidates.sort(key=lambda v:v[0].revision, reverse=True)
        for i,(_,entry) in enumerate(candidates):
            entry["is_latest"] = i == 0
            entry["revision_count"] = len(candidates)
        latest.append(dict(candidates[0][1]))
    latest.sort(key=lambda x:(str(x.get("period_end") or ""),str(x.get("journal") or "").casefold()), reverse=True)
    return grouped, latest


def _status_badge(entry: dict[str, Any]) -> str:
    value=str(entry.get("period_status") or "FINAL")
    cls=" mtd" if value == "MTD" else ""
    return f'<span class="badge{cls}">{_e(value)}</span>'


def _period_page(journal: str, label: str, entries: list[dict[str, Any]]) -> str:
    entries=sorted(entries,key=lambda x:int(x["revision"]),reverse=True)
    rows=[]
    for entry in entries:
        r=int(entry["revision"])
        rows.append(f'<tr><td>r{r:02d}</td><td>{_status_badge(entry)}</td><td>{_e(entry.get("period_start"))} → {_e(entry.get("period_end"))}</td><td>{_e(entry.get("article_count"))}</td><td>{_e(entry.get("translated_article_count"))}/{_e(entry.get("article_count"))}</td><td class="actions"><a href="r{r:02d}/">開啟互動 HTML</a><a href="r{r:02d}/edition.json">JSON</a><a href="r{r:02d}/manifest.json">manifest</a></td></tr>')
    return f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{_e(journal)} {_e(label)}｜EvidenceRadar Editions</title><style>{STYLE}</style></head><body><header class="hero"><h1>{_e(journal)}</h1><p>{_e(label)} · 同一期別的重建以 immutable revision 保存。</p></header><main class="shell"><p><a href="../">← 返回月份表</a></p><div class="table-wrap"><table><thead><tr><th>revision</th><th>狀態</th><th>來源涵蓋</th><th>文獻</th><th>繁中</th><th>入口</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></main><footer>EvidenceRadar Editions</footer></body></html>\n'''


def _journal_page(journal: str, latest_entries: list[dict[str, Any]]) -> str:
    months=[x for x in latest_entries if x.get("period_kind") == "month"]
    others=[x for x in latest_entries if x.get("period_kind") != "month"]
    months.sort(key=lambda x:str(x.get("period_key") or ""), reverse=True)
    def row(entry):
        r=int(entry["revision"])
        return f'<tr><td><strong>{_e(entry.get("period_key"))}</strong><div class="small">{_e(entry.get("period_label_zh_tw"))}</div></td><td>{_status_badge(entry)}</td><td>{_e(entry.get("period_end"))}</td><td>{_e(entry.get("article_count"))}</td><td>{_e(entry.get("translated_article_count"))}/{_e(entry.get("article_count"))}</td><td>r{r:02d}</td><td class="actions"><a href="{_e(entry["period_key"] + "/r" + format(r,"02d") + "/")}">開啟互動 HTML</a><a href="{_e(entry["period_key"] + "/")}">版本紀錄</a></td></tr>'
    month_rows=''.join(row(x) for x in months) or '<tr><td colspan="7">尚無月刊。</td></tr>'
    other_html=''
    if others:
        other_html='<h2>其他期別</h2><div class="table-wrap"><table><thead><tr><th>期別</th><th>狀態</th><th>截至</th><th>文獻</th><th>繁中</th><th>rev</th><th>入口</th></tr></thead><tbody>'+''.join(row(x) for x in others)+'</tbody></table></div>'
    return f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{_e(journal)}｜EvidenceRadar Editions</title><style>{STYLE}</style></head><body><header class="hero"><h1>{_e(journal)}</h1><p>每一列是一個月份；當月尚未結束時標 MTD，月底重建仍屬同一 YYYY-MM 並新增 revision。</p></header><main class="shell"><p><a href="../../">← 返回期刊總表</a></p><h2>月份資料</h2><div class="table-wrap"><table><thead><tr><th>月份</th><th>狀態</th><th>涵蓋至</th><th>文獻</th><th>繁中</th><th>最新 rev</th><th>入口</th></tr></thead><tbody>{month_rows}</tbody></table></div>{other_html}</main><footer>EvidenceRadar Editions</footer></body></html>\n'''


def _portal_page(latest_entries: list[dict[str, Any]], revision_count: int, article_count: int) -> str:
    by_journal: dict[str,list[dict[str,Any]]] = defaultdict(list)
    for entry in latest_entries:
        by_journal[str(entry["journal_slug"])].append(entry)
    rows=[]
    for slug, items in sorted(by_journal.items(), key=lambda kv:str(kv[1][0].get("journal") or "").casefold()):
        months=sorted([x for x in items if x.get("period_kind")=="month"], key=lambda x:str(x.get("period_key") or ""), reverse=True)
        latest=months[0] if months else sorted(items,key=lambda x:str(x.get("period_end") or ""),reverse=True)[0]
        search=' '.join([str(latest.get("journal") or ""),slug,str(latest.get("period_key") or "")])
        rows.append(f'<tr data-search="{_e(search)}" data-kind="{_e(latest.get("period_kind") or "")}"><td class="journal"><a href="journals/{_e(slug)}/">{_e(latest.get("journal"))}</a></td><td>{_e(latest.get("period_key"))}</td><td>{_status_badge(latest)}<div class="small">至 {_e(latest.get("period_end"))}</div></td><td>{_e(latest.get("article_count"))}</td><td>{_e(latest.get("translated_article_count"))}/{_e(latest.get("article_count"))}</td><td>{len(months)}</td><td>{sum(int(x.get("revision_count") or 1) for x in items)}</td><td class="actions"><a href="journals/{_e(slug)}/">月份表</a><a href="{_e(latest.get("revision_url"))}">最新刊</a></td></tr>')
    return f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="EvidenceRadar Editions 期刊與月份總表"><title>EvidenceRadar Editions</title><style>{STYLE}</style></head><body><header class="hero"><h1>EvidenceRadar Editions</h1><p>期刊總表 → 各期刊月份表 → immutable revision。可搜尋期刊、文章題名或 DOI。</p></header><main class="shell"><section class="search"><input id="portal-query" type="search" placeholder="搜尋期刊、文章題名或 DOI…"><select id="portal-kind"><option value="">全部期別</option><option value="month">月刊</option><option value="week">週刊</option><option value="day">日刊</option><option value="range">範圍</option></select><button id="portal-clear" type="button">清除</button></section><div class="summary"><div class="metric"><strong>{len(by_journal)}</strong><span>期刊</span></div><div class="metric"><strong>{len(latest_entries)}</strong><span>期別</span></div><div class="metric"><strong>{revision_count}</strong><span>revisions</span></div><div class="metric"><strong>{article_count}</strong><span>最新版文章索引</span></div><div class="metric"><strong id="journal-visible">{len(by_journal)}</strong><span>目前顯示期刊</span></div></div><h2>期刊總表</h2><div class="table-wrap"><table id="journal-table"><thead><tr><th>期刊</th><th>最新月份／期別</th><th>狀態</th><th>文獻</th><th>繁中</th><th>月份數</th><th>rev 數</th><th>入口</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div><section id="article-results" class="article-results"></section></main><footer>EvidenceRadar Editions · published archive, not live monitoring</footer><script>{SCRIPT}</script></body></html>\n'''


def build_pages_site(*, archive_root: Path, output_dir: Path, repository: str, base_url: str | None = None, require_zh_tw: bool = True) -> dict[str, Any]:
    archive_root=Path(archive_root).resolve(); output_dir=Path(output_dir).resolve()
    if output_dir == archive_root or archive_root in output_dir.parents:
        raise ValueError("Pages output cannot be inside the archive")
    if output_dir.is_symlink():
        raise ValueError("Pages output directory must not be a symlink")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"Pages output directory must be empty: {output_dir}")
    publications=discover_publications(archive_root, require_zh_tw=require_zh_tw)
    entries=[_entry(p) for p in publications]
    grouped, latest_entries=_group_latest(publications, entries)
    output_dir.mkdir(parents=True, exist_ok=True); (output_dir/".nojekyll").write_text("",encoding="utf-8")
    publication_by_id={str(e["publication_id"]):p for p,e in zip(publications,entries,strict=True)}
    for p in publications:
        dest=output_dir/p.relative_path; dest.parent.mkdir(parents=True,exist_ok=True); shutil.copytree(p.directory,dest)
    search_articles=[]; by_journal=defaultdict(list)
    for latest in latest_entries:
        by_journal[str(latest["journal_slug"])].append(latest)
        p=publication_by_id[str(latest["publication_id"])]
        for a in p.edition.get("articles") or []:
            if not isinstance(a,dict): continue
            search_articles.append({"canonical_id":a.get("canonical_id"),"title_zh_tw":a.get("title_zh_tw"),"title_original":a.get("title_original") or a.get("title"),"doi":a.get("doi"),"pmid":a.get("pmid"),"pmcid":a.get("pmcid"),"journal":latest.get("journal"),"journal_slug":latest.get("journal_slug"),"period_key":latest.get("period_key"),"revision":latest.get("revision"),"url":latest.get("revision_url")})
    for (slug,period), candidates in grouped.items():
        c_entries=[e for _,e in candidates]; latest=c_entries[0]; pdir=output_dir/"journals"/slug/period; pdir.mkdir(parents=True,exist_ok=True)
        (pdir/"index.html").write_text(_period_page(str(latest.get("journal") or slug),str(latest.get("period_label_zh_tw") or period),c_entries),encoding="utf-8")
        (pdir/"index.json").write_text(json_text({"schema_version":"1.1","artifact_type":"EvidenceRadar_Editions_PeriodIndex","journal_slug":slug,"period_key":period,"latest_revision":latest.get("revision"),"revisions":c_entries}),encoding="utf-8")
    for slug, items in by_journal.items():
        ordered=sorted(items,key=lambda x:str(x.get("period_end") or ""),reverse=True); jname=str(ordered[0].get("journal") or slug); jdir=output_dir/"journals"/slug; jdir.mkdir(parents=True,exist_ok=True)
        (jdir/"index.html").write_text(_journal_page(jname,ordered),encoding="utf-8")
        (jdir/"index.json").write_text(json_text({"schema_version":"1.1","artifact_type":"EvidenceRadar_Editions_JournalIndex","journal":jname,"journal_slug":slug,"periods":ordered}),encoding="utf-8")
    generated=utc_now_iso(); catalog={"schema_version":"1.1","artifact_type":"EvidenceRadar_Editions_Catalog","generated_at":generated,"repository":repository,"journal_count":len(by_journal),"period_count":len(latest_entries),"revision_count":len(entries),"latest_editions":latest_entries,"editions":entries}
    search_index={"schema_version":"1.1","artifact_type":"EvidenceRadar_Editions_SearchIndex","generated_at":generated,"semantics":"latest_revision_per_journal_period","article_count":len(search_articles),"articles":search_articles}
    (output_dir/"index.html").write_text(_portal_page(latest_entries,len(entries),len(search_articles)),encoding="utf-8"); (output_dir/"index.json").write_text(json_text(catalog),encoding="utf-8"); (output_dir/"search-index.json").write_text(json_text(search_index),encoding="utf-8")
    public_base=_validate_base_url(base_url if base_url is not None else _repository_base_url(repository)); links={"schema_version":"1.1","artifact_type":"EvidenceRadar_Editions_PublicLinks","repository":repository,"generated_at":generated,"base_url":public_base,"portal_url":public_base,"catalog_url":public_base+"index.json","search_index_url":public_base+"search-index.json","journal_count":len(by_journal),"period_count":len(latest_entries),"revision_count":len(entries),"publication_semantics":"published_archive_not_live_monitoring"}
    (output_dir/"links.json").write_text(json_text(links),encoding="utf-8"); return links
