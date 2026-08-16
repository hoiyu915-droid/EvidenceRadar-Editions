from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .pages_v13 import build_pages_site as build_v13_pages_site
from .provider_catalog import load_provider_catalogs
from .serialization import json_text

PROVIDERS_INDEX_FILENAME = "providers.json"


def _escape(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _provider_command(provider: str, slug: str) -> str:
    return (
        "python -m evidenceradar_editions run "
        f"--provider {provider} --journal-slug {slug} "
        "--start YYYY-MM-DD --end YYYY-MM-DD --output-dir work/edition"
    )


def _page_shell(title: str, body: str, *, back_href: str, back_label: str) -> str:
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_escape(title)}</title>
<style>
:root{{color-scheme:light dark;font-family:ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
body{{margin:0;background:#f5f7f8;color:#172126}}
a{{color:#0a5b8e}}.shell{{max-width:1120px;margin:0 auto;padding:28px 20px 64px}}
.top{{display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap;margin-bottom:22px}}
.back{{text-decoration:none;font-weight:650}}h1{{margin:0;font-size:clamp(1.7rem,4vw,2.6rem)}}
.lede{{max-width:820px;color:#52616b;line-height:1.65}}.grid{{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(270px,1fr))}}
.card{{background:#fff;border:1px solid #dfe6e9;border-radius:14px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,.04)}}
.meta{{font-size:.9rem;color:#66757d}}code{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;overflow-wrap:anywhere}}
.search{{width:100%;box-sizing:border-box;padding:12px 14px;border:1px solid #cbd5da;border-radius:10px;font:inherit;background:#fff;color:#172126;margin:10px 0 18px}}
.row{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;padding:13px 0;border-top:1px solid #e6ecef;align-items:start}}
.row:first-child{{border-top:0}}.name{{font-weight:700}}.slug{{font-size:.88rem;color:#687780;margin-top:4px}}
.actions{{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}}button,.button{{border:1px solid #c4d0d5;background:#fff;color:#19313c;padding:7px 10px;border-radius:8px;text-decoration:none;cursor:pointer;font:inherit;font-size:.88rem}}
.note{{padding:12px 14px;background:#edf6fb;border:1px solid #c7dfed;border-radius:10px;line-height:1.55}}
@media (prefers-color-scheme:dark){{body{{background:#101518;color:#e6edf0}}.card,.search,button,.button{{background:#172126;color:#e6edf0;border-color:#34444c}}.lede,.meta,.slug{{color:#aab8bf}}.row{{border-color:#2d3a40}}.note{{background:#14252f;border-color:#294959}}a{{color:#78c7fa}}}}
</style>
</head>
<body><main class="shell"><div class="top"><a class="back" href="{_escape(back_href)}">← {_escape(back_label)}</a></div>{body}</main></body>
</html>"""


def _render_provider_index(catalogs: list[dict[str, Any]]) -> str:
    cards = []
    for catalog in catalogs:
        provider = str(catalog["provider"])
        count = int(catalog["journal_count"])
        cards.append(
            '<article class="card">'
            f'<h2><a href="{_escape(provider)}/">{_escape(catalog["publisher"])}</a></h2>'
            f'<p><strong>{count}</strong> 本 provider 期刊</p>'
            f'<p class="meta">範圍：{_escape(catalog["scope"])}</p>'
            f'<p class="meta">Snapshot：{_escape(catalog["observed_at"])}</p>'
            '</article>'
        )
    body = (
        '<h1>Publisher providers</h1>'
        '<p class="lede">這裡是出版社 adapter 暴露的可選期刊目錄。Provider catalog 只負責發現與選擇；真正建立 Edition 時仍只抓你指定的那一本期刊。</p>'
        f'<div class="grid">{"".join(cards)}</div>'
    )
    return _page_shell("Publisher providers", body, back_href="../", back_label="期刊總覽")


def _render_provider_page(catalog: dict[str, Any]) -> str:
    provider = str(catalog["provider"])
    rows = []
    for journal in catalog["journals"]:
        slug = str(journal["slug"])
        name = str(journal["name"])
        command = _provider_command(provider, slug)
        source_url = str(journal.get("url") or "")
        link = (
            f'<a class="button" href="{_escape(source_url)}" rel="noopener">Cambridge Core</a>'
            if source_url
            else ""
        )
        rows.append(
            f'<div class="row" data-search="{_escape((name + " " + slug).casefold())}">'
            '<div>'
            f'<div class="name">{_escape(name)}</div>'
            f'<div class="slug">{_escape(slug)}</div>'
            f'<div class="slug"><code>{_escape(command)}</code></div>'
            '</div>'
            '<div class="actions">'
            f'{link}<button type="button" data-copy="{_escape(command)}">複製指令</button>'
            '</div></div>'
        )
    count = int(catalog["journal_count"])
    body = f"""
<h1>{_escape(catalog['publisher'])}</h1>
<p class="lede"><strong>{count}</strong> 本 fully open-access journals。這是 provider discovery snapshot，不代表這 {count} 本都已建立 Edition，也不會讓 runtime 一次掃完它們。</p>
<p class="note">用法：挑一本 → 複製它的 <code>--provider {provider} --journal-slug …</code>。執行時 Cambridge adapter 只 resolve 並抓該本期刊。</p>
<p class="meta">來源快照：{_escape(catalog['observed_at'])} · <a href="../{_escape(provider)}.json">machine-readable JSON</a> · <a href="{_escape(catalog['source_url'])}" rel="noopener">Cambridge OA listing</a></p>
<input id="provider-search" class="search" type="search" placeholder="搜尋期刊名稱或 slug…" aria-label="搜尋 provider 期刊">
<div id="provider-list">{''.join(rows)}</div>
<script>
const q=document.getElementById('provider-search');
const rows=[...document.querySelectorAll('[data-search]')];
q.addEventListener('input',()=>{{const v=q.value.trim().toLocaleLowerCase();for(const row of rows)row.hidden=v&&!row.dataset.search.includes(v);}});
for(const button of document.querySelectorAll('[data-copy]'))button.addEventListener('click',async()=>{{try{{await navigator.clipboard.writeText(button.dataset.copy);button.textContent='已複製';setTimeout(()=>button.textContent='複製指令',1200);}}catch(_e){{button.textContent='請手動複製';}}}});
</script>
"""
    return _page_shell(
        str(catalog["publisher"]),
        body,
        back_href="../",
        back_label="Publisher providers",
    )


def _inject_provider_entry(path: Path, catalogs: list[dict[str, Any]]) -> None:
    page = path.read_text(encoding="utf-8")
    if 'href="providers/"' in page:
        return
    marker = '<main class="shell">'
    if marker not in page:
        raise ValueError("portal template marker is missing for provider entry")
    journal_count = sum(int(item["journal_count"]) for item in catalogs)
    names = "、".join(str(item["publisher"]) for item in catalogs)
    banner = (
        '<main class="shell"><p style="padding:13px 15px;background:#eef4fb;'
        'border:1px solid #c5d8ed;border-radius:12px">'
        '<strong>Publisher providers：</strong>'
        f'{_escape(names)} 共 {_escape(journal_count)} 本可選 provider 期刊。'
        '這些是 discovery catalog，不等於已建立 Edition。 '
        '<a href="providers/">選期刊</a></p>'
    )
    path.write_text(page.replace(marker, banner, 1), encoding="utf-8")


def _publish_provider_catalogs(
    *,
    output: Path,
    catalog_root: Path,
    links: dict[str, Any],
) -> dict[str, Any] | None:
    catalogs = load_provider_catalogs(catalog_root)
    if not catalogs:
        return None

    providers_dir = output / "providers"
    providers_dir.mkdir(parents=True, exist_ok=True)
    summaries: list[dict[str, Any]] = []
    for catalog in catalogs:
        provider = str(catalog["provider"])
        provider_dir = providers_dir / provider
        provider_dir.mkdir(parents=True, exist_ok=True)
        (provider_dir / "index.html").write_text(
            _render_provider_page(catalog), encoding="utf-8"
        )
        (providers_dir / f"{provider}.json").write_text(
            json_text(catalog), encoding="utf-8"
        )
        summaries.append(
            {
                "provider": provider,
                "publisher": catalog["publisher"],
                "scope": catalog["scope"],
                "observed_at": catalog["observed_at"],
                "journal_count": catalog["journal_count"],
                "page": f"providers/{provider}/",
                "catalog": f"providers/{provider}.json",
            }
        )

    provider_index = {
        "artifact_type": "EvidenceRadar_Editions_ProviderIndex",
        "schema_version": "1.0",
        "provider_count": len(summaries),
        "journal_count": sum(int(item["journal_count"]) for item in summaries),
        "providers": summaries,
    }
    (output / PROVIDERS_INDEX_FILENAME).write_text(
        json_text(provider_index), encoding="utf-8"
    )
    (providers_dir / "index.html").write_text(
        _render_provider_index(catalogs), encoding="utf-8"
    )
    _inject_provider_entry(output / "index.html", catalogs)

    catalog_path = output / "index.json"
    root_catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    root_catalog["publisher_providers"] = provider_index
    catalog_path.write_text(json_text(root_catalog), encoding="utf-8")

    public_base = str(links.get("base_url") or "")
    links["publisher_providers"] = provider_index
    links["publisher_providers_url"] = public_base + "providers/"
    links["publisher_providers_index_url"] = public_base + PROVIDERS_INDEX_FILENAME
    return provider_index


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
    links = build_v13_pages_site(
        output_dir=output_dir,
        repository=repository,
        editions_root=editions_root,
        archive_root=archive_root,
        catalog_root=catalog_root,
        base_url=base_url,
        require_zh_tw=require_zh_tw,
    )
    if editions_root is None or archive_root is not None or catalog_root is None:
        return links

    output = Path(output_dir)
    _publish_provider_catalogs(
        output=output,
        catalog_root=Path(catalog_root),
        links=links,
    )
    (output / "links.json").write_text(json_text(links), encoding="utf-8")
    return links


__all__ = ["PROVIDERS_INDEX_FILENAME", "build_pages_site"]
