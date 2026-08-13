from __future__ import annotations

from html import escape
from typing import Any, Iterable


STYLE = r"""
:root {
  color-scheme: light;
  --ink: #172033;
  --muted: #5c667a;
  --line: #dbe2ee;
  --panel: #ffffff;
  --soft: #f4f7fb;
  --brand: #2457d6;
  --brand-2: #6f42c1;
  --ok: #18794e;
  --warn: #9a6700;
  --bad: #b42318;
  --shadow: 0 10px 30px rgba(24, 37, 68, .08);
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  background: #eef2f8;
  color: var(--ink);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans TC", "PingFang TC", sans-serif;
  line-height: 1.55;
}
a { color: var(--brand); text-underline-offset: .16em; }
button, input, select { font: inherit; }
.hero {
  background: linear-gradient(135deg, #10275f 0%, #244fc1 55%, #6f42c1 100%);
  color: white;
  padding: 32px max(20px, calc((100vw - 1180px) / 2));
}
.eyebrow { margin: 0 0 8px; letter-spacing: .08em; font-size: .78rem; font-weight: 750; opacity: .82; }
.hero h1 { margin: 0; font-size: clamp(1.8rem, 4vw, 3.1rem); line-height: 1.15; }
.hero .period { margin: 8px 0 0; font-size: 1.08rem; opacity: .94; }
.hero-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-top: 24px; }
.metric { padding: 12px 14px; border: 1px solid rgba(255,255,255,.22); background: rgba(255,255,255,.1); border-radius: 12px; backdrop-filter: blur(8px); }
.metric strong { display: block; font-size: 1.35rem; }
.metric span { font-size: .82rem; opacity: .82; }
.shell { width: min(1180px, calc(100% - 28px)); margin: 22px auto 60px; }
.notice { margin: 0 0 16px; padding: 14px 16px; border-radius: 12px; background: #fff8db; border: 1px solid #ecd887; color: #5d4a00; }
.notice strong { color: #493900; }
.toolbar {
  position: sticky;
  top: 0;
  z-index: 10;
  display: grid;
  grid-template-columns: minmax(240px, 2fr) repeat(3, minmax(145px, 1fr));
  gap: 10px;
  padding: 14px;
  background: rgba(255,255,255,.96);
  border: 1px solid var(--line);
  border-radius: 14px;
  box-shadow: var(--shadow);
  backdrop-filter: blur(12px);
}
.field { display: grid; gap: 5px; }
.field label { font-size: .78rem; color: var(--muted); font-weight: 700; }
.field input, .field select {
  width: 100%;
  min-height: 42px;
  border: 1px solid #bfc9d9;
  border-radius: 9px;
  background: white;
  color: var(--ink);
  padding: 8px 10px;
}
.field input:focus, .field select:focus, button:focus-visible, a:focus-visible { outline: 3px solid rgba(36,87,214,.25); outline-offset: 1px; }
.filter-row { grid-column: 1 / -1; display: flex; flex-wrap: wrap; gap: 8px 14px; align-items: center; }
.check { display: inline-flex; align-items: center; gap: 6px; color: #344054; font-size: .9rem; }
.check input { width: 17px; height: 17px; }
.actions { margin-left: auto; display: flex; gap: 8px; }
.btn { min-height: 38px; border: 1px solid #bfc9d9; border-radius: 9px; padding: 7px 12px; background: white; color: var(--ink); cursor: pointer; }
.btn:hover { border-color: var(--brand); color: var(--brand); }
.btn.primary { background: var(--brand); border-color: var(--brand); color: white; }
.result-bar { display: flex; justify-content: space-between; gap: 12px; align-items: center; margin: 18px 2px 10px; color: var(--muted); }
.result-bar strong { color: var(--ink); }
.downloads { display: flex; gap: 10px; flex-wrap: wrap; }
.downloads a { font-size: .86rem; }
.section-card { background: var(--panel); border: 1px solid var(--line); border-radius: 14px; box-shadow: var(--shadow); margin: 14px 0; overflow: hidden; }
.section-card > summary { cursor: pointer; padding: 14px 16px; font-weight: 760; }
.coverage-wrap { overflow-x: auto; padding: 0 16px 16px; }
table { width: 100%; border-collapse: collapse; font-size: .9rem; }
th, td { text-align: left; border-bottom: 1px solid var(--line); padding: 9px 8px; vertical-align: top; }
th { color: var(--muted); font-size: .78rem; text-transform: uppercase; letter-spacing: .035em; }
.status { display: inline-flex; border-radius: 999px; padding: 3px 9px; font-size: .76rem; font-weight: 800; }
.status.success { background: #e8f6ef; color: var(--ok); }
.status.partial { background: #fff3d6; color: var(--warn); }
.status.no-results { background: #eef2f8; color: #475467; }
.status.failed { background: #ffebe9; color: var(--bad); }
.status.not-attempted { background: #fff3d6; color: var(--warn); }
.paper-list { display: grid; gap: 12px; }
.paper { background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: 18px; box-shadow: var(--shadow); }
.paper[hidden] { display: none !important; }
.paper-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 14px; }
.paper h2 { margin: 0; font-size: clamp(1.05rem, 2.1vw, 1.28rem); line-height: 1.35; }
.original-title { margin: 7px 0 0; color: var(--muted); font-size: .9rem; }
.badges { display: flex; flex-wrap: wrap; gap: 6px; margin: 12px 0; }
.badge { display: inline-flex; align-items: center; min-height: 25px; padding: 3px 9px; border-radius: 999px; background: #edf2ff; color: #2346a5; font-size: .76rem; font-weight: 750; }
.badge.type { background: #f1eafe; color: #6240a0; }
.badge.source { background: #e9f6f1; color: #176b4c; }
.badge.pending { background: #fff1d6; color: #805600; }
.summary { margin: 12px 0 0; padding: 12px 14px; background: var(--soft); border-left: 4px solid var(--brand); border-radius: 8px; }
.summary .basis { display: block; color: var(--muted); font-size: .76rem; margin-top: 7px; }
.meta { display: flex; flex-wrap: wrap; gap: 7px 15px; color: var(--muted); font-size: .84rem; margin-top: 12px; }
.identifiers { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.identifier { display: inline-flex; align-items: center; border: 1px solid #ccd5e3; border-radius: 8px; padding: 5px 8px; font-size: .8rem; text-decoration: none; background: white; }
.paper details { margin-top: 12px; border-top: 1px solid var(--line); padding-top: 10px; }
.paper details summary { cursor: pointer; color: var(--brand); font-size: .86rem; font-weight: 700; }
.detail-grid { display: grid; grid-template-columns: 110px minmax(0, 1fr); gap: 7px 12px; margin-top: 10px; font-size: .84rem; }
.detail-grid dt { color: var(--muted); }
.detail-grid dd { margin: 0; overflow-wrap: anywhere; }
.empty { display: none; padding: 30px; text-align: center; border: 1px dashed #aeb9ca; border-radius: 14px; background: white; color: var(--muted); }
.empty.visible { display: block; }
footer { color: var(--muted); font-size: .8rem; text-align: center; padding: 20px; }
@media (max-width: 850px) {
  .hero-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .toolbar { position: static; grid-template-columns: 1fr 1fr; }
  .toolbar .field.search { grid-column: 1 / -1; }
}
@media (max-width: 560px) {
  .hero { padding: 24px 18px; }
  .shell { width: min(100% - 18px, 1180px); }
  .hero-grid, .toolbar { grid-template-columns: 1fr; }
  .toolbar .field.search, .filter-row { grid-column: 1; }
  .actions { margin-left: 0; width: 100%; }
  .actions .btn { flex: 1; }
  .paper-head { display: block; }
  .detail-grid { grid-template-columns: 1fr; }
}
@media print {
  body { background: white; }
  .toolbar, .downloads, .actions { display: none !important; }
  .paper, .section-card { box-shadow: none; break-inside: avoid; }
}
"""


