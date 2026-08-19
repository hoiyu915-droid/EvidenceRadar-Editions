from __future__ import annotations

from collections import Counter
from html import escape
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

from . import pages_curation as base
from .serialization import json_text

SOURCE_LABELS = {
    "cambridge_core": "Cambridge Core",
    "crossref": "Crossref",
    "pubmed": "PubMed",
    "europe_pmc": "Europe PMC",
    "rsc": "RSC",
    "radar_rss": "Radar 期刊來源提示",
    "sciencedirect": "ScienceDirect",
}
TYPE_LABELS = {
    "journal-article": "期刊論文",
    "Journal Article": "期刊論文",
    "Systematic Review": "系統性回顧",
    "Meta-Analysis": "統合分析",
    "Randomized Controlled Trial": "隨機對照試驗",
    "Review": "回顧",
    "Editorial": "社論",
    "Letter": "讀者投書",
    "unspecified": "未分類",
}


def _safe_url(value: Any) -> str:
    url = str(value or "").strip()
    return url if url.startswith(("https://", "http://")) else ""


def _source_values(article: dict[str, Any]) -> list[str]:
    return sorted(
        {
            str(record.get("source"))
            for record in (article.get("source_records") or [])
            if isinstance(record, dict) and record.get("source")
        }
    )


def _doi_url(doi: str) -> str:
    return f"https://doi.org/{doi}" if doi else ""


def _is_doi_resolver(url: str, doi: str) -> bool:
    return bool(doi and url.rstrip("/").lower() == _doi_url(doi).lower())


def _publisher_search_link(doi: str) -> dict[str, str] | None:
    if not doi.lower().startswith("10.1016/"):
        return None
    return {
        "kind": "source",
        "source": "sciencedirect",
        "label": "ScienceDirect",
        "url": f"https://www.sciencedirect.com/search?qs={quote(doi, safe='')}",
    }


def _external_links(article: dict[str, Any]) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    doi = str(article.get("doi") or "").strip()

    for record in article.get("source_records") or []:
        if not isinstance(record, dict):
            continue
        url = _safe_url(record.get("url"))
        if not url or url in seen:
            continue
        source = str(record.get("source") or "")
        if source == "crossref" and _is_doi_resolver(url, doi):
            continue
        links.append(
            {
                "kind": "source",
                "source": source,
                "label": SOURCE_LABELS.get(source, source or "原文"),
                "url": url,
            }
        )
        seen.add(url)

    for value in article.get("urls") or []:
        url = _safe_url(value)
        if not url or url in seen or _is_doi_resolver(url, doi):
            continue
        links.append({"kind": "source", "source": "", "label": "原文", "url": url})
        seen.add(url)

    if not any(item.get("kind") == "source" for item in links):
        publisher_link = _publisher_search_link(doi)
        if publisher_link:
            links.append(publisher_link)
            seen.add(publisher_link["url"])

    pmid = str(article.get("pmid") or "").strip()
    pmcid = str(article.get("pmcid") or "").strip()
    standards = [
        ("doi", "DOI", _doi_url(doi)),
        ("pmid", "PubMed", f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""),
        ("pmcid", "PMC", f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/" if pmcid else ""),
    ]
    for kind, label, url in standards:
        if not url or url in seen:
            continue
        links.append({"kind": kind, "source": "", "label": label, "url": url})
        seen.add(url)
    return links


def _browse_article(article: dict[str, Any]) -> dict[str, Any]:
    original = str(article.get("title_original") or article.get("title") or "").strip()
    translated = str(article.get("title_zh_tw") or "").strip()
    external_links = _external_links(article)
    source_link = next(
        (item["url"] for item in external_links if item.get("kind") == "source"),
        "",
    )
    primary_url = source_link or (external_links[0]["url"] if external_links else "")
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
        "external_links": external_links,
        "primary_url": primary_url,
        "translated": bool(translated and article.get("summary_zh_tw")),
        "curation_role": base.classify_publication_role(original),
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
        "schema_version": "1.1",
        "artifact_type": "EvidenceRadar_Editions_CuratedBrowseIndex",
        "edition_id": edition.get("edition_id"),
        "journal": scope.get("journal"),
        "period_key": scope.get("period_key"),
        "period_label_zh_tw": scope.get("period_label_zh_tw"),
        "revision": int(scope.get("revision") or 1),
        "article_count": article_count,
        "default_role": default_role,
        "default_page_size": 50,
        "role_labels": base.ROLE_LABELS,
        "source_labels": SOURCE_LABELS,
        "type_labels": TYPE_LABELS,
        "role_counts": {key: int(role_counts.get(key, 0)) for key in base.ROLE_LABELS},
        "facets": facets,
        "articles": articles,
        "curation_semantics": (
            "Pages-only, non-destructive title-role classification. Canonical edition data are unchanged. "
            "Reader cards expose canonical source/identifier links while internal canonical IDs remain in browse JSON."
        ),
    }


