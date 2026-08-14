from __future__ import annotations

import argparse
import html
import json
import os
import shutil
from pathlib import Path
from typing import Any, Mapping

from .abstract_acquisition import DISPOSITION_FILENAME, MANIFEST_FILENAME, RECEIPTS_FILENAME, acquire_plan, delete_payload_vault, validate_payload_vault, validate_plan
from .serialization import json_text
from .utils import sha256_file, utc_now_iso

PUBLIC_RECEIPTS_FILENAME = "abstract-acquisition.json"
PUBLIC_PAGE_FILENAME = "abstract-acquisition.html"


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _assert_no_abstract_text(value: Any) -> None:
    forbidden = {"abstract", "abstract_text", "abstractText", "payload_text", "raw_response"}
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key) in forbidden:
                raise ValueError(f"public acquisition artifact contains forbidden field: {key}")
            _assert_no_abstract_text(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_abstract_text(child)


def _public_receipts(receipts: Mapping[str, Any]) -> dict[str, Any]:
    public = json.loads(json.dumps(receipts, ensure_ascii=False))
    _assert_no_abstract_text(public)
    public["payload_policy"] = {"storage": "NOT_PUBLISHED", "public_receipts_contain_abstract_text": False, "disposition": "EPHEMERAL_PAYLOADS_DELETED_BEFORE_UPLOAD"}
    return public


def render_acquisition_page(receipts: Mapping[str, Any]) -> str:
    counts = receipts.get("counts") or {}
    items = list(receipts.get("items") or [])
    payload = json.dumps(items, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    binding = html.escape(str(receipts.get("receipt_binding_sha256") or ""))
    return f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>EvidenceRadar Editions — Abstract acquisition</title><style>
:root{{--ink:#18212f;--muted:#667085;--line:#d8dee9;--paper:#f6f8fb;--ok:#176b3a;--warn:#9a5a00;--bad:#a2261d;--blue:#2457d6}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}.shell{{max-width:1180px;margin:auto;padding:28px 18px 60px}}h1{{font-size:clamp(28px,4vw,48px);line-height:1.05;margin:0 0 12px}}.lede{{max-width:920px;color:var(--muted);font-size:17px}}.notice{{padding:14px 16px;border:1px solid #f0c36d;background:#fff8e8;border-radius:12px;margin:18px 0}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:20px 0}}.metric{{background:#fff;border:1px solid var(--line);border-radius:14px;padding:15px}}.metric strong{{display:block;font-size:28px}}.controls{{display:grid;grid-template-columns:2fr repeat(2,minmax(170px,1fr));gap:10px;margin:18px 0}}input,select{{width:100%;padding:11px;border:1px solid var(--line);border-radius:10px;background:white}}.list{{display:grid;gap:12px}}.item{{background:white;border:1px solid var(--line);border-radius:14px;padding:16px}}.top{{display:flex;gap:8px;flex-wrap:wrap}}.badge{{font-size:12px;font-weight:750;padding:3px 8px;border-radius:999px;background:#eef2f7}}.badge.ok{{background:#e8f6ed;color:var(--ok)}}.badge.warn{{background:#fff1d7;color:var(--warn)}}.badge.bad{{background:#ffe8e5;color:var(--bad)}}.title{{font-size:17px;font-weight:750;margin:7px 0}}.meta{{font-size:13px;color:var(--muted)}}a{{color:var(--blue)}}code{{font-size:12px;word-break:break-all}}@media(max-width:760px){{.controls{{grid-template-columns:1fr}}}}</style></head><body><main class="shell">
<h1>Abstract acquisition</h1><p class="lede">只執行 Editorial Shortlist 的 FETCH_NOW 計畫。公開頁面保存來源、結果與摘要內容雜湊，不發布摘要原文。</p><p class="notice"><strong>界線：</strong><code>ABSTRACT_ACQUIRED</code> 只代表 exact identifier 的來源回傳摘要文字；<strong>尚未審讀摘要、尚未抓全文、尚未評估證據。</strong></p><section class="grid"><div class="metric"><span>Planned</span><strong>{int(receipts.get("plan_item_count") or 0):,}</strong></div><div class="metric"><span>Acquired</span><strong>{int(counts.get("abstract_acquired") or 0):,}</strong></div><div class="metric"><span>No abstract</span><strong>{int(counts.get("abstract_not_present") or 0):,}</strong></div><div class="metric"><span>Not found</span><strong>{int(counts.get("record_not_found") or 0):,}</strong></div><div class="metric"><span>Inconclusive</span><strong>{int(counts.get("acquisition_inconclusive") or 0):,}</strong></div></section><p><a href="{PUBLIC_RECEIPTS_FILENAME}">receipts JSON</a> · <a href="abstract-fetch-plan.json">fetch plan</a></p><section class="controls"><input id="q" type="search" placeholder="搜尋題名、期刊、identifier"><select id="status"><option value="">全部 status</option></select><select id="source"><option value="">全部 acquired source</option></select></section><p id="summary" class="meta"></p><section id="list" class="list"></section><footer class="meta">Receipt binding <code>{binding}</code></footer></main><script>
const ITEMS={payload};const $=id=>document.getElementById(id);for(const value of [...new Set(ITEMS.map(x=>x.status).filter(Boolean))].sort()){{const o=document.createElement("option");o.value=o.textContent=value;$("status").append(o)}}for(const value of [...new Set(ITEMS.map(x=>x.acquired_source).filter(Boolean))].sort()){{const o=document.createElement("option");o.value=o.textContent=value;$("source").append(o)}}function text(parent,tag,value,cls){{const n=document.createElement(tag);if(cls)n.className=cls;n.textContent=String(value??"");parent.append(n);return n}}function render(){{const q=$("q").value.trim().toLowerCase(),status=$("status").value,source=$("source").value;const rows=ITEMS.filter(x=>{{if(status&&x.status!==status)return false;if(source&&x.acquired_source!==source)return false;const hay=[x.title_original,x.journal,x.canonical_id,x.status,x.acquired_source,JSON.stringify(x.identifiers||{{}})].join(" ").toLowerCase();return !q||hay.includes(q)}});$("list").replaceChildren();$("summary").textContent=`顯示 ${{rows.length}} / ${{ITEMS.length}} 筆`;for(const row of rows){{const card=document.createElement("article");card.className="item";const top=document.createElement("div");top.className="top";card.append(top);const cls=row.status==="ABSTRACT_ACQUIRED"?"badge ok":row.status==="ACQUISITION_INCONCLUSIVE"?"badge bad":"badge warn";text(top,"span",row.status,cls);if(row.acquired_source)text(top,"span",row.acquired_source,"badge");text(card,"div",row.title_original,"title");text(card,"div",`${{row.journal||""}} · ${{row.canonical_id||""}}`,"meta");text(card,"div",`sha256 ${{row.abstract_sha256||"—"}} · bytes ${{row.abstract_bytes||0}} · chars ${{row.abstract_characters||0}}`,"meta");text(card,"div",(row.attempts||[]).map(a=>`${{a.source}}:${{a.status}}`).join(" · "),"meta");$("list").append(card)}}}}for(const id of ["q","status","source"])$(id).addEventListener("input",render);render();</script></body></html>'''


def _inject_portal_banner(path: Path, receipts: Mapping[str, Any]) -> None:
    content = path.read_text(encoding="utf-8")
    marker = '<main class="shell">'
    if marker not in content or 'href="abstract-acquisition.html"' in content:
        return
    counts = receipts.get("counts") or {}
    banner = marker + '<p style="padding:13px 15px;background:#eef7ff;border:1px solid #b8d0e8;border-radius:12px"><strong>Abstract acquisition：</strong>' + f'{int(counts.get("abstract_acquired") or 0)} / {int(receipts.get("plan_item_count") or 0)} 筆取得摘要；' + '公開層只保存 receipt 與 SHA-256，不發布摘要原文。 <a href="abstract-acquisition.html">查看 acquisition 狀態</a></p>'
    path.write_text(content.replace(marker, banner, 1), encoding="utf-8")


def attach_acquisition_to_site(site_dir: Path, receipts: Mapping[str, Any]) -> None:
    site = Path(site_dir)
    public = _public_receipts(receipts)
    (site / PUBLIC_RECEIPTS_FILENAME).write_text(json_text(public), encoding="utf-8")
    (site / PUBLIC_PAGE_FILENAME).write_text(render_acquisition_page(public), encoding="utf-8")
    _inject_portal_banner(site / "index.html", public)
    index_path = site / "index.json"
    index = _read_json(index_path)
    summary = {"artifact_type": public.get("artifact_type"), "plan_binding_sha256": public.get("plan_binding_sha256"), "receipt_binding_sha256": public.get("receipt_binding_sha256"), "plan_item_count": public.get("plan_item_count"), "receipt_count": public.get("receipt_count"), "counts": dict(public.get("counts") or {}), "scientific_boundary": public.get("scientific_boundary"), "receipts_file": PUBLIC_RECEIPTS_FILENAME, "page_file": PUBLIC_PAGE_FILENAME}
    index["abstract_acquisition"] = summary
    index_path.write_text(json_text(index), encoding="utf-8")
    links_path = site / "links.json"
    links = _read_json(links_path)
    base_url = str(links.get("base_url") or "")
    links["abstract_acquisition"] = summary
    links["abstract_acquisition_url"] = base_url + PUBLIC_PAGE_FILENAME
    links["abstract_acquisition_receipts_url"] = base_url + PUBLIC_RECEIPTS_FILENAME
    links_path.write_text(json_text(links), encoding="utf-8")


def run_delivery(*, site_dir: Path, work_dir: Path, payload_dir: Path, maximum_items: int = 300, crossref_mailto: str | None = None) -> dict[str, Any]:
    site, work, payload = Path(site_dir), Path(work_dir), Path(payload_dir)
    work.mkdir(parents=True, exist_ok=True)
    plan_path = site / "abstract-fetch-plan.json"
    plan = validate_plan(_read_json(plan_path), maximum_items=maximum_items)
    receipts = acquire_plan(plan, payload_dir=payload, maximum_items=maximum_items, crossref_mailto=crossref_mailto)
    vault = validate_payload_vault(receipts, payload)
    receipts_path = work / RECEIPTS_FILENAME
    receipts_path.write_text(json_text(receipts), encoding="utf-8")
    disposition = {"schema_version": "1.0", "artifact_type": "EvidenceRadar_Editions_AbstractPayloadDisposition", "generated_at": utc_now_iso(), "plan_binding_sha256": plan["plan_binding_sha256"], "receipt_binding_sha256": receipts["receipt_binding_sha256"], "payload_object_count_verified": vault["payload_object_count"], "payload_bytes_verified": vault["payload_bytes"], "disposition": "DELETED_BEFORE_ARTIFACT_UPLOAD", "abstract_text_published": False, "abstract_text_committed_to_git": False, "abstract_text_added_to_pages": False}
    disposition_path = work / DISPOSITION_FILENAME
    disposition_path.write_text(json_text(disposition), encoding="utf-8")
    attach_acquisition_to_site(site, receipts)
    shutil.copyfile(plan_path, work / "abstract-fetch-plan.json")
    delete_payload_vault(payload)
    if payload.exists():
        raise ValueError("abstract payload vault still exists after deletion")
    manifest = {"schema_version": "1.0", "artifact_type": "EvidenceRadar_Editions_AbstractAcquisitionManifest", "generated_at": utc_now_iso(), "plan_binding_sha256": plan["plan_binding_sha256"], "receipt_binding_sha256": receipts["receipt_binding_sha256"], "payload_disposition": disposition["disposition"], "files": {"abstract-fetch-plan.json": {"sha256": sha256_file(work / "abstract-fetch-plan.json"), "bytes": (work / "abstract-fetch-plan.json").stat().st_size}, RECEIPTS_FILENAME: {"sha256": sha256_file(receipts_path), "bytes": receipts_path.stat().st_size}, DISPOSITION_FILENAME: {"sha256": sha256_file(disposition_path), "bytes": disposition_path.stat().st_size}}}
    manifest_path = work / MANIFEST_FILENAME
    manifest_path.write_text(json_text(manifest), encoding="utf-8")
    return {"receipts": receipts, "disposition": disposition, "manifest": manifest}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Execute bounded abstract acquisition and publish sanitized receipts.")
    parser.add_argument("--site-dir", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--payload-dir", type=Path, required=True)
    parser.add_argument("--maximum-items", type=int, default=300)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = run_delivery(site_dir=args.site_dir, work_dir=args.work_dir, payload_dir=args.payload_dir, maximum_items=args.maximum_items, crossref_mailto=os.environ.get("CROSSREF_MAILTO"))
    receipts = result["receipts"]
    print(json.dumps({"plan_item_count": receipts["plan_item_count"], "receipt_count": receipts["receipt_count"], "counts": receipts["counts"], "receipt_binding_sha256": receipts["receipt_binding_sha256"], "payload_disposition": result["disposition"]["disposition"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