SCRIPT = r"""
(() => {
  const q = document.querySelector('#filter-query');
  const type = document.querySelector('#filter-type');
  const source = document.querySelector('#filter-source');
  const date = document.querySelector('#filter-date');
  const sort = document.querySelector('#filter-sort');
  const doi = document.querySelector('#filter-doi');
  const pmid = document.querySelector('#filter-pmid');
  const pmcid = document.querySelector('#filter-pmcid');
  const translated = document.querySelector('#filter-translated');
  const clear = document.querySelector('#clear-filters');
  const expand = document.querySelector('#toggle-details');
  const list = document.querySelector('#paper-list');
  const cards = Array.from(list.querySelectorAll('.paper'));
  const visible = document.querySelector('#visible-count');
  const empty = document.querySelector('#empty-state');
  let detailsOpen = false;

  const norm = value => String(value || '').normalize('NFKC').toLocaleLowerCase('zh-Hant');
  const apply = () => {
    const needle = norm(q.value).trim();
    const wantedType = type.value;
    const wantedSource = source.value;
    const wantedDate = date.value;
    let shown = 0;
    for (const card of cards) {
      const ok = (!needle || norm(card.dataset.search).includes(needle))
        && (!wantedType || card.dataset.type === wantedType)
        && (!wantedSource || card.dataset.sources.split('|').includes(wantedSource))
        && (!wantedDate || card.dataset.date === wantedDate)
        && (!doi.checked || card.dataset.doi === '1')
        && (!pmid.checked || card.dataset.pmid === '1')
        && (!pmcid.checked || card.dataset.pmcid === '1')
        && (!translated.checked || card.dataset.translated === '1');
      card.hidden = !ok;
      if (ok) shown += 1;
    }
    const visibleCards = cards.filter(card => !card.hidden);
    visibleCards.sort((a, b) => {
      if (sort.value === 'oldest') return a.dataset.date.localeCompare(b.dataset.date) || a.dataset.sortTitle.localeCompare(b.dataset.sortTitle, 'zh-Hant');
      if (sort.value === 'title') return a.dataset.sortTitle.localeCompare(b.dataset.sortTitle, 'zh-Hant');
      return b.dataset.date.localeCompare(a.dataset.date) || a.dataset.sortTitle.localeCompare(b.dataset.sortTitle, 'zh-Hant');
    });
    for (const card of visibleCards) list.appendChild(card);
    visible.textContent = String(shown);
    empty.classList.toggle('visible', shown === 0);
  };

  for (const control of [q, type, source, date, sort, doi, pmid, pmcid, translated]) {
    control.addEventListener(control.tagName === 'INPUT' && control.type === 'search' ? 'input' : 'change', apply);
  }
  clear.addEventListener('click', () => {
    q.value = '';
    type.value = '';
    source.value = '';
    date.value = '';
    sort.value = 'newest';
    doi.checked = pmid.checked = pmcid.checked = translated.checked = false;
    apply();
    q.focus();
  });
  expand.addEventListener('click', () => {
    detailsOpen = !detailsOpen;
    for (const details of list.querySelectorAll('details')) details.open = detailsOpen;
    expand.textContent = detailsOpen ? '收合全部細節' : '展開全部細節';
  });
  apply();
})();
"""


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
SOURCE_LABELS = {
    "pubmed": "PubMed",
    "europe_pmc": "Europe PMC",
    "crossref": "Crossref",
    "radar_rss": "Radar 期刊來源提示",
}
STATUS_LABELS = {
    "SUCCESS": "成功",
    "NO_RESULTS": "無結果",
    "PARTIAL": "部分取得",
    "FAILED": "失敗",
    "NOT_ATTEMPTED": "未執行",
}
BASIS_LABELS = {
    "TITLE_ONLY": "依題名整理，未核實研究結果",
    "METADATA": "依書目／索引資料整理",
    "ABSTRACT": "依摘要整理",
    "FULL_TEXT": "依全文整理",
}
DATE_PRECISION_LABELS = {
    "DAY": "日期精度：日",
    "MONTH": "日期精度：月；實際日未明",
    "YEAR": "日期精度：年；實際月日未明",
}
RUN_STATUS_LABELS = {
    "COMPLETE": "來源完整",
    "PARTIAL_SOURCE_COVERAGE": "來源部分覆蓋",
    "SOURCE_ACCESS_GAP": "來源存取缺口",
    "NO_MATCHING_ARTICLES": "期間內無符合文章",
}


