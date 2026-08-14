from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any, Iterable, Mapping

from .metadata_triage import (
    enrich_article_with_triage,
    select_triaged_projection,
    triage_counts,
)
from .pages_curation import build_browse_index
from .processing_policy import (
    JournalProcessingPolicy,
    apply_volume_guard,
    policy_for_slug,
)
from .serialization import json_text


def _e(value: Any) -> str:
    return escape(str(value if value is not None else ""), quote=True)


def build_triaged_browse_index(
    publication: Any,
    *,
    processing_policy: JournalProcessingPolicy,
    triage_policy: Mapping[str, Any],
) -> tuple[dict[str, Any], JournalProcessingPolicy, list[dict[str, Any]]]:
    browse = build_browse_index(publication)
    all_articles = [
        enrich_article_with_triage(article, policy=triage_policy)
        for article in (browse.get("articles") or [])
        if isinstance(article, dict)
    ]
    canonical_count = len(all_articles)
    effective = apply_volume_guard(
        processing_policy,
        observed_total=canonical_count,
    )
    limit = max(0, int(effective.pages_record_limit))
    projected = select_triaged_projection(
        all_articles,
        limit=limit,
        policy=triage_policy,
    )
    projected_ids = {
        str(article.get("canonical_id") or "") for article in projected
    }
    for article in all_articles:
        article["default_projected"] = (
            str(article.get("canonical_id") or "") in projected_ids
        )
    for article in projected:
        article["default_projected"] = True

    omitted = max(0, canonical_count - len(projected))
    browse["articles"] = projected
    browse["article_count"] = canonical_count
    browse["projected_article_count"] = len(projected)
    browse["projection"] = {
        "mode": "LIMITED" if omitted else "INLINE_ALL",
        "processing_mode_configured": effective.configured_mode,
        "processing_mode_effective": effective.effective_mode,
        "policy_source": effective.policy_source,
        "record_limit": limit,
        "canonical_article_count": canonical_count,
        "projected_article_count": len(projected),
        "omitted_article_count": omitted,
        "volume_guard_triggered": effective.volume_guard_triggered,
        "canonical_json_complete": True,
        "selection_basis": (
            "Deterministic title and bibliographic-metadata triage with "
            "near-duplicate suppression. It is not evidence-quality, novelty, "
            "or relevance grading."
        ),
    }
    browse["metadata_triage"] = {
        "policy_id": triage_policy.get("policy_id"),
        "basis": "TITLE_AND_BIBLIOGRAPHIC_METADATA",
        "canonical_counts": triage_counts(all_articles),
        "projected_counts": triage_counts(projected),
        "requires_later_evidence_review": True,
        "semantics": (
            "Every canonical record was assigned an operational metadata tier. "
            "Only the bounded Pages projection is loaded by default; the complete "
            "canonical edition remains unchanged."
        ),
    }
    browse["curation_semantics"] = (
        "Pages-only metadata triage and bounded browsing. Canonical edition JSON "
        "remains complete and immutable."
    )
    return browse, effective, all_articles


