from __future__ import annotations

import re
from collections import Counter
from html import escape
from pathlib import Path
from typing import Any, Iterable

from .serialization import json_text

ROLE_LABELS = {
    "primary": "主要內容",
    "correction": "修正／勘誤",
    "concern": "關切／撤回",
    "editorial": "社論／前言",
}

_CONCERN_RE = re.compile(
    r"^(?:(?:editorial\s+)?expression\s+of\s+concern|retraction(?:\s+note)?|retracted|withdrawal|withdrawn)\b",
    re.IGNORECASE,
)
_CORRECTION_RE = re.compile(
    r"^(?:(?:author|publisher)\s+)?correction\b|^corrigendum\b|^erratum\b",
    re.IGNORECASE,
)
_EDITORIAL_RE = re.compile(
    r"^(?:guest\s+)?editorial(?:\b|:)|^preface\b|^introduction\s+(?:to|for)\s+(?:the\s+)?(?:special|themed)\s+issue\b",
    re.IGNORECASE,
)


def classify_publication_role(title: Any) -> str:
    value = str(title or "").strip()
    if _CONCERN_RE.search(value):
        return "concern"
    if _CORRECTION_RE.search(value):
        return "correction"
    if _EDITORIAL_RE.search(value):
        return "editorial"
    return "primary"


def _source_values(article: dict[str, Any]) -> list[str]:
    return sorted(
        {
            str(record.get("source"))
            for record in (article.get("source_records") or [])
            if isinstance(record, dict) and record.get("source")
        }
    )


def _browse_article(article: dict[str, Any]) -> dict[str, Any]:
    original = str(article.get("title_original") or article.get("title") or "").strip()
    translated = str(article.get("title_zh_tw") or "").strip()
    return {
        "canonical_id": article.get("canonical_id"),
        "title_zh_tw": translated,
        "title_original": original,
        "summary_zh_tw": str(article.get("summary_zh_tw") or "").strip(),
        "publication_date": article.get("publication_date"),
        "publication_date_precision": article.get("publication_date_precision") or "DAY",
        "article_type": article.get("article_type") or "unspecified",
        "authors": [str(value) for value in (article.get("authors") or []) if value],
        "doi": article.get("doi"),
        "pmid": article.get("pmid"),
        "pmcid": article.get("pmcid"),
        "sources": _source_values(article),
        "translated": bool(translated and article.get("summary_zh_tw")),
        "curation_role": classify_publication_role(original),
    }


def build_browse_index(publication: Any) -> dict[str, Any]:
    edition = publication.edition
    scope = edition.get("scope") or {}
    articles = [
        _browse_article(article)
        for article in (edition.get("articles") or [])
        if isinstance(article, dict)
    ]
    role_counts = Counter(article["curation_role"] for article in articles)
    article_count = len(articles)
    default_role = "primary" if article_count > 200 and role_counts.get("primary") else "all"
    facets = {
        "types": sorted({str(article["article_type"]) for article in articles}),
        "sources": sorted({source for article in articles for source in article["sources"]}),
        "dates": sorted(
            {str(article["publication_date"]) for article in articles if article["publication_date"]},
            reverse=True,
        ),
    }
    return {
        "schema_version": "1.0",
        "artifact_type": "EvidenceRadar_Editions_CuratedBrowseIndex",
        "edition_id": edition.get("edition_id"),
        "journal": scope.get("journal"),
        "period_key": scope.get("period_key"),
        "period_label_zh_tw": scope.get("period_label_zh_tw"),
        "revision": int(scope.get("revision") or 1),
        "article_count": article_count,
        "default_role": default_role,
        "default_page_size": 50,
        "role_labels": ROLE_LABELS,
        "role_counts": {key: int(role_counts.get(key, 0)) for key in ROLE_LABELS},
        "facets": facets,
        "articles": articles,
        "curation_semantics": (
            "Pages-only, non-destructive title-role classification. Canonical edition data are unchanged."
        ),
    }


