from __future__ import annotations

import html
import json
from typing import Any, Mapping


def _json_for_script(value: Any) -> str:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def render_editorial_shortlist_page(
    shortlist: Mapping[str, Any],
) -> str:
    counts = shortlist.get("counts") or {}
    items = list(shortlist.get("items") or [])
    payload = _json_for_script(items)
    binding = html.escape(str(shortlist.get("shortlist_binding_sha256") or ""))
    policy_id = html.escape(str(shortlist.get("policy_id") or ""))
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>EvidenceRadar Editions — Editorial Shortlist</title>
<style>
:root{{--ink:#18212f;--muted:#667085;--line:#d8dee9;--paper:#f6f8fb;--card:#fff;--blue:#2457d6;--amber:#9a5a00;--gray:#596273;--red:#a2261d}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
.shell{{max-width:1180px;margin:auto;padding:28px 18px 60px}} h1{{font-size:clamp(28px,4vw,48px);line-height:1.05;margin:0 0 12px}}
.lede{{max-width:900px;color:var(--muted);font-size:17px}} .notice{{padding:14px 16px;border:1px solid #f0c36d;background:#fff8e8;border-radius:12px;margin:18px 0}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:12px;margin:20px 0}}
.metric{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:15px}} .metric strong{{display:block;font-size:28px}}
.controls{{display:grid;grid-template-columns:2fr repeat(3,minmax(150px,1fr));gap:10px;position:sticky;top:0;background:rgba(246,248,251,.96);padding:12px 0;z-index:2}}
input,select{{width:100%;padding:11px 12px;border:1px solid var(--line);border-radius:10px;background:white;color:var(--ink)}}
.list{{display:grid;gap:12px;margin-top:14px}} .item{{background:white;border:1px solid var(--line);border-radius:14px;padding:16px}}
.topline{{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:7px}} .badge{{font-size:12px;font-weight:750;padding:3px 8px;border-radius:999px;background:#eef2f7;color:var(--gray)}}
.badge.fetch{{background:#e8efff;color:var(--blue)}} .badge.hold{{background:#fff1d7;color:var(--amber)}} .badge.integrity{{background:#ffe8e5;color:var(--red)}}
.title{{font-size:18px;font-weight:750;margin:4px 0}} .meta,.reasons{{color:var(--muted);font-size:13px}} a{{color:var(--blue)}} code{{font-size:12px;word-break:break-all}}
.footer{{margin-top:30px;color:var(--muted);font-size:13px}} @media(max-width:760px){{.controls{{grid-template-columns:1fr;position:static}}}}
</style>
</head>
<body>
<main class="shell">
<h1>Editorial Shortlist</h1>
<p class="lede">從完整 canonical metadata 與 precision-hardened prefetch triage 中，建立一個小型、可稽核的摘要取得候選集。這一頁不評研究品質，也沒有讀摘要或全文。</p>
<p class="notice"><strong>界線：</strong><code>FETCH_NOW</code> 只表示較早安排摘要取得；不表示研究有效、新穎、相關、可改變決策或已被核實。</p>
<section class="grid">
<div class="metric"><span>Canonical</span><strong>{int(counts.get("canonical_article_count") or 0):,}</strong></div>
<div class="metric"><span>FETCH_NOW</span><strong>{int(counts.get("fetch_now_count") or 0):,}</strong></div>
<div class="metric"><span>HOLD_RESERVE</span><strong>{int(counts.get("hold_reserve_count") or 0):,}</strong></div>
<div class="metric"><span>完整性維護</span><strong>{int(counts.get("integrity_attention_count") or 0):,}</strong></div>
</section>
<p><a href="editorial-shortlist.json">shortlist JSON</a> · <a href="abstract-fetch-plan.json">bounded abstract fetch plan</a> · <a href="editorial-shortlist-policy.json">policy</a></p>
<section class="controls">
<input id="q" type="search" placeholder="搜尋題名、期刊、理由">
<select id="route"><option value="">全部 route</option><option>FETCH_NOW</option><option>HOLD_RESERVE</option><option>CATALOG_ONLY</option></select>
<select id="path"><option value="">全部 evidence path</option></select>
<select id="journal"><option value="">全部期刊</option></select>
</section>
<p id="status" class="meta"></p>
<section id="list" class="list"></section>
<footer class="footer">Policy <code>{policy_id}</code> · binding <code>{binding}</code></footer>
</main>
<script>
const ITEMS={payload};
const $=id=>document.getElementById(id);
const escapeText=value=>String(value??"");
const pathValues=[...new Set(ITEMS.map(x=>x.primary_path).filter(Boolean))].sort();
const journalValues=[...new Set(ITEMS.map(x=>x.journal).filter(Boolean))].sort((a,b)=>a.localeCompare(b));
for(const value of pathValues){{const o=document.createElement("option");o.value=o.textContent=value;$("path").append(o)}}
for(const value of journalValues){{const o=document.createElement("option");o.value=o.textContent=value;$("journal").append(o)}}
function add(parent,tag,text,cls){{const el=document.createElement(tag);if(cls)el.className=cls;el.textContent=escapeText(text);parent.append(el);return el}}
function render(){{
 const query=$("q").value.trim().toLowerCase(), route=$("route").value, path=$("path").value, journal=$("journal").value;
 const rows=ITEMS.filter(x=>{{
  if(route && x.editorial_route!==route)return false;
  if(path && x.primary_path!==path)return false;
  if(journal && x.journal!==journal)return false;
  const hay=[x.title_original,x.title_zh_tw,x.journal,x.primary_path,...(x.decision_reasons||[])].join(" ").toLowerCase();
  return !query||hay.includes(query);
 }});
 $("list").replaceChildren(); $("status").textContent=`顯示 ${{rows.length}} / ${{ITEMS.length}} 筆`;
 for(const row of rows){{
  const card=document.createElement("article");card.className="item";
  const top=document.createElement("div");top.className="topline";card.append(top);
  const badge=add(top,"span",row.editorial_route,"badge "+(row.editorial_route==="FETCH_NOW"?"fetch":row.editorial_route==="HOLD_RESERVE"?"hold":""));
  if(row.integrity_attention)add(top,"span","RECORD_MAINTENANCE","badge integrity");
  add(top,"span",row.primary_path,"badge");
  add(top,"span",row.primary_category,"badge");
  add(card,"div",row.title_zh_tw||row.title_original,"title");
  if(row.title_zh_tw && row.title_original!==row.title_zh_tw)add(card,"div",row.title_original,"meta");
  add(card,"div",`${{row.journal||""}} · ${{row.publication_date||""}} · operational prefetch score ${{row.prefetch_score??""}}`,"meta");
  add(card,"div",(row.decision_reasons||[]).join(" · "),"reasons");
  const links=document.createElement("div");links.className="meta";
  if(row.edition_url){{const a=document.createElement("a");a.href=row.edition_url;a.textContent="edition";links.append(a)}}
  const urls=row.source_urls||[];if(urls.length){{if(links.childNodes.length)links.append(" · ");const a=document.createElement("a");a.href=urls[0];a.rel="noopener";a.textContent="source";links.append(a)}}
  card.append(links);$("list").append(card);
 }}
}}
for(const id of ["q","route","path","journal"])$(id).addEventListener("input",render);
render();
</script>
</body>
</html>"""


__all__ = ["render_editorial_shortlist_page"]
