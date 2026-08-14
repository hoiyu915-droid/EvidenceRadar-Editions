from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .journal_catalog import load_journal_registry
from .pages_v2 import STYLE, _e
from .pages_v4 import build_pages_site as build_v4_pages_site
from .serialization import json_text

EXTRA_STYLE = r"""
.filters{display:grid;grid-template-columns:minmax(260px,2fr) repeat(4,minmax(150px,1fr)) auto;gap:10px;padding:14px;background:#fff;border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow)}
.filters .wide{grid-column:span 2}.filter-note{font-size:.78rem;color:var(--muted);margin:8px 2px 0}
.shortcuts,.az{display:flex;flex-wrap:wrap;gap:7px;margin:12px 0}.shortcut,.az button{min-height:34px;padding:5px 10px;border-radius:999px;background:#fff}.shortcut.active,.az button.active{background:var(--brand);border-color:var(--brand);color:#fff}
.tag{display:inline-block;border-radius:999px;padding:2px 8px;margin:2px 4px 2px 0;font-size:.73rem;background:#eef2f8;color:#475467}.tag.category{background:#edf2ff;color:#2346a5}.tag.publisher{background:#e9f6f1;color:#176b4c}.tag.planned{background:#fff1dc;color:#934b00}
.registry-state{font-weight:750}.registry-state.planned{color:#934b00}.registry-state.active{color:#18794e}.muted-link{color:var(--muted)}
#journal-table td:nth-child(2){min-width:210px}.portal-head{display:flex;justify-content:space-between;gap:14px;align-items:flex-end;flex-wrap:wrap}.portal-head h2{margin-bottom:0}
@media(max-width:980px){.filters{grid-template-columns:1fr 1fr}.filters .wide{grid-column:1/-1}}
@media(max-width:620px){.filters{grid-template-columns:1fr}.filters .wide{grid-column:1}.portal-head{display:block}}
"""

PORTAL_SCRIPT = r"""
(() => {
  const q=document.querySelector('#journal-query');
  const category=document.querySelector('#journal-category');
  const publisher=document.querySelector('#journal-publisher');
  const month=document.querySelector('#journal-month');
  const content=document.querySelector('#journal-content');
  const oa=document.querySelector('#journal-oa');
  const clear=document.querySelector('#journal-clear');
  const rows=Array.from(document.querySelectorAll('#journal-table tbody tr'));
  const visible=document.querySelector('#journal-visible');
  const articleBox=document.querySelector('#article-results');
  const shortcuts=Array.from(document.querySelectorAll('[data-shortcut-category]'));
  const letters=Array.from(document.querySelectorAll('[data-letter]'));
  let activeLetter='';
  let articleIndex=null;
  const norm=v=>String(v||'').normalize('NFKC').toLocaleLowerCase('zh-Hant');
  const split=v=>String(v||'').split('|').filter(Boolean);
  const esc=s=>String(s||'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));

  async function loadArticles(){
    if(articleIndex!==null)return articleIndex;
    try{
      const r=await fetch('search-index.json',{cache:'no-store'});
      if(!r.ok)throw new Error(String(r.status));
      articleIndex=await r.json();
    }catch(e){articleIndex={articles:[]}}
    return articleIndex;
  }

  function setShortcutState(){
    for(const button of shortcuts){
      button.classList.toggle('active',button.dataset.shortcutCategory===category.value);
    }
    for(const button of letters){
      button.classList.toggle('active',(button.dataset.letter||'')===activeLetter);
    }
  }

  async function apply(){
    const needle=norm(q.value).trim();
    let shown=0;
    for(const row of rows){
      const categories=split(row.dataset.categories);
      const months=split(row.dataset.months);
      const selectedMonth=month.value;
      const hasAny=row.dataset.hasPublication==='1';
      const hasMonth=selectedMonth ? months.includes(selectedMonth) : hasAny;
      let contentOk=true;
      if(content.value==='has-month')contentOk=hasMonth;
      else if(content.value==='no-month')contentOk=!hasMonth;
      else if(content.value==='published')contentOk=hasAny;
      else if(content.value==='planned')contentOk=row.dataset.registryStatus==='planned';
      const ok=(!needle||norm(row.dataset.search).includes(needle))
        &&(!category.value||categories.includes(category.value))
        &&(!publisher.value||row.dataset.publisher===publisher.value)
        &&(!oa.value||row.dataset.oa===oa.value)
        &&(!activeLetter||row.dataset.letter===activeLetter)
        &&contentOk;
      row.hidden=!ok;
      if(ok)shown++;
    }
    visible.textContent=String(shown);
    setShortcutState();
    articleBox.innerHTML='';
    if(needle.length>=2){
      const idx=await loadArticles();
      const matches=(idx.articles||[])
        .filter(x=>norm([x.title_zh_tw,x.title_original,x.doi,x.pmid,x.journal].join(' ')).includes(needle))
        .slice(0,50);
      articleBox.innerHTML=matches.length
        ?'<h2>文章搜尋結果</h2>'+matches.map(x=>`<div class="result"><a href="${esc(x.url)}"><strong>${esc(x.title_zh_tw||x.title_original)}</strong></a><span class="small">${esc(x.journal)} · ${esc(x.period_key)}${x.doi?' · DOI '+esc(x.doi):''}</span></div>`).join('')
        :'<p class="empty">沒有文章符合這個關鍵字。</p>';
    }
  }

  for(const el of [q,category,publisher,month,content,oa]){
    el.addEventListener(el===q?'input':'change',apply);
  }
  clear.addEventListener('click',()=>{
    q.value='';category.value='';publisher.value='';oa.value='';content.value='';
    month.value=month.dataset.defaultMonth||'';
    activeLetter='';
    apply();q.focus();
  });
  for(const button of shortcuts){
    button.addEventListener('click',()=>{
      category.value=button.dataset.shortcutCategory===category.value?'':button.dataset.shortcutCategory;
      apply();
    });
  }
  for(const button of letters){
    button.addEventListener('click',()=>{
      const value=button.dataset.letter||'';
      activeLetter=value===activeLetter?'':value;
      apply();
    });
  }
  apply();
})();
"""