def _e(value: Any) -> str:
    return escape(str(value if value is not None else ""), quote=True)


def _options(values: Iterable[str]) -> str:
    return "".join(f'<option value="{_e(value)}">{_e(value)}</option>' for value in values)


_STYLE = r"""
:root{color-scheme:light;--ink:#172033;--muted:#667085;--line:#dbe2ee;--panel:#fff;--soft:#f4f7fb;--brand:#2457d6;--warn:#9a6700;--bad:#b42318;--ok:#18794e}*{box-sizing:border-box}body{margin:0;background:#eef2f8;color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans TC","PingFang TC",sans-serif;line-height:1.55}a{color:var(--brand);text-underline-offset:.16em}.hero{background:linear-gradient(135deg,#10275f,#244fc1 55%,#6f42c1);color:white;padding:28px max(18px,calc((100vw - 1180px)/2))}.hero h1{margin:0;font-size:clamp(1.7rem,4vw,2.8rem)}.hero p{margin:7px 0 0}.shell{width:min(1180px,calc(100% - 24px));margin:20px auto 60px}.notice{padding:13px 15px;background:#fff8db;border:1px solid #ecd887;border-radius:12px;color:#5d4a00}.toolbar{display:grid;grid-template-columns:minmax(240px,2fr) repeat(4,minmax(140px,1fr));gap:10px;padding:14px;background:white;border:1px solid var(--line);border-radius:14px;position:sticky;top:0;z-index:10}.field{display:grid;gap:5px}.field label{font-size:.76rem;color:var(--muted);font-weight:700}.field input,.field select{min-height:40px;border:1px solid #bfc9d9;border-radius:9px;background:white;padding:7px 9px}.wide{grid-column:span 2}.checks{grid-column:1/-1;display:flex;gap:12px;flex-wrap:wrap;align-items:center}.checks label{font-size:.88rem}.actions{margin-left:auto;display:flex;gap:7px;flex-wrap:wrap}.btn{border:1px solid #bfc9d9;background:white;border-radius:9px;min-height:36px;padding:6px 10px;cursor:pointer}.btn.primary{background:var(--brand);color:#fff;border-color:var(--brand)}.summary-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;margin:14px 0}.metric{background:white;border:1px solid var(--line);border-radius:12px;padding:10px 12px}.metric strong{display:block;font-size:1.25rem}.metric span{font-size:.78rem;color:var(--muted)}.result-bar,.pager{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;margin:14px 2px}.downloads{display:flex;gap:9px;flex-wrap:wrap;font-size:.84rem}.paper-list{display:grid;gap:10px}.paper{background:white;border:1px solid var(--line);border-radius:14px;padding:16px;box-shadow:0 8px 24px rgba(24,37,68,.06)}.paper h2{font-size:1.08rem;line-height:1.38;margin:0}.original{color:var(--muted);font-size:.87rem;margin:6px 0 0}.badges{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}.badge{display:inline-flex;padding:2px 8px;border-radius:999px;background:#edf2ff;color:#2346a5;font-size:.74rem;font-weight:750}.badge.correction{background:#fff3d6;color:var(--warn)}.badge.concern{background:#ffebe9;color:var(--bad)}.badge.editorial{background:#f1eafe;color:#6240a0}.badge.primary{background:#e8f6ef;color:var(--ok)}.summary{background:var(--soft);border-left:4px solid var(--brand);border-radius:8px;padding:10px 12px;font-size:.9rem}.meta{display:flex;gap:8px 14px;flex-wrap:wrap;margin-top:10px;color:var(--muted);font-size:.82rem}.ids{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px}.ids a,.ids span{font-size:.78rem;border:1px solid #ccd5e3;background:white;border-radius:7px;padding:4px 7px;text-decoration:none}.empty{display:none;text-align:center;padding:28px;background:white;border:1px dashed #aeb9ca;border-radius:12px;color:var(--muted)}.empty.visible{display:block}.small{font-size:.78rem;color:var(--muted)}footer{text-align:center;padding:20px;color:var(--muted);font-size:.78rem}@media(max-width:900px){.toolbar{position:static;grid-template-columns:1fr 1fr}.wide{grid-column:1/-1}.summary-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:560px){.toolbar{grid-template-columns:1fr}.wide,.checks{grid-column:1}.summary-grid{grid-template-columns:1fr 1fr}.actions{margin-left:0;width:100%}.btn{flex:1}}
"""