def _e(value: Any) -> str:
    return escape(str(value if value is not None else ""), quote=True)


def _option(value: str, label: str) -> str:
    return f'<option value="{_e(value)}">{_e(label)}</option>'


def _display_publication_date(value: Any, precision: str) -> str:
    raw = str(value or "")
    normalized = precision.upper()
    if normalized == "YEAR":
        return raw[:4]
    if normalized == "MONTH":
        return raw[:7]
    return raw


def _source_values(article: dict[str, Any]) -> list[str]:
    return sorted(
        {
            str(item.get("source"))
            for item in (article.get("source_records") or [])
            if isinstance(item, dict) and item.get("source")
        }
    )


def _identifier_links(article: dict[str, Any]) -> Iterable[str]:
    doi = str(article.get("doi") or "").strip()
    pmid = str(article.get("pmid") or "").strip()
    pmcid = str(article.get("pmcid") or "").strip()
    if doi:
        yield f'<a class="identifier" href="https://doi.org/{_e(doi)}" rel="noopener noreferrer">DOI {_e(doi)}</a>'
    if pmid:
        yield f'<a class="identifier" href="https://pubmed.ncbi.nlm.nih.gov/{_e(pmid)}/" rel="noopener noreferrer">PMID {_e(pmid)}</a>'
    if pmcid:
        yield f'<a class="identifier" href="https://pmc.ncbi.nlm.nih.gov/articles/{_e(pmcid)}/" rel="noopener noreferrer">PMCID {_e(pmcid)}</a>'