CATEGORY_FALLBACK = {
    "clinical_medicine": "臨床醫學",
    "sport_science": "運動科學",
    "sport_nutrition_fitness": "運動營養／體適能",
    "llm_research": "AI／LLM",
    "human_ai": "Human-AI／HCI",
    "interdisciplinary": "跨領域",
    "physics_astronomy": "物理／天文",
    "chemistry": "化學",
}


def _option(value: str, label: str, *, selected: bool = False) -> str:
    marker = ' selected' if selected else ''
    return f'<option value="{_e(value)}"{marker}>{_e(label)}</option>'


def _published_maps(catalog: dict[str, Any]) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    by_slug: dict[str, list[dict[str, Any]]] = defaultdict(list)
    month_keys: set[str] = set()
    for entry in catalog.get("latest_editions") or []:
        if not isinstance(entry, dict):
            continue
        slug = str(entry.get("journal_slug") or "")
        if not slug:
            continue
        by_slug[slug].append(entry)
        if entry.get("period_kind") == "month" and entry.get("period_key"):
            month_keys.add(str(entry["period_key"]))
    for values in by_slug.values():
        values.sort(key=lambda x: str(x.get("period_end") or ""), reverse=True)
    return by_slug, sorted(month_keys, reverse=True)


def _letter(name: str) -> str:
    stripped = name.strip()
    if not stripped:
        return "#"
    value = stripped[0].upper()
    return value if "A" <= value <= "Z" else "#"