_STYLE = r"""
:root{color-scheme:light;--ink:#172033;--muted:#667085;--line:#dbe2ee;--soft:#f4f7fb;--brand:#2457d6;--alert:#b42318;--high:#9a4d00;--medium:#176b4c;--low:#667085}*{box-sizing:border-box}body{margin:0;background:#eef2f8;color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans TC","PingFang TC",sans-serif;line-height:1.55}a{color:var(--brand);text-underline-offset:.16em}.hero{background:linear-gradient(135deg,#10275f,#244fc1 55%,#6f42c1);color:white;padding:28px max(18px,calc((100vw - 1180px)/2))}.hero h1{margin:0;font-size:clamp(1.65rem,4vw,2.7rem)}.hero p{margin:7px 0 0}.shell{width:min(1180px,calc(100% - 24px));margin:20px auto 60px}.notice{padding:13px 15px;background:#fff8db;border:1px solid #ecd887;border-radius:12px;color:#5d4a00;margin:12px 0}.summary-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px;margin:14px 0}.metric{background:white;border:1px solid var(--line);border-radius:12px;padding:10px 12px}.metric strong{display:block;font-size:1.25rem}.metric span{font-size:.76rem;color:var(--muted)}.toolbar{display:grid;grid-template-columns:minmax(260px,2fr) repeat(4,minmax(150px,1fr));gap:10px;padding:14px;background:white;border:1px solid var(--line);border-radius:14px;position:sticky;top:0;z-index:10}.field{display:grid;gap:5px}.field label{font-size:.76rem;color:var(--muted);font-weight:700}.field input,.field select{min-height:40px;border:1px solid #bfc9d9;border-radius:9px;background:white;padding:7px 9px}.wide{grid-column:span 2}.actions{grid-column:1/-1;display:flex;gap:8px;align-items:center;flex-wrap:wrap}.btn{border:1px solid #bfc9d9;background:white;border-radius:9px;min-height:36px;padding:6px 10px;cursor:pointer}.btn.primary{background:var(--brand);color:#fff;border-color:var(--brand)}.result-bar,.pager{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;margin:14px 2px}.downloads{display:flex;gap:9px;flex-wrap:wrap;font-size:.84rem}.paper-list{display:grid;gap:10px}.paper{background:white;border:1px solid var(--line);border-radius:14px;padding:16px;box-shadow:0 8px 24px rgba(24,37,68,.06)}.paper h2{font-size:1.08rem;line-height:1.38;margin:0}.original{color:var(--muted);font-size:.87rem;margin:6px 0 0}.badges{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}.badge{display:inline-flex;padding:2px 8px;border-radius:999px;background:#edf2ff;color:#2346a5;font-size:.74rem;font-weight:750}.badge.ALERT{background:#ffebe9;color:var(--alert)}.badge.HIGH{background:#fff1dc;color:var(--high)}.badge.MEDIUM{background:#e9f6f1;color:var(--medium)}.badge.LOW{background:#eef2f6;color:var(--low)}.triage-box{background:var(--soft);border-left:4px solid var(--brand);border-radius:8px;padding:10px 12px;font-size:.88rem}.reasons{color:var(--muted);font-size:.78rem;margin-top:6px}.meta{display:flex;gap:8px 14px;flex-wrap:wrap;margin-top:10px;color:var(--muted);font-size:.82rem}.ids{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px}.ids a,.ids span{font-size:.78rem;border:1px solid #ccd5e3;background:white;border-radius:7px;padding:4px 7px;text-decoration:none}.empty{display:none;text-align:center;padding:28px;background:white;border:1px dashed #aeb9ca;border-radius:12px;color:var(--muted)}.empty.visible{display:block}.small{font-size:.78rem;color:var(--muted)}footer{text-align:center;padding:20px;color:var(--muted);font-size:.78rem}@media(max-width:980px){.toolbar{position:static;grid-template-columns:1fr 1fr}.wide{grid-column:1/-1}.summary-grid{grid-template-columns:repeat(3,1fr)}}@media(max-width:580px){.toolbar{grid-template-columns:1fr}.wide{grid-column:1}.summary-grid{grid-template-columns:1fr 1fr}}
"""