_SCRIPT = r"""
(() => {
  const esc=s=>String(s??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));
  const norm=v=>String(v||'').normalize('NFKC').toLocaleLowerCase('zh-Hant');
  const q=document.querySelector('#filter-query'),role=document.querySelector('#filter-role'),type=document.querySelector('#filter-type'),source=document.querySelector('#filter-source'),date=document.querySelector('#filter-date'),sort=document.querySelector('#filter-sort'),doi=document.querySelector('#filter-doi'),pmid=document.querySelector('#filter-pmid'),pmcid=document.querySelector('#filter-pmcid'),translated=document.querySelector('#filter-translated'),pageSize=document.querySelector('#page-size'),list=document.querySelector('#paper-list'),matched=document.querySelector('#matched-count'),pageLabel=document.querySelector('#page-label'),prev=document.querySelector('#page-prev'),next=document.querySelector('#page-next'),empty=document.querySelector('#empty-state'),reset=document.querySelector('#clear-filters'),showAll=document.querySelector('#show-all-roles');
  let data=null,filtered=[],page=1;
  const idLinks=a=>[a.doi?`<a href="https://doi.org/${esc(a.doi)}">DOI</a>`:'',a.pmid?`<a href="https://pubmed.ncbi.nlm.nih.gov/${esc(a.pmid)}/">PMID</a>`:'',a.pmcid?`<a href="https://pmc.ncbi.nlm.nih.gov/articles/${esc(a.pmcid)}/">PMCID</a>`:''].filter(Boolean).join('');
  const card=a=>{const title=a.title_zh_tw||a.title_original;const roleLabel=(data.role_labels||{})[a.curation_role]||a.curation_role;const authors=(a.authors||[]).join('、');return `<article class="paper"><h2>${esc(title)}</h2>${a.title_zh_tw?`<p class="original"><strong>原文題名：</strong>${esc(a.title_original)}</p>`:''}<div class="badges"><span class="badge ${esc(a.curation_role)}">${esc(roleLabel)}</span><span class="badge">${esc(a.article_type)}</span>${(a.sources||[]).map(x=>`<span class="badge">${esc(x)}</span>`).join('')}</div>${a.summary_zh_tw?`<div class="summary">${esc(a.summary_zh_tw)}</div>`:''}<div class="meta"><span>${esc(a.publication_date||'')}</span><span>${esc(authors||'作者未列出')}</span><span>${esc(a.canonical_id||'')}</span></div><div class="ids">${idLinks(a)||'<span>無標準識別碼</span>'}</div></article>`};
  function apply(resetPage=true){if(!data)return;const needle=norm(q.value).trim(),wantedRole=role.value,wantedType=type.value,wantedSource=source.value,wantedDate=date.value;filtered=data.articles.filter(a=>(!needle||norm([a.title_zh_tw,a.title_original,a.summary_zh_tw,(a.authors||[]).join(' '),a.doi,a.pmid,a.pmcid,a.canonical_id].join(' ')).includes(needle))&&(!wantedRole||wantedRole==='all'||a.curation_role===wantedRole)&&(!wantedType||a.article_type===wantedType)&&(!wantedSource||(a.sources||[]).includes(wantedSource))&&(!wantedDate||a.publication_date===wantedDate)&&(!doi.checked||!!a.doi)&&(!pmid.checked||!!a.pmid)&&(!pmcid.checked||!!a.pmcid)&&(!translated.checked||!!a.translated));filtered.sort((a,b)=>sort.value==='oldest'?String(a.publication_date).localeCompare(String(b.publication_date)):sort.value==='title'?String(a.title_zh_tw||a.title_original).localeCompare(String(b.title_zh_tw||b.title_original),'zh-Hant'):String(b.publication_date).localeCompare(String(a.publication_date)));if(resetPage)page=1;render();}
  function render(){const size=Number(pageSize.value)||50,totalPages=Math.max(1,Math.ceil(filtered.length/size));page=Math.min(page,totalPages);const start=(page-1)*size,end=Math.min(start+size,filtered.length),slice=filtered.slice(start,end);list.innerHTML=slice.map(card).join('');matched.textContent=String(filtered.length);pageLabel.textContent=filtered.length?`${start+1}–${end} / ${filtered.length} · 第 ${page}/${totalPages} 頁`:'0 / 0';prev.disabled=page<=1;next.disabled=page>=totalPages;empty.classList.toggle('visible',filtered.length===0);}
  function bind(el,event='change'){el.addEventListener(event,()=>apply(true));}
  fetch('browse.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error(String(r.status));return r.json()}).then(v=>{data=v;role.value=data.default_role||'all';document.querySelector('#total-count').textContent=String(data.article_count||0);for(const [k,n] of Object.entries(data.role_counts||{})){const el=document.querySelector(`[data-role-count="${k}"]`);if(el)el.textContent=String(n)};apply(true)}).catch(()=>{document.querySelector('#load-error').hidden=false;});
  bind(q,'input');for(const el of [role,type,source,date,sort,doi,pmid,pmcid,translated,pageSize])bind(el);prev.addEventListener('click',()=>{page=Math.max(1,page-1);render();scrollTo({top:document.querySelector('.result-bar').offsetTop-10,behavior:'smooth'})});next.addEventListener('click',()=>{page+=1;render();scrollTo({top:document.querySelector('.result-bar').offsetTop-10,behavior:'smooth'})});reset.addEventListener('click',()=>{q.value='';role.value=data?.default_role||'all';type.value='';source.value='';date.value='';sort.value='newest';doi.checked=pmid.checked=pmcid.checked=translated.checked=false;pageSize.value=String(data?.default_page_size||50);apply(true)});showAll.addEventListener('click',()=>{role.value='all';apply(true)});
})();
"""