def _placeholder_journal_page(journal: dict[str, Any], labels: dict[str, str]) -> str:
    categories = "、".join(labels.get(value, value) for value in journal.get("categories") or []) or "未分類"
    status = str(journal.get("status") or "active")
    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{_e(journal.get("name"))}｜EvidenceRadar Editions</title><style>{STYLE}{EXTRA_STYLE}</style></head><body><header class="hero"><h1>{_e(journal.get("name"))}</h1><p>已登記於 Editions journal registry；目前尚無已出版 edition。</p></header><main class="shell"><p><a href="../../">← 返回期刊總表</a></p><div class="section-note"><strong>狀態：</strong>{_e(status)}<br><strong>Publisher：</strong>{_e(journal.get("publisher") or "—")}<br><strong>ISSN：</strong>{_e(journal.get("issn") or "—")}<br><strong>領域：</strong>{_e(categories)}</div></main><footer>EvidenceRadar Editions</footer></body></html>\n"""


def _portal_page(
    registry: dict[str, Any],
    catalog: dict[str, Any],
    search_index: dict[str, Any],
) -> str:
    journals = [value for value in registry.get("journals") or [] if isinstance(value, dict)]
    labels = dict(CATEGORY_FALLBACK)
    labels.update(registry.get("category_labels") or {})
    by_slug, month_keys = _published_maps(catalog)
    latest_month = month_keys[0] if month_keys else ""

    publishers = sorted(
        {str(j.get("publisher") or "") for j in journals if j.get("publisher")},
        key=str.casefold,
    )
    categories = sorted(
        {str(value) for j in journals for value in (j.get("categories") or [])},
        key=lambda value: labels.get(value, value).casefold(),
    )
    oa_modes = sorted({str(j.get("oa") or "") for j in journals if j.get("oa")})
    category_counts = {
        key: sum(1 for j in journals if key in (j.get("categories") or []))
        for key in categories
    }

    rows: list[str] = []
    published_journals = 0
    month_journals = 0
    planned_journals = 0
    for journal in sorted(journals, key=lambda value: str(value.get("name") or "").casefold()):
        slug = str(journal.get("slug") or "")
        name = str(journal.get("name") or slug)
        entries = by_slug.get(slug, [])
        months = sorted(
            [value for value in entries if value.get("period_kind") == "month"],
            key=lambda value: str(value.get("period_key") or ""),
            reverse=True,
        )
        latest = months[0] if months else (entries[0] if entries else None)
        has_publication = bool(entries)
        has_latest_month = bool(latest_month and any(str(x.get("period_key")) == latest_month for x in months))
        if has_publication:
            published_journals += 1
        if has_latest_month:
            month_journals += 1
        if str(journal.get("status") or "") == "planned":
            planned_journals += 1
        month_values = "|".join(str(value.get("period_key")) for value in months if value.get("period_key"))
        categories_value = "|".join(str(value) for value in journal.get("categories") or [])
        category_badges = "".join(
            f'<span class="tag category">{_e(labels.get(str(value), str(value)))}</span>'
            for value in journal.get("categories") or []
        ) or '<span class="tag">未分類</span>'
        publisher_value = str(journal.get("publisher") or "")
        publisher_badge = f'<span class="tag publisher">{_e(publisher_value)}</span>' if publisher_value else "—"
        status = str(journal.get("status") or "active")
        status_class = "planned" if status == "planned" else "active"
        latest_period = str(latest.get("period_key") or "") if latest else "—"
        latest_status = str(latest.get("period_status") or "") if latest else ""
        latest_count = str(latest.get("article_count") or 0) if latest else "—"
        latest_detail = (
            f'<span class="badge{" mtd" if latest_status == "MTD" else ""}">{_e(latest_status or "FINAL")}</span>'
            if latest else '<span class="small">尚無刊物</span>'
        )
        search = " ".join(
            [
                name,
                slug,
                str(journal.get("issn") or ""),
                publisher_value,
                " ".join(str(value) for value in journal.get("categories") or []),
                " ".join(str(value) for value in journal.get("aliases") or []),
            ]
        )
        rows.append(
            f'<tr data-search="{_e(search)}" data-categories="{_e(categories_value)}" '
            f'data-publisher="{_e(publisher_value)}" data-months="{_e(month_values)}" '
            f'data-has-publication="{1 if has_publication else 0}" data-registry-status="{_e(status)}" '
            f'data-oa="{_e(journal.get("oa") or "")}" data-letter="{_e(_letter(name))}">'
            f'<td class="journal"><a href="journals/{_e(slug)}/">{_e(name)}</a>'
            f'<div class="small">{_e(journal.get("issn") or "ISSN 未登記")}</div></td>'
            f'<td>{category_badges}</td><td>{publisher_badge}</td>'
            f'<td><strong>{_e(latest_period)}</strong><div>{latest_detail}</div></td>'
            f'<td>{_e(latest_count)}</td>'
            f'<td><span class="registry-state {status_class}">{_e(status)}</span>'
            f'<div class="small">{_e(journal.get("oa") or "OA 未標示")}</div></td>'
            f'<td class="actions"><a href="journals/{_e(slug)}/">期刊頁</a>'
            + (f'<a href="{_e(latest.get("revision_url"))}">最新刊</a>' if latest else "")
            + '</td></tr>'
        )

    category_options = "".join(_option(value, labels.get(value, value)) for value in categories)
    publisher_options = "".join(_option(value, value) for value in publishers)
    month_options = "".join(_option(value, value, selected=value == latest_month) for value in month_keys)
    oa_options = "".join(_option(value, value) for value in oa_modes)
    shortcuts = "".join(
        f'<button type="button" class="shortcut" data-shortcut-category="{_e(value)}">{_e(labels.get(value, value))} <span class="small">{category_counts[value]}</span></button>'
        for value in categories
    )
    az = '<button type="button" data-letter="">全部</button>' + "".join(
        f'<button type="button" data-letter="{letter}">{letter}</button>' for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    )

    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="EvidenceRadar Editions 可搜尋期刊與月份目錄"><title>EvidenceRadar Editions</title><style>{STYLE}{EXTRA_STYLE}</style></head><body><header class="hero"><h1>EvidenceRadar Editions</h1><p>從領域或 Publisher 找期刊，再進入月份與 immutable revision。分類只是檢視方式，不改變期刊與 edition 的永久網址。</p></header><main class="shell"><section class="filters"><input class="wide" id="journal-query" type="search" placeholder="搜尋期刊、ISSN、文章題名或 DOI…"><select id="journal-category"><option value="">全部領域</option>{category_options}</select><select id="journal-publisher"><option value="">全部 Publisher</option>{publisher_options}</select><select id="journal-month" data-default-month="{_e(latest_month)}"><option value="">全部月份</option>{month_options}</select><select id="journal-content"><option value="">全部內容狀態</option><option value="has-month">所選月份有內容</option><option value="no-month">所選月份無內容</option><option value="published">已有任何 edition</option><option value="planned">planned</option></select><select id="journal-oa"><option value="">全部 OA 狀態</option>{oa_options}</select><button id="journal-clear" type="button">清除</button></section><p class="filter-note">月份預設為最新已出版月份；切換「所選月份有內容」可快速縮成當月實際有刊物的期刊。</p><div class="summary"><div class="metric"><strong>{len(journals)}</strong><span>已登記期刊</span></div><div class="metric"><strong>{published_journals}</strong><span>已有 edition</span></div><div class="metric"><strong>{month_journals}</strong><span>{_e(latest_month or "最新月份")} 有內容</span></div><div class="metric"><strong>{planned_journals}</strong><span>planned</span></div><div class="metric"><strong>{_e(search_index.get("article_count") or 0)}</strong><span>最新版文章索引</span></div><div class="metric"><strong id="journal-visible">{len(journals)}</strong><span>目前顯示期刊</span></div></div><h2>領域入口</h2><div class="shortcuts">{shortcuts}</div><h2>A–Z</h2><div class="az">{az}</div><div class="portal-head"><h2>期刊總表</h2><p class="small"><a href="journals.json">Journal Registry JSON</a> · <a href="index.json">Catalog JSON</a> · <a href="search-index.json">Search Index</a></p></div><div class="table-wrap"><table id="journal-table"><thead><tr><th>期刊</th><th>領域</th><th>Publisher</th><th>最新期別</th><th>文獻</th><th>Registry</th><th>入口</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div><section id="article-results" class="article-results"></section></main><footer>EvidenceRadar Editions · registered journal catalog + published immutable editions</footer><script>{PORTAL_SCRIPT}</script></body></html>\n"""


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
    links = build_v4_pages_site(
        editions_root=editions_root,
        archive_root=archive_root,
        catalog_root=catalog_root,
        output_dir=output_dir,
        repository=repository,
        base_url=base_url,
        require_zh_tw=require_zh_tw,
    )
    if catalog_root is None:
        return links

    registry = load_journal_registry(catalog_root)
    output = Path(output_dir)
    catalog_path = output / "index.json"
    search_path = output / "search-index.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    search_index = json.loads(search_path.read_text(encoding="utf-8"))

    catalog["journal_registry"] = registry
    catalog["registered_journal_count"] = len(registry.get("journals") or [])
    catalog["published_journal_count"] = int(catalog.get("journal_count") or 0)
    catalog_path.write_text(json_text(catalog), encoding="utf-8")

    registry_path = output / "journals.json"
    registry_path.write_text(json_text(registry), encoding="utf-8")

    labels = dict(CATEGORY_FALLBACK)
    labels.update(registry.get("category_labels") or {})
    for journal in registry.get("journals") or []:
        if not isinstance(journal, dict):
            continue
        slug = str(journal.get("slug") or "")
        journal_dir = output / "journals" / slug
        journal_dir.mkdir(parents=True, exist_ok=True)
        if not (journal_dir / "index.html").exists():
            (journal_dir / "index.html").write_text(
                _placeholder_journal_page(journal, labels),
                encoding="utf-8",
            )
        (journal_dir / "registry.json").write_text(
            json_text(journal),
            encoding="utf-8",
        )

    (output / "index.html").write_text(
        _portal_page(registry, catalog, search_index),
        encoding="utf-8",
    )

    public_base = str(links.get("base_url") or "")
    links["journal_registry_url"] = public_base + "journals.json"
    links["registered_journal_count"] = len(registry.get("journals") or [])
    links["published_journal_count"] = int(catalog.get("journal_count") or 0)
    (output / "links.json").write_text(json_text(links), encoding="utf-8")
    return links
