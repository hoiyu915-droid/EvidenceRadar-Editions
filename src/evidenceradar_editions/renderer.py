from __future__ import annotations

import html
import json
from collections import Counter
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlsplit


def _escape(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def _safe_url(value: object) -> str:
    text = str(value or "").strip()
    try:
        parsed = urlsplit(text)
    except ValueError:
        return ""
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.netloc:
        return ""
    return text


def _links(values: Iterable[object]) -> str:
    links: list[str] = []
    for index, value in enumerate(values, start=1):
        url = _safe_url(value)
        if not url:
            continue
        label = "DOI" if "doi.org" in url else "來源"
        links.append(
            f'<a class="source-link" href="{_escape(url)}" target="_blank" '
            f'rel="noopener noreferrer">{label} {index}</a>'
        )
    return " ".join(links) or '<span class="muted">未提供公開來源連結</span>'


def _badge(value: str, css_class: str = "") -> str:
    return f'<span class="badge {_escape(css_class)}">{_escape(value)}</span>'


def render_edition(edition: dict[str, Any], sources: dict[str, Any]) -> str:
    collection = edition["collection"]
    period = edition["period"]
    articles = edition.get("articles", [])
    receipts = sources.get("receipts", [])
    source_status = Counter(str(item.get("status") or "UNKNOWN") for item in receipts)
    study_counts = Counter(
        design
        for article in articles
        for design in article.get("study_designs", [])
    )
    oa_count = len([item for item in articles if item.get("oa_status") == "YES"])
    source_rows = "".join(
        "<tr>"
        f'<td><code>{_escape(receipt.get("source"))}</code></td>'
        f'<td>{_badge(str(receipt.get("status") or "UNKNOWN"), str(receipt.get("status") or "").casefold())}</td>'
        f'<td>{int(receipt.get("returned_count") or 0)}</td>'
        f'<td>{int(receipt.get("request_count") or 0)}</td>'
        f'<td><details><summary>查詢</summary><code>{_escape(receipt.get("query"))}</code></details></td>'
        "</tr>"
        for receipt in receipts
    )

    cards: list[str] = []
    for index, article in enumerate(articles, start=1):
        title = str(article.get("title") or "Untitled record")
        authors = ", ".join(str(value) for value in article.get("authors", [])) or "作者資料未提供"
        designs = "".join(_badge(str(value), "study") for value in article.get("study_designs", []))
        types = "".join(_badge(str(value), "type") for value in article.get("article_types", []))
        source_badges = "".join(_badge(str(value), "source") for value in article.get("sources", []))
        precision = str(article.get("publication_date_precision") or "UNKNOWN")
        publication_label = str(article.get("publication_date") or "")
        if precision != "DAY":
            publication_label = f"{publication_label} ({precision.lower()} precision)"
        identifiers = " · ".join(
            value
            for value in (
                f"DOI {article.get('doi')}" if article.get("doi") else "",
                f"PMID {article.get('pmid')}" if article.get("pmid") else "",
                f"PMCID {article.get('pmcid')}" if article.get("pmcid") else "",
            )
            if value
        ) or "沒有 DOI／PMID／PMCID"
        abstract = str(article.get("abstract") or "")
        search_text = " ".join(
            [
                title,
                authors,
                str(article.get("journal") or ""),
                identifiers,
                " ".join(article.get("article_types", [])),
                " ".join(article.get("study_designs", [])),
                " ".join(article.get("sources", [])),
                abstract,
            ]
        ).casefold()
        primary_url = next(
            (url for url in (_safe_url(value) for value in article.get("urls", [])) if url),
            "",
        )
        title_html = _escape(title)
        if primary_url:
            title_html = (
                f'<a href="{_escape(primary_url)}" target="_blank" '
                f'rel="noopener noreferrer">{title_html}</a>'
            )
        cards.append(
            f'<article class="paper-card" data-canonical-id="{_escape(article.get("canonical_id"))}" '
            f'data-search="{_escape(search_text)}" '
            f'data-oa="{_escape(article.get("oa_status"))}" '
            f'data-designs="{_escape("|".join(article.get("study_designs", [])))}">'
            '<div class="card-top">'
            f'<span class="rank">#{index:03d}</span>'
            f'{_badge(str(article.get("oa_status") or "UNKNOWN"), "oa")}'
            f'{source_badges}{designs}{types}'
            '</div>'
            f'<h2>{title_html}</h2>'
            f'<p class="authors">{_escape(authors)}</p>'
            '<dl class="metadata">'
            f'<div><dt>期刊</dt><dd>{_escape(article.get("journal"))}</dd></div>'
            f'<div><dt>出版日期</dt><dd>{_escape(publication_label)}</dd></div>'
            f'<div><dt>識別碼</dt><dd>{_escape(identifiers)}</dd></div>'
            f'<div><dt>來源</dt><dd>{_links(article.get("urls", []))}</dd></div>'
            '</dl>'
            + (
                '<details class="abstract"><summary>摘要／來源文字</summary>'
                f'<p>{_escape(abstract)}</p></details>'
                if abstract
                else '<p class="muted">來源未提供摘要。</p>'
            )
            + '</article>'
        )

    if not cards:
        cards.append(
            '<section class="empty"><h2>這個範圍沒有符合的記錄</h2>'
            '<p>這表示已啟用來源在此次查詢中沒有留下符合期刊與日期條件的候選；'
            '請同時查看來源狀態，NO_RESULTS 與 FAILED 是不同事情。</p></section>'
        )

    edition_json = json.dumps(
        {
            "edition_id": edition["edition_id"],
            "article_count": edition["article_count"],
            "status": edition["status"],
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")
    design_options = "".join(
        f'<option value="{_escape(name)}">{_escape(name)} ({count})</option>'
        for name, count in sorted(study_counts.items())
    )
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{_escape(collection['name'])} · {_escape(period['start'])}–{_escape(period['end'])} · EvidenceRadar Editions</title>
<style>
:root{{--bg:#f5f7fb;--panel:#fff;--text:#172033;--muted:#667085;--line:#d9dfeb;--accent:#3157c8;--accent2:#6e45c6;--good:#147d64;--warn:#b54708;--bad:#b42318;--chip:#edf2ff}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font:15px/1.62 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}} a{{color:var(--accent);text-decoration-thickness:.08em;text-underline-offset:.15em}} .wrap{{width:min(1180px,calc(100% - 28px));margin:auto}} header{{background:linear-gradient(125deg,#162b72,#47318d);color:#fff;padding:54px 0 36px}} .eyebrow{{font-weight:800;letter-spacing:.08em;text-transform:uppercase;opacity:.82}} h1{{font-size:clamp(2rem,5vw,4rem);line-height:1.05;margin:.35rem 0}} header p{{max-width:850px;font-size:1.06rem;opacity:.9}} .status{{display:flex;gap:8px;flex-wrap:wrap}} main{{padding:28px 0 64px}} .summary-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-top:-48px}} .metric,.panel,.paper-card,.empty{{background:var(--panel);border:1px solid var(--line);border-radius:16px;box-shadow:0 8px 28px rgba(30,43,77,.07)}} .metric{{padding:18px}} .metric strong{{display:block;font-size:1.9rem}} .metric span{{color:var(--muted)}} .panel{{padding:20px;margin-top:18px}} .notice{{border-left:5px solid var(--accent2)}} .controls{{display:grid;grid-template-columns:1fr 220px 160px;gap:10px}} input,select{{width:100%;padding:12px 14px;border:1px solid var(--line);border-radius:10px;background:var(--panel);color:var(--text);font:inherit}} table{{width:100%;border-collapse:collapse}} th,td{{text-align:left;padding:10px;border-bottom:1px solid var(--line);vertical-align:top}} code{{white-space:pre-wrap;overflow-wrap:anywhere}} #results{{display:grid;gap:14px;margin-top:18px}} .paper-card{{padding:22px}} .paper-card h2{{font-size:1.25rem;line-height:1.35;margin:.6rem 0}} .card-top{{display:flex;gap:6px;flex-wrap:wrap;align-items:center}} .rank{{font-variant-numeric:tabular-nums;color:var(--muted);font-weight:750}} .badge{{display:inline-flex;align-items:center;border-radius:999px;padding:3px 9px;background:var(--chip);font-size:.76rem;font-weight:750}} .badge.success{{background:#d9f2e8;color:#075c48}} .badge.no_results{{background:#eef2f6;color:#475467}} .badge.failed{{background:#fee4e2;color:#912018}} .badge.oa{{background:#e8f7ef;color:#176a51}} .badge.source{{background:#eef0ff;color:#3730a3}} .badge.study{{background:#f4ebff;color:#6941c6}} .badge.type{{background:#fff3d6;color:#8a4b08}} .authors,.muted{{color:var(--muted)}} .metadata{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px 18px}} .metadata div{{display:grid;grid-template-columns:90px 1fr;gap:8px}} dt{{font-weight:750}} dd{{margin:0;overflow-wrap:anywhere}} .source-link{{display:inline-block;margin:0 5px 5px 0}} details.abstract{{margin-top:12px}} footer{{color:var(--muted);padding:22px 0 44px}} .hidden{{display:none!important}} .empty{{padding:30px;text-align:center}} @media(max-width:780px){{.summary-grid{{grid-template-columns:repeat(2,1fr)}}.controls{{grid-template-columns:1fr}}.metadata{{grid-template-columns:1fr}}table{{display:block;overflow-x:auto}}}} @media(prefers-color-scheme:dark){{:root{{--bg:#0d1220;--panel:#151c2c;--text:#edf1f8;--muted:#aab4c6;--line:#303b50;--chip:#243255}}header{{background:linear-gradient(125deg,#14245c,#392568)}}a{{color:#9db8ff}}}}
</style>
</head>
<body data-edition-id="{_escape(edition['edition_id'])}">
<header><div class="wrap"><div class="eyebrow">EvidenceRadar Editions</div><h1>{_escape(collection['name'])}</h1><p>{_escape(period['start'])} 至 {_escape(period['end'])} · {_escape(period['timezone'])}</p><div class="status">{_badge(edition['status'], edition['status'].casefold())}{_badge('current-source reconstruction')}{_badge(f"retrieved {edition['retrieved_at']}")}</div></div></header>
<main class="wrap">
<section class="summary-grid" aria-label="摘要"><div class="metric"><strong>{len(articles)}</strong><span>去重後文獻</span></div><div class="metric"><strong>{oa_count}</strong><span>OA metadata = YES</span></div><div class="metric"><strong>{source_status.get('SUCCESS',0)}</strong><span>成功來源</span></div><div class="metric"><strong>{source_status.get('FAILED',0)}</strong><span>失敗來源</span></div></section>
<section class="panel notice"><h2>時間與證據語義</h2><p>這份 edition 是在 <strong>{_escape(edition['retrieved_at'])}</strong> 重新查詢目前的原始來源，以重建歷史出版區間。它不表示 Radar 在當時實際看見的世界，也不把 metadata、摘要或搜尋命中自動升格為已核實科學結論。</p></section>
<section class="panel"><h2>篩選</h2><div class="controls"><input id="search" type="search" placeholder="搜尋題名、作者、摘要、DOI、來源…" aria-label="搜尋"><select id="design"><option value="">所有研究設計</option>{design_options}</select><select id="oa"><option value="">所有 OA 狀態</option><option value="YES">OA：YES</option><option value="UNKNOWN">OA：UNKNOWN</option><option value="NO">OA：NO</option></select></div><p id="count" class="muted" aria-live="polite"></p></section>
<section class="panel"><h2>來源執行紀錄</h2><table><thead><tr><th>來源</th><th>狀態</th><th>原始記錄</th><th>請求</th><th>查詢</th></tr></thead><tbody>{source_rows}</tbody></table></section>
<section id="results">{''.join(cards)}</section>
<section class="panel"><h2>Provenance</h2><pre><code>{_escape(json.dumps(edition.get('provenance', {}), ensure_ascii=False, indent=2, sort_keys=True))}</code></pre></section>
<script type="application/json" id="edition-summary">{edition_json}</script>
<script>
(()=>{{const cards=[...document.querySelectorAll('.paper-card')];const q=document.querySelector('#search');const d=document.querySelector('#design');const o=document.querySelector('#oa');const count=document.querySelector('#count');function apply(){{const term=q.value.trim().toLocaleLowerCase();let shown=0;for(const card of cards){{const okTerm=!term||card.dataset.search.includes(term);const okDesign=!d.value||(card.dataset.designs||'').split('|').includes(d.value);const okOa=!o.value||card.dataset.oa===o.value;const visible=okTerm&&okDesign&&okOa;card.classList.toggle('hidden',!visible);if(visible)shown++;}}count.textContent=`顯示 ${{shown}} / ${{cards.length}} 篇`;}}q.addEventListener('input',apply);d.addEventListener('change',apply);o.addEventListener('change',apply);apply();}})();
</script>
</main>
<footer class="wrap">EvidenceRadar Editions · Source records remain subject to their original terms. This report is research discovery infrastructure, not medical advice.</footer>
</body></html>"""