def render_browse_page(publication: Any, browse: dict[str, Any]) -> str:
    edition = publication.edition
    scope = edition.get("scope") or {}
    artifacts = edition.get("artifacts") or {}
    report_name = str(artifacts.get("report_html") or "")
    report_link = (
        f'<a href="{_e(report_name)}">完整 canonical HTML</a>' if report_name else ""
    )
    role_options = '<option value="all">全部角色</option>' + "".join(
        f'<option value="{_e(key)}">{_e(label)}</option>' for key, label in ROLE_LABELS.items()
    )
    facets = browse.get("facets") or {}
    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="{_e(scope.get('journal'))} {_e(scope.get('period_label_zh_tw'))} 輕量分頁瀏覽"><title>{_e(scope.get('journal'))}｜{_e(scope.get('period_label_zh_tw'))}｜EvidenceRadar Editions</title><style>{_STYLE}</style></head><body><header class="hero"><h1>{_e(scope.get('journal'))}</h1><p>{_e(scope.get('period_label_zh_tw') or scope.get('period_key'))} · r{int(scope.get('revision') or 1):02d}</p><p class="small" style="color:#e6ebff">Pages 輕量瀏覽層；canonical edition 不因篩選或分頁而刪除。</p></header><main class="shell"><p class="notice"><strong>非破壞式 curation：</strong>大型期刊預設顯示主要內容；修正、勘誤、關切／撤回、明確社論／前言仍完整保留，可由角色篩選或「顯示全部角色」查看。</p><section class="summary-grid"><div class="metric"><strong id="total-count">{browse.get('article_count',0)}</strong><span>完整紀錄</span></div><div class="metric"><strong data-role-count="primary">{(browse.get('role_counts') or {}).get('primary',0)}</strong><span>主要內容</span></div><div class="metric"><strong data-role-count="correction">{(browse.get('role_counts') or {}).get('correction',0)}</strong><span>修正／勘誤</span></div><div class="metric"><strong data-role-count="concern">{(browse.get('role_counts') or {}).get('concern',0)}</strong><span>關切／撤回</span></div><div class="metric"><strong data-role-count="editorial">{(browse.get('role_counts') or {}).get('editorial',0)}</strong><span>社論／前言</span></div></section><section class="toolbar"><div class="field wide"><label for="filter-query">搜尋題名、作者、DOI、PMID</label><input id="filter-query" type="search" placeholder="輸入關鍵字…"></div><div class="field"><label for="filter-role">紀錄角色</label><select id="filter-role">{role_options}</select></div><div class="field"><label for="filter-type">文章類型</label><select id="filter-type"><option value="">全部類型</option>{_options(facets.get('types') or [])}</select></div><div class="field"><label for="filter-source">來源</label><select id="filter-source"><option value="">全部來源</option>{_options(facets.get('sources') or [])}</select></div><div class="field"><label for="filter-date">出版日期</label><select id="filter-date"><option value="">全部日期</option>{_options(facets.get('dates') or [])}</select></div><div class="checks"><label><input id="filter-doi" type="checkbox">有 DOI</label><label><input id="filter-pmid" type="checkbox">有 PMID</label><label><input id="filter-pmcid" type="checkbox">有 PMCID</label><label><input id="filter-translated" type="checkbox">繁中完成</label><div class="field"><label for="filter-sort">排序</label><select id="filter-sort"><option value="newest">日期：新到舊</option><option value="oldest">日期：舊到新</option><option value="title">題名</option></select></div><div class="field"><label for="page-size">每頁</label><select id="page-size"><option>25</option><option selected>50</option><option>100</option><option>200</option></select></div><div class="actions"><button class="btn" id="show-all-roles" type="button">顯示全部角色</button><button class="btn primary" id="clear-filters" type="button">重設</button></div></div></section><div class="result-bar"><span>符合條件 <strong id="matched-count">0</strong> 篇</span><span class="downloads">{report_link}<a href="edition.json">完整 JSON</a><a href="manifest.json">manifest</a><a href="browse.json">browse JSON</a></span></div><p id="load-error" class="notice" hidden>輕量索引載入失敗；請改用完整 canonical HTML／JSON。</p><section id="paper-list" class="paper-list" aria-live="polite"></section><div id="empty-state" class="empty">沒有紀錄符合目前篩選。</div><div class="pager"><button class="btn" id="page-prev" type="button">上一頁</button><strong id="page-label">0 / 0</strong><button class="btn" id="page-next" type="button">下一頁</button></div><p class="small">角色分類只依題名的明確前綴作保守判定；它是 Pages 檢視 metadata，不改 canonical article identity，也不代表研究品質評分。</p></main><footer>EvidenceRadar Editions · full archive + non-destructive curated browsing</footer><script>{_SCRIPT}</script></body></html>\n"""


def enhance_revision_pages(*, output_dir: Path, publications: Iterable[Any]) -> int:
    output = Path(output_dir)
    count = 0
    for publication in publications:
        revision_dir = output / publication.relative_path
        if not revision_dir.is_dir():
            raise ValueError(f"Pages revision directory is missing: {publication.relative_path}")
        browse = build_browse_index(publication)
        (revision_dir / "browse.json").write_text(json_text(browse), encoding="utf-8")
        (revision_dir / "index.html").write_text(
            render_browse_page(publication, browse), encoding="utf-8"
        )
        count += 1
    return count