def _render_source_coverage(checks: list[dict[str, Any]]) -> str:
    rows: list[str] = []
    for check in checks:
        status = str(check.get("status") or "NOT_ATTEMPTED")
        css = status.casefold().replace("_", "-")
        total = check.get("total_available")
        total_label = "—" if total is None else str(total)
        query = str(check.get("query") or "")
        detail = str(check.get("detail") or "—")
        rows.append(
            "<tr>"
            f"<td>{_e(SOURCE_LABELS.get(str(check.get('source')), str(check.get('source'))))}</td>"
            f'<td><span class="status {_e(css)}">{_e(STATUS_LABELS.get(status, status))}</span></td>'
            f"<td>{_e(check.get('returned_count', 0))}</td>"
            f"<td>{_e(check.get('accepted_count', 0))}</td>"
            f"<td>{_e(total_label)}</td>"
            f"<td>{_e(detail)}<details><summary>查詢式</summary><code>{_e(query)}</code></details></td>"
            "</tr>"
        )
    return (
        '<details class="section-card">'
        '<summary>來源覆蓋與查詢狀態</summary>'
        '<div class="coverage-wrap"><table><thead><tr>'
        '<th>來源</th><th>狀態</th><th>取得</th><th>納入</th><th>來源總數</th><th>備註</th>'
        '</tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table></div></details>"
    )