_SCRIPT = r"""
(() => {
 const esc=s=>String(s??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));
 const norm=v=>String(v||'').normalize('NFKC').toLocaleLowerCase('zh-Hant');
 const q=document.querySelector('#q'),tier=document.querySelector('#tier'),klass=document.querySelector('#klass'),rec=document.querySelector('#rec'),role=document.querySelector('#role'),sort=document.querySelector('#sort'),size=document.querySelector('#size'),list=document.querySelector('#list'),matched=document.querySelector('#matched'),pageLabel=document.querySelector('#page-label'),prev=document.querySelector('#prev'),next=document.querySelector('#next'),empty=document.querySelector('#empty'),reset=document.querySelector('#reset');
 let data=null,filtered=[],page=1;
 const labels={ALERT:'警示',HIGH:'優先',MEDIUM:'一般候選',LOW:'低優先／背景'};
 const recommendations={VERIFY_IMMEDIATELY:'立即核對',FETCH_PRIORITY:'優先抓摘要／全文',FETCH_IF_CAPACITY:'有餘裕再抓',METADATA_ONLY:'先停在 metadata'};
 const ids=a=>[a.doi?`<a href="https://doi.org/${esc(a.doi)}">DOI</a>`:'',a.pmid?`<a href="https://pubmed.ncbi.nlm.nih.gov/${esc(a.pmid)}/">PMID</a>`:'',a.pmcid?`<a href="https://pmc.ncbi.nlm.nih.gov/articles/${esc(a.pmcid)}/">PMCID</a>`:''].filter(Boolean).join('');
 const card=a=>{const t=a.metadata_triage||{},title=a.title_zh_tw||a.title_original,authors=(a.authors||[]).join('、');return `<article class="paper"><h2>${esc(title)}</h2>${a.title_zh_tw?`<p class="original"><strong>原文題名：</strong>${esc(a.title_original)}</p>`:''}<div class="badges"><span class="badge ${esc(t.tier)}">${esc(labels[t.tier]||t.tier)}</span><span class="badge">${esc(t.label_zh_tw||t.attention_class)}</span><span class="badge">${esc(a.curation_role||'primary')}</span><span class="badge">${esc(a.article_type||'unspecified')}</span></div><div class="triage-box"><strong>${esc(recommendations[t.fetch_recommendation]||t.fetch_recommendation)}</strong><div>依題名與書目 metadata 分流；需要摘要或全文才能作科學判斷。</div><div class="reasons">理由碼：${esc((t.reason_codes||[]).join(' · '))}</div></div><div class="meta"><span>${esc(a.publication_date||'')}</span><span>${esc(authors||'作者未列出')}</span><span>${esc(a.canonical_id||'')}</span></div><div class="ids">${ids(a)||'<span>無標準識別碼</span>'}</div></article>`};
 function apply(resetPage=true){if(!data)return;const needle=norm(q.value).trim();filtered=(data.articles||[]).filter(a=>{const t=a.metadata_triage||{};return(!needle||norm([a.title_zh_tw,a.title_original,(a.authors||[]).join(' '),a.doi,a.pmid,a.pmcid,a.canonical_id,(t.reason_codes||[]).join(' ')].join(' ')).includes(needle))&&(!tier.value||t.tier===tier.value)&&(!klass.value||t.attention_class===klass.value)&&(!rec.value||t.fetch_recommendation===rec.value)&&(!role.value||a.curation_role===role.value)});const rank={ALERT:0,HIGH:1,MEDIUM:2,LOW:3};filtered.sort((a,b)=>sort.value==='newest'?String(b.publication_date).localeCompare(String(a.publication_date)):sort.value==='title'?String(a.title_zh_tw||a.title_original).localeCompare(String(b.title_zh_tw||b.title_original),'zh-Hant'):(rank[a.metadata_triage?.tier]??9)-(rank[b.metadata_triage?.tier]??9)||Number(a.metadata_triage?.signal_order??999)-Number(b.metadata_triage?.signal_order??999)||String(b.publication_date).localeCompare(String(a.publication_date)));if(resetPage)page=1;render();}
 function render(){const n=Number(size.value)||50,pages=Math.max(1,Math.ceil(filtered.length/n));page=Math.min(page,pages);const start=(page-1)*n,end=Math.min(start+n,filtered.length);list.innerHTML=filtered.slice(start,end).map(card).join('');matched.textContent=String(filtered.length);pageLabel.textContent=filtered.length?`${start+1}–${end} / ${filtered.length} · 第 ${page}/${pages} 頁`:'0 / 0';prev.disabled=page<=1;next.disabled=page>=pages;empty.classList.toggle('visible',filtered.length===0)}
 fetch('browse.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error(String(r.status));return r.json()}).then(v=>{data=v;const classes=[...new Set((v.articles||[]).map(a=>a.metadata_triage?.attention_class).filter(Boolean))].sort(),roles=[...new Set((v.articles||[]).map(a=>a.curation_role).filter(Boolean))].sort();klass.innerHTML='<option value="">全部類別</option>'+classes.map(x=>`<option>${esc(x)}</option>`).join('');role.innerHTML='<option value="">全部角色</option>'+roles.map(x=>`<option>${esc(x)}</option>`).join('');apply(true)}).catch(()=>document.querySelector('#load-error').hidden=false);
 for(const el of [q,tier,klass,rec,role,sort,size])el.addEventListener(el===q?'input':'change',()=>apply(true));prev.addEventListener('click',()=>{page=Math.max(1,page-1);render()});next.addEventListener('click',()=>{page+=1;render()});reset.addEventListener('click',()=>{q.value='';tier.value='';klass.value='';rec.value='';role.value='';sort.value='priority';size.value='50';apply(true)});
})();
"""