SCRIPT = r"""
(() => {
  const esc=s=>String(s??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));
  const norm=v=>String(v||'').normalize('NFKC').toLocaleLowerCase('zh-Hant');
  const q=document.querySelector('#filter-query'),role=document.querySelector('#filter-role'),type=document.querySelector('#filter-type'),source=document.querySelector('#filter-source'),date=document.querySelector('#filter-date'),sort=document.querySelector('#filter-sort'),doi=document.querySelector('#filter-doi'),pmid=document.querySelector('#filter-pmid'),pmcid=document.querySelector('#filter-pmcid'),translated=document.querySelector('#filter-translated'),pageSize=document.querySelector('#page-size'),list=document.querySelector('#paper-list'),matched=document.querySelector('#matched-count'),pageLabel=document.querySelector('#page-label'),prev=document.querySelector('#page-prev'),next=document.querySelector('#page-next'),empty=document.querySelector('#empty-state'),reset=document.querySelector('#clear-filters'),showAll=document.querySelector('#show-all-roles');
  let data=null,filtered=[],page=1;
  const sourceLabel=x=>(data.source_labels||{})[x]||String(x||'').replaceAll('_',' ');
  const typeLabel=x=>(data.type_labels||{})[x]||x;
  const linkButtons=a=>{const links=(a.external_links||[]).map((x,i)=>`<a class="${i===0?'primary-link':''}" href="${esc(x.url)}" rel="noopener noreferrer">${esc(x.kind==='source'?'原文 ↗':x.label)}</a>`);return links.length?links.join(''):'<span class="no-link">未提供外部文章入口</span>';};
  const card=a=>{const title=a.title_zh_tw||a.title_original;const roleLabel=(data.role_labels||{})[a.curation_role]||a.curation_role;const authors=(a.authors||[]).join('、');const titleHtml=a.primary_url?`<a href="${esc(a.primary_url)}" rel="noopener noreferrer">${esc(title)}</a>`:esc(title);const typeBadge=a.article_type&&a.article_type!=='unspecified'?`<span class="badge">${esc(typeLabel(a.article_type))}</span>`:'';return `<article class="paper"><h2>${titleHtml}</h2>${a.title_zh_tw?`<p class="original"><strong>原文題名：</strong>${esc(a.title_original)}</p>`:''}<div class="badges"><span class="badge ${esc(a.curation_role)}">${esc(roleLabel)}</span>${typeBadge}${(a.sources||[]).map(x=>`<span class="badge">${esc(sourceLabel(x))}</span>`).join('')}</div>${a.summary_zh_tw?`<div class="summary">${esc(a.summary_zh_tw)}</div>`:''}<div class="meta"><span>${esc(a.publication_date||'')}</span><span>${esc(authors||'作者未列出')}</span></div><div class="ids">${linkButtons(a)}</div></article>`};
  function apply(resetPage=true){if(!data)return;const needle=norm(q.value).trim(),wantedRole=role.value,wantedType=type.value,wantedSource=source.value,wantedDate=date.value;filtered=data.articles.filter(a=>(!needle||norm([a.title_zh_tw,a.title_original,a.summary_zh_tw,(a.authors||[]).join(' '),a.doi,a.pmid,a.pmcid,a.canonical_id].join(' ')).includes(needle))&&(!wantedRole||wantedRole==='all'||a.curation_role===wantedRole)&&(!wantedType||a.article_type===wantedType)&&(!wantedSource||(a.sources||[]).includes(wantedSource))&&(!wantedDate||a.publication_date===wantedDate)&&(!doi.checked||!!a.doi)&&(!pmid.checked||!!a.pmid)&&(!pmcid.checked||!!a.pmcid)&&(!translated.checked||!!a.translated));filtered.sort((a,b)=>sort.value==='oldest'?String(a.publication_date).localeCompare(String(b.publication_date)):sort.value==='title'?String(a.title_zh_tw||a.title_original).localeCompare(String(b.title_zh_tw||b.title_original),'zh-Hant'):String(b.publication_date).localeCompare(String(a.publication_date)));if(resetPage)page=1;render();}
  function render(){const size=Number(pageSize.value)||50,totalPages=Math.max(1,Math.ceil(filtered.length/size));page=Math.min(page,totalPages);const start=(page-1)*size,end=Math.min(start+size,filtered.length),slice=filtered.slice(start,end);list.innerHTML=slice.map(card).join('');matched.textContent=String(filtered.length);pageLabel.textContent=filtered.length?`${start+1}–${end} / ${filtered.length} · 第 ${page}/${totalPages} 頁`:'0 / 0';prev.disabled=page<=1;next.disabled=page>=totalPages;empty.classList.toggle('visible',filtered.length===0);}
  function bind(el,event='change'){el.addEventListener(event,()=>apply(true));}
  fetch('browse.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error(String(r.status));return r.json()}).then(v=>{data=v;role.value=data.default_role||'all';document.querySelector('#total-count').textContent=String(data.article_count||0);for(const [k,n] of Object.entries(data.role_counts||{})){const el=document.querySelector(`[data-role-count="${k}"]`);if(el)el.textContent=String(n)};apply(true)}).catch(()=>{document.querySelector('#load-error').hidden=false;});
  bind(q,'input');for(const el of [role,type,source,date,sort,doi,pmid,pmcid,translated,pageSize])bind(el);prev.addEventListener('click',()=>{page=Math.max(1,page-1);render();scrollTo({top:document.querySelector('.result-bar').offsetTop-10,behavior:'smooth'})});next.addEventListener('click',()=>{page+=1;render();scrollTo({top:document.querySelector('.result-bar').offsetTop-10,behavior:'smooth'})});reset.addEventListener('click',()=>{q.value='';role.value=data?.default_role||'all';type.value='';source.value='';date.value='';sort.value='newest';doi.checked=pmid.checked=pmcid.checked=translated.checked=false;pageSize.value=String(data?.default_page_size||50);apply(true)});showAll.addEventListener('click',()=>{role.value='all';apply(true)});
})();
"""