def _render_article(article: dict[str, Any]) -> str:
    original = str(article.get("title_original") or article.get("title") or "未命名")
    translated_title = str(article.get("title_zh_tw") or "").strip()
    summary = str(article.get("summary_zh_tw") or "").strip()
    translated = bool(translated_title and summary)
    display_title = translated_title or original
    article_type = str(article.get("article_type") or "unspecified")
    date_precision = str(article.get("publication_date_precision") or "DAY").upper()
    precision_label = DATE_PRECISION_LABELS.get(date_precision, date_precision)
    sources = _source_values(article)
    source_badges = "".join(
        f'<span class="badge source">{_e(SOURCE_LABELS.get(value, value))}</span>'
        for value in sources
    )
    translation_badge = (
        '<span class="badge">繁中完成</span>'
        if translated
        else '<span class="badge pending">待繁中</span>'
    )
    author_text = "、".join(str(value) for value in (article.get("authors") or []) if value)
    identifiers = "".join(_identifier_links(article))
    identifiers_html = identifiers or '<span class="badge pending">無標準識別碼</span>'
    source_links: list[str] = []
    for record in article.get("source_records") or []:
        if not isinstance(record, dict):
            continue
        source = str(record.get("source") or "")
        url = str(record.get("url") or "")
        label = SOURCE_LABELS.get(source, source)
        if url.startswith(("https://", "http://")):
            source_links.append(
                f'<a href="{_e(url)}" rel="noopener noreferrer">{_e(label)}</a>'
            )
        elif label:
            source_links.append(_e(label))
    source_links = list(dict.fromkeys(source_links))
    translation_source = str(article.get("translation_source_url") or "")
    basis_label = BASIS_LABELS.get(
        str(article.get("translation_basis") or ""),
        str(article.get("translation_basis") or ""),
    )
    if translation_source.startswith(("https://", "http://")):
        basis_label += " · "
        basis_html = (
            f'<span class="basis">{_e(basis_label)}'
            f'<a href="{_e(translation_source)}" rel="noopener noreferrer">來源</a></span>'
        )
    else:
        basis_html = f'<span class="basis">{_e(basis_label)}</span>'
    summary_html = (
        f'<div class="summary">{_e(summary)}{basis_html}</div>'
        if summary
        else '<div class="summary">尚未提供繁中導讀；目前僅顯示原文題名。<span class="basis">出版至 Pages 前應完成繁中翻譯契約。</span></div>'
    )
    original_html = (
        f'<p class="original-title"><strong>原文題名：</strong>{_e(original)}</p>'
        if translated
        else '<p class="original-title">原文題名（尚未翻譯）</p>'
    )
    search_text = " ".join(
        [
            display_title,
            original,
            summary,
            author_text,
            str(article.get("doi") or ""),
            str(article.get("pmid") or ""),
            str(article.get("pmcid") or ""),
            article_type,
            " ".join(sources),
        ]
    )
    return (
        f'<article class="paper" data-canonical-id="{_e(article.get("canonical_id"))}" '
        f'data-search="{_e(search_text)}" data-date="{_e(article.get("publication_date"))}" '
        f'data-type="{_e(article_type)}" data-sources="{_e("|".join(sources))}" '
        f'data-doi="{1 if article.get("doi") else 0}" data-pmid="{1 if article.get("pmid") else 0}" '
        f'data-pmcid="{1 if article.get("pmcid") else 0}" data-translated="{1 if translated else 0}" '
        f'data-sort-title="{_e(display_title)}">'
        '<div class="paper-head"><div>'
        f'<h2>{_e(display_title)}</h2>{original_html}</div>'
        f'<time datetime="{_e(article.get("publication_date"))}">{_e(_display_publication_date(article.get("publication_date"), date_precision))}</time></div>'
        '<div class="badges">'
        f'{translation_badge}<span class="badge type">{_e(TYPE_LABELS.get(article_type, article_type))}</span>'
        f'<span class="badge type">{_e(precision_label)}</span>{source_badges}'
        '</div>'
        f'{summary_html}'
        '<div class="meta">'
        f'<span><strong>作者：</strong>{_e(author_text or "未列出")}</span>'
        f'<span><strong>期刊：</strong>{_e(article.get("journal"))}</span>'
        '</div>'
        f'<div class="identifiers">{identifiers_html}</div>'
        '<details><summary>識別碼、來源與永久身分</summary><dl class="detail-grid">'
        f'<dt>Canonical ID</dt><dd>{_e(article.get("canonical_id"))}</dd>'
        f'<dt>日期精度</dt><dd>{_e(precision_label)}</dd>'
        f'<dt>ISSN</dt><dd>{_e("、".join(article.get("issns") or []) or "—")}</dd>'
        f'<dt>來源連結</dt><dd>{" · ".join(source_links) if source_links else "—"}</dd>'
        '</dl></details></article>'
    )


def render_html(run: dict[str, Any]) -> str:
    scope = run.get("scope") or {}
    articles = [article for article in (run.get("articles") or []) if isinstance(article, dict)]
    checks = [check for check in (run.get("source_checks") or []) if isinstance(check, dict)]
    article_types = sorted({str(article.get("article_type") or "unspecified") for article in articles})
    sources = sorted({value for article in articles for value in _source_values(article)})
    dates = sorted({str(article.get("publication_date") or "") for article in articles if article.get("publication_date")}, reverse=True)
    translated_count = sum(1 for article in articles if article.get("title_zh_tw") and article.get("summary_zh_tw"))
    upstream = run.get("upstream_radar") or {}
    artifacts = run.get("artifacts") or {}
    translation = run.get("translation") or {}
    run_status = str(run.get("run_status") or "")
    run_status_label = RUN_STATUS_LABELS.get(run_status, run_status or "未標示")

    type_options = "".join(_option(value, TYPE_LABELS.get(value, value)) for value in article_types)
    source_options = "".join(_option(value, SOURCE_LABELS.get(value, value)) for value in sources)
    date_options = "".join(_option(value, value) for value in dates)
    cards = "".join(_render_article(article) for article in articles)
    download_links = "".join(
        f'<a href="{_e(artifacts.get(key))}" download>{_e(label)}</a>'
        for key, label in (
            ("report_html", "下載 HTML"),
            ("edition_json", "下載 JSON"),
            ("manifest_json", "下載 manifest"),
        )
        if artifacts.get(key)
    )
    semantics = (
        "這份刊物是依目前公開來源重建指定出版日期範圍，並非重播當時 Radar 曾看見的世界。"
        "後續新增索引、PMCID、修正或撤回狀態可能改變重建結果。"
    )
    html = f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="{_e(scope.get('journal'))} {_e(scope.get('period_label_zh_tw'))} 文獻刊物">