def render_triaged_revision_page(publication: Any, browse: Mapping[str, Any]) -> str:
    edition = publication.edition
    scope = edition.get("scope") or {}
    projection = browse.get("projection") or {}
    counts = (browse.get("metadata_triage") or {}).get("canonical_counts") or {}
    tiers = counts.get("by_tier") or {}
    artifacts = edition.get("artifacts") or {}
    report_name = str(artifacts.get("report_html") or "")
    report_link = (
        f'<a href="{_e(report_name)}">完整 canonical HTML</a>'
        if report_name
        else ""
    )
    omitted = int(projection.get("omitted_article_count") or 0)
    selection_note = (
        f"此頁載入 {projection.get('projected_article_count',0)} / "
        f"{projection.get('canonical_article_count',0)} 筆；其餘 {omitted} 筆仍在完整 canonical JSON。"
        if omitted
        else "此期所有 canonical records 都在瀏覽投影內。"
    )
    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="{_e(scope.get('journal'))} metadata triage"><title>{_e(scope.get('journal'))}｜metadata triage｜EvidenceRadar Editions</title><style>{_STYLE}</style></head><body><header class="hero"><h1>{_e(scope.get('journal'))}</h1><p>{_e(scope.get('period_label_zh_tw') or scope.get('period_key'))} · r{int(scope.get('revision') or 1):02d}</p><p class="small" style="color:#e6ebff">metadata triage v1 · canonical edition 不改寫</p></header><main class="shell"><p class="notice"><strong>這是候選分流，不是論文評分：</strong>{_e(selection_note)} 排序只看題名、article type、識別碼與來源 metadata；沒讀摘要／全文，就不宣稱 evidence quality、novelty 或結果可信度。</p><section class="summary-grid"><div class="metric"><strong>{projection.get('canonical_article_count',0)}</strong><span>canonical records</span></div><div class="metric"><strong>{projection.get('projected_article_count',0)}</strong><span>預設投影</span></div><div class="metric"><strong>{tiers.get('ALERT',0)}</strong><span>警示</span></div><div class="metric"><strong>{tiers.get('HIGH',0)}</strong><span>優先候選</span></div><div class="metric"><strong>{tiers.get('MEDIUM',0)}</strong><span>一般候選</span></div><div class="metric"><strong>{tiers.get('LOW',0)}</strong><span>低優先／背景</span></div></section><section class="toolbar"><div class="field wide"><label for="q">搜尋題名、作者、識別碼或理由碼</label><input id="q" type="search" placeholder="輸入關鍵字…"></div><div class="field"><label for="tier">Triage tier</label><select id="tier"><option value="">全部層級</option><option>ALERT</option><option>HIGH</option><option>MEDIUM</option><option>LOW</option></select></div><div class="field"><label for="klass">候選類別</label><select id="klass"><option value="">全部類別</option></select></div><div class="field"><label for="rec">後續動作</label><select id="rec"><option value="">全部建議</option><option>VERIFY_IMMEDIATELY</option><option>FETCH_PRIORITY</option><option>FETCH_IF_CAPACITY</option><option>METADATA_ONLY</option></select></div><div class="field"><label for="role">出版角色</label><select id="role"><option value="">全部角色</option></select></div><div class="actions"><div class="field"><label for="sort">排序</label><select id="sort"><option value="priority">Triage 優先</option><option value="newest">日期新到舊</option><option value="title">題名</option></select></div><div class="field"><label for="size">每頁</label><select id="size"><option>25</option><option selected>50</option><option>100</option><option>200</option></select></div><button class="btn primary" id="reset" type="button">重設</button></div></section><div class="result-bar"><span>符合條件 <strong id="matched">0</strong> 篇</span><span class="downloads">{report_link}<a href="edition.json">完整 JSON</a><a href="manifest.json">manifest</a><a href="browse.json">triage browse JSON</a><a href="../../../../metadata-triage/">全站 triage</a></span></div><p id="load-error" class="notice" hidden>triage browse JSON 載入失敗；請改用完整 canonical JSON。</p><section id="list" class="paper-list" aria-live="polite"></section><div id="empty" class="empty">沒有紀錄符合目前篩選。</div><div class="pager"><button class="btn" id="prev" type="button">上一頁</button><strong id="page-label">0 / 0</strong><button class="btn" id="next" type="button">下一頁</button></div><p class="small">理由碼是 deterministic metadata heuristics。`FETCH_PRIORITY` 只代表值得進一步取得摘要／全文，不代表研究結論成立。</p></main><footer>EvidenceRadar Editions · metadata triage + immutable canonical archive</footer><script>{_SCRIPT}</script></body></html>\n"""


def write_triaged_revision_pages(
    *,
    output_dir: Path,
    publications: Iterable[Any],
    catalog_root: Path | str,
    processing_catalog: Mapping[str, Any],
    triage_policy: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    output = Path(output_dir)
    stats = {
        "revision_count": 0,
        "limited_revision_count": 0,
        "canonical_article_count_all_revisions": 0,
        "projected_article_count_all_revisions": 0,
        "omitted_article_count_all_revisions": 0,
    }
    results: dict[str, dict[str, Any]] = {}
    for publication in publications:
        revision_dir = output / publication.relative_path
        if not revision_dir.is_dir():
            raise ValueError(
                f"Pages revision directory is missing: {publication.relative_path}"
            )
        processing = policy_for_slug(
            publication.journal_slug,
            catalog_root=catalog_root,
            catalog=processing_catalog,
        )
        browse, effective, all_articles = build_triaged_browse_index(
            publication,
            processing_policy=processing,
            triage_policy=triage_policy,
        )
        (revision_dir / "browse.json").write_text(
            json_text(browse), encoding="utf-8"
        )
        (revision_dir / "index.html").write_text(
            render_triaged_revision_page(publication, browse),
            encoding="utf-8",
        )
        publication_id = str(
            publication.edition.get("publication_id")
            or publication.edition.get("edition_id")
            or f"{publication.journal_slug}:{publication.period_key}:r{publication.revision}"
        )
        results[publication_id] = {
            "publication": publication,
            "browse": browse,
            "effective_processing_policy": effective,
            "all_articles": all_articles,
        }
        projection = browse["projection"]
        stats["revision_count"] += 1
        stats["limited_revision_count"] += int(
            projection["omitted_article_count"] > 0
        )
        stats["canonical_article_count_all_revisions"] += int(
            projection["canonical_article_count"]
        )
        stats["projected_article_count_all_revisions"] += int(
            projection["projected_article_count"]
        )
        stats["omitted_article_count_all_revisions"] += int(
            projection["omitted_article_count"]
        )
    return stats, results