EXTRA_STYLE = r"""
html{-webkit-text-size-adjust:100%;text-size-adjust:100%}
.paper h2{font-size:clamp(1rem,3.8vw,1.12rem);overflow-wrap:anywhere}
.paper h2 a{color:var(--ink);text-decoration:none}
.paper h2 a:hover,.paper h2 a:focus{text-decoration:underline;color:var(--brand)}
.ids a.primary-link{background:var(--brand);border-color:var(--brand);color:#fff;font-weight:750}
.ids .no-link{border:0;background:transparent;color:var(--muted);padding-left:0}
@media(max-width:560px){.paper{padding:14px}.badges{margin:8px 0}.meta{margin-top:8px}.ids{margin-top:9px}}
"""


def render_browse_page(publication: Any, browse: dict[str, Any]) -> str:
    old_script = base._SCRIPT
    try:
        base._SCRIPT = SCRIPT
        page = base.render_browse_page(publication, browse)
    finally:
        base._SCRIPT = old_script
    page = page.replace("</style>", EXTRA_STYLE + "</style>", 1)
    for source, label in SOURCE_LABELS.items():
        page = page.replace(
            f'<option value="{escape(source, quote=True)}">{escape(source)}</option>',
            f'<option value="{escape(source, quote=True)}">{escape(label)}</option>',
        )
    page = page.replace(
        '<option value="unspecified">unspecified</option>',
        '<option value="unspecified">未分類</option>',
    )
    return page


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


__all__ = ["build_browse_index", "enhance_revision_pages", "render_browse_page"]