<title>{_e(scope.get('journal'))}｜{_e(scope.get('period_label_zh_tw'))}｜EvidenceRadar Editions</title>
<style>{STYLE}</style>
</head>
<body data-edition-id="{_e(run.get('edition_id'))}">
<header class="hero">
  <p class="eyebrow">EVIDENCERADAR EDITIONS · 可追溯期刊刊物</p>
  <h1>{_e(scope.get('journal'))}</h1>
  <p class="period">{_e(scope.get('period_label_zh_tw') or (str(scope.get('start_date')) + ' 至 ' + str(scope.get('end_date'))))}</p>
  <div class="hero-grid">
    <div class="metric"><strong>{len(articles)}</strong><span>去重後文章</span></div>
    <div class="metric"><strong>{translated_count}</strong><span>繁中完成</span></div>
    <div class="metric"><strong>{_e(run_status_label)}</strong><span>本次來源狀態</span></div>
    <div class="metric"><strong>r{int(scope.get('revision') or 1):02d}</strong><span>刊物修訂版</span></div>
  </div>
</header>
<main class="shell">
  <p class="notice"><strong>資料語義：</strong>{_e(semantics)}</p>
  <section class="toolbar" aria-label="文章篩選工具" data-testid="interactive-filters">
    <div class="field search"><label for="filter-query">搜尋題名、作者、DOI、PMID、摘要導讀</label><input id="filter-query" type="search" placeholder="輸入關鍵字…" autocomplete="off"></div>
    <div class="field"><label for="filter-type">文章類型</label><select id="filter-type"><option value="">全部類型</option>{type_options}</select></div>
    <div class="field"><label for="filter-source">來源</label><select id="filter-source"><option value="">全部來源</option>{source_options}</select></div>
    <div class="field"><label for="filter-date">出版日期</label><select id="filter-date"><option value="">全部日期</option>{date_options}</select></div>
    <div class="filter-row">
      <label class="check"><input id="filter-doi" type="checkbox">有 DOI</label>
      <label class="check"><input id="filter-pmid" type="checkbox">有 PMID</label>
      <label class="check"><input id="filter-pmcid" type="checkbox">有 PMCID／PMC 全文入口</label>
      <label class="check"><input id="filter-translated" type="checkbox">繁中完成</label>
      <div class="field"><label for="filter-sort">排序</label><select id="filter-sort"><option value="newest">日期：新到舊</option><option value="oldest">日期：舊到新</option><option value="title">題名</option></select></div>
      <div class="actions"><button class="btn" id="clear-filters" type="button">清除篩選</button><button class="btn primary" id="toggle-details" type="button">展開全部細節</button></div>
    </div>
  </section>
  <div class="result-bar"><span>目前顯示 <strong id="visible-count">{len(articles)}</strong> / {len(articles)} 篇</span><span class="downloads">{download_links}</span></div>
  {_render_source_coverage(checks)}
  <section class="paper-list" id="paper-list" aria-live="polite">{cards}</section>
  <div class="empty" id="empty-state">沒有文章符合目前的篩選條件。</div>
  <details class="section-card"><summary>刊物 provenance 與翻譯狀態</summary><div class="coverage-wrap"><dl class="detail-grid">
    <dt>刊物 ID</dt><dd>{_e(run.get('edition_id'))}</dd>
    <dt>重建時間</dt><dd>{_e(run.get('retrieved_at'))}</dd>
    <dt>執行狀態</dt><dd>{_e(run_status)}（{_e(run_status_label)}）</dd>
    <dt>Radar 參考版本</dt><dd>{_e(upstream.get('commit') or '未 pin')}</dd>
    <dt>Radar 設定雜湊</dt><dd>{_e(upstream.get('config_sha256') or '—')}</dd>
    <dt>翻譯狀態</dt><dd>{_e(translation.get('status') or 'NOT_REQUESTED')}（{translated_count}/{len(articles)}）</dd>
    <dt>資料範圍</dt><dd>{_e(scope.get('start_date'))} 至 {_e(scope.get('end_date'))}</dd>
  </dl></div></details>
</main>
<footer>EvidenceRadar Editions · HTML 由 canonical edition JSON 投影生成；不可在 HTML 內另加未寫回資料層的實質結論。</footer>
<script>{SCRIPT}</script>
</body>
</html>
"""
    return html
