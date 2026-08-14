from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
from typing import Any, Mapping

from .abstract_acquisition import (
    DISPOSITION_FILENAME,
    RECEIPTS_FILENAME,
    acquire_plan,
    delete_payload_vault,
    validate_payload_vault,
    validate_plan,
)
from .abstract_acquisition_delivery import attach_acquisition_to_site
from .abstract_review import (
    ABSTRACT_REVIEW_FILENAME,
    ABSTRACT_REVIEW_PAGE_FILENAME,
    ABSTRACT_REVIEW_POLICY_FILENAME,
    FULLTEXT_FETCH_PLAN_FILENAME,
    build_abstract_review,
    load_abstract_review_policy,
)
from .evidence_evaluation import (
    EDITORIAL_FILENAME,
    EDITORIAL_PAGE_FILENAME,
    EVALUATION_FILENAME,
    EVALUATION_PAGE_FILENAME,
    POLICY_FILENAME as EVIDENCE_POLICY_FILENAME,
    build_evaluated_edition,
    evaluate_fulltext,
    load_policy as load_evidence_evaluation_policy,
)
from .fulltext_acquisition import (
    EVIDENCE_REVIEW_PLAN_FILENAME,
    FULLTEXT_DISPOSITION_FILENAME,
    FULLTEXT_RECEIPTS_FILENAME,
    acquire_fulltext_plan,
    delete_fulltext_payload_vault,
    validate_fulltext_payload_vault,
)
from .review_fulltext_delivery import (
    FULLTEXT_PAGE_FILENAME,
    FULLTEXT_PUBLIC_FILENAME,
    attach as attach_review_fulltext,
)
from .serialization import json_text
from .utils import sha256_file, utc_now_iso

COMPLETE_MANIFEST_FILENAME = "complete-edition-manifest.json"
FORBIDDEN = {
    "abstract", "abstract_text", "abstractText", "payload_text", "raw_response",
    "fulltext", "full_text", "fulltext_text", "full_text_text", "raw_fulltext",
}


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _assert_safe(value: Any) -> None:
    if isinstance(value, Mapping):
        bad = set(map(str, value)).intersection(FORBIDDEN)
        if bad:
            raise ValueError(f"forbidden raw content fields: {sorted(bad)}")
        for child in value.values():
            _assert_safe(child)
    elif isinstance(value, list):
        for child in value:
            _assert_safe(child)


def _entry(path: Path) -> dict[str, Any]:
    return {"sha256": sha256_file(path), "bytes": path.stat().st_size}


def _metric_cards(metrics: list[tuple[str, Any]]) -> str:
    return "".join(
        f'<div class="m"><span>{html.escape(str(label))}</span><strong>{int(value or 0):,}</strong></div>'
        for label, value in metrics
    )


def _simple_page(title: str, lede: str, notice: str, metrics: list[tuple[str, Any]], links: list[tuple[str, str]], binding: Any) -> str:
    nav = " · ".join(f'<a href="{html.escape(url)}">{html.escape(label)}</a>' for label, url in links)
    return f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title><style>body{{margin:0;background:#f6f8fb;color:#18212f;font:15px/1.55 system-ui,sans-serif}}main{{max-width:1080px;margin:auto;padding:32px 18px}}h1{{font-size:42px;margin:0 0 10px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:20px 0}}.m{{background:#fff;border:1px solid #d8dee9;border-radius:14px;padding:15px}}.m strong{{display:block;font-size:28px}}.n{{padding:14px;background:#fff8e8;border:1px solid #efc66d;border-radius:12px}}a{{color:#2457d6}}code{{word-break:break-all}}</style></head><body><main><h1>{html.escape(title)}</h1><p>{html.escape(lede)}</p><p class="n">{html.escape(notice)}</p><section class="grid">{_metric_cards(metrics)}</section><p>{nav}</p><footer>binding <code>{html.escape(str(binding or ""))}</code></footer></main></body></html>'''


def _editorial_page(editorial: Mapping[str, Any]) -> str:
    featured = [row for row in editorial.get("items") or [] if row.get("editorial_route") == "FEATURED"]
    cards = []
    for row in sorted(featured, key=lambda value: int(value.get("selection_ordinal") or 999999)):
        coverage = float(row.get("reporting_coverage_fraction") or 0.0)
        gaps = ", ".join(row.get("critical_reporting_gaps") or []) or "none detected"
        cards.append(
            '<article class="item">'
            f'<div class="rank">#{int(row.get("selection_ordinal") or 0)}</div>'
            f'<h2>{html.escape(str(row.get("title_original") or ""))}</h2>'
            f'<p class="meta">{html.escape(str(row.get("journal") or ""))} · {html.escape(str(row.get("primary_path") or "DEFAULT"))}</p>'
            f'<p>Reporting coverage <strong>{coverage:.0%}</strong> · {html.escape(str(row.get("reporting_coverage_class") or ""))}</p>'
            f'<p class="meta">Critical reporting gaps: {html.escape(gaps)}</p>'
            '</article>'
        )
    counts = editorial.get("counts") or {}
    return f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>EvidenceRadar Editions — evaluated edition</title><style>body{{margin:0;background:#f6f8fb;color:#18212f;font:15px/1.55 system-ui,sans-serif}}main{{max-width:1080px;margin:auto;padding:32px 18px}}h1{{font-size:42px;margin:0 0 10px}}.notice{{padding:14px;background:#fff8e8;border:1px solid #efc66d;border-radius:12px}}.grid{{display:grid;gap:12px}}.item{{background:white;border:1px solid #d8dee9;border-radius:14px;padding:16px}}.rank{{font-weight:800;color:#2457d6}}h2{{font-size:18px;margin:5px 0}}.meta{{color:#667085;font-size:13px}}a{{color:#2457d6}}</style></head><body><main><h1>Evaluated edition</h1><p class="notice">FEATURED 只代表在 hash-bound 全文 reporting audit 後獲較高公開編輯注意優先序；不是 endorsement、正式 risk-of-bias 結論或臨床建議。</p><p>Featured {int(counts.get("featured") or 0):,} · Evidence reserve {int(counts.get("evidence_reserve") or 0):,} · Limited review {int(counts.get("limited_review") or 0):,}</p><p><a href="{EDITORIAL_FILENAME}">machine-readable selection</a> · <a href="{EVALUATION_PAGE_FILENAME}">evidence evaluation</a></p><section class="grid">{"".join(cards)}</section></main></body></html>'''


def _inject_final_banner(path: Path, evaluation: Mapping[str, Any], editorial: Mapping[str, Any]) -> None:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    marker = '<main class="shell">'
    if marker not in text or f'href="{EDITORIAL_PAGE_FILENAME}"' in text:
        return
    ec = evaluation.get("counts") or {}
    sc = editorial.get("counts") or {}
    banner = marker + (
        '<p style="padding:13px 15px;background:#edf8f0;border:1px solid #b9ddc3;border-radius:12px">'
        f'<strong>Default end-to-end evidence lane：</strong>{int(ec.get("evidence_evaluated") or 0)} 篇全文完成 machine evidence-reporting audit；'
        f'{int(sc.get("featured") or 0)} 篇進 FEATURED。 '
        f'<a href="{EVALUATION_PAGE_FILENAME}">evidence audit</a> · <a href="{EDITORIAL_PAGE_FILENAME}">evaluated edition</a></p>'
    )
    path.write_text(text.replace(marker, banner, 1), encoding="utf-8")


def _attach_evidence(site_dir: Path, evaluation: Mapping[str, Any], editorial: Mapping[str, Any], policy: Mapping[str, Any]) -> None:
    site = Path(site_dir)
    for value in (evaluation, editorial, policy):
        _assert_safe(value)
    (site / EVALUATION_FILENAME).write_text(json_text(dict(evaluation)), encoding="utf-8")
    (site / EVIDENCE_POLICY_FILENAME).write_text(json_text(dict(policy)), encoding="utf-8")
    (site / EDITORIAL_FILENAME).write_text(json_text(dict(editorial)), encoding="utf-8")
    ec = evaluation.get("counts") or {}
    sc = editorial.get("counts") or {}
    (site / EVALUATION_PAGE_FILENAME).write_text(
        _simple_page(
            "Evidence evaluation",
            "對 hash-verified 全文執行 design-aware reporting checklist，再產生公開 editorial projection。",
            "evidence_evaluated=true 表示 deterministic full-text evidence-reporting audit 已執行；不等於正式 risk-of-bias、因果有效性或臨床重要性已確立。",
            [
                ("Full text acquired", ec.get("fulltext_acquired")),
                ("Evidence evaluated", ec.get("evidence_evaluated")),
                ("Limited text", ec.get("limited_no_machine_text")),
                ("No full text", ec.get("no_fulltext")),
                ("Featured", sc.get("featured")),
            ],
            [("evaluation JSON", EVALUATION_FILENAME), ("policy", EVIDENCE_POLICY_FILENAME), ("evaluated edition", EDITORIAL_PAGE_FILENAME)],
            evaluation.get("evidence_evaluation_binding_sha256"),
        ),
        encoding="utf-8",
    )
    (site / EDITORIAL_PAGE_FILENAME).write_text(_editorial_page(editorial), encoding="utf-8")
    _inject_final_banner(site / "index.html", evaluation, editorial)
    index = _read_json(site / "index.json")
    index["evidence_evaluation"] = {
        "policy_id": evaluation.get("policy_id"),
        "policy_sha256": evaluation.get("policy_sha256"),
        "fulltext_receipt_binding_sha256": evaluation.get("fulltext_receipt_binding_sha256"),
        "evidence_evaluation_binding_sha256": evaluation.get("evidence_evaluation_binding_sha256"),
        "counts": dict(ec),
        "evaluation_file": EVALUATION_FILENAME,
        "page_file": EVALUATION_PAGE_FILENAME,
        "policy_file": EVIDENCE_POLICY_FILENAME,
    }
    index["evaluated_edition"] = {
        "evaluated_edition_binding_sha256": editorial.get("evaluated_edition_binding_sha256"),
        "evidence_evaluation_binding_sha256": editorial.get("evidence_evaluation_binding_sha256"),
        "counts": dict(sc),
        "edition_file": EDITORIAL_FILENAME,
        "page_file": EDITORIAL_PAGE_FILENAME,
    }
    (site / "index.json").write_text(json_text(index), encoding="utf-8")
    links = _read_json(site / "links.json")
    base = str(links.get("base_url") or "")
    links["evidence_evaluation"] = index["evidence_evaluation"]
    links["evidence_evaluation_url"] = base + EVALUATION_PAGE_FILENAME
    links["evidence_evaluation_json_url"] = base + EVALUATION_FILENAME
    links["evaluated_edition"] = index["evaluated_edition"]
    links["evaluated_edition_url"] = base + EDITORIAL_PAGE_FILENAME
    links["evaluated_edition_json_url"] = base + EDITORIAL_FILENAME
    (site / "links.json").write_text(json_text(links), encoding="utf-8")


def run_delivery(
    *,
    site_dir: Path,
    work_dir: Path,
    abstract_payload_dir: Path,
    fulltext_payload_dir: Path,
    catalog_root: Path,
    maximum_abstract_items: int = 300,
    maximum_fulltext_items: int = 120,
    crossref_mailto: str | None = None,
) -> dict[str, Any]:
    site, work, abstract_payload, fulltext_payload = map(
        Path, (site_dir, work_dir, abstract_payload_dir, fulltext_payload_dir)
    )
    work.mkdir(parents=True, exist_ok=True)

    abstract_plan = validate_plan(_read_json(site / "abstract-fetch-plan.json"), maximum_items=maximum_abstract_items)
    abstract_receipts = acquire_plan(
        abstract_plan,
        payload_dir=abstract_payload,
        maximum_items=maximum_abstract_items,
        crossref_mailto=crossref_mailto,
    )
    abstract_vault = validate_payload_vault(abstract_receipts, abstract_payload)
    attach_acquisition_to_site(site, abstract_receipts)

    shortlist = _read_json(site / "editorial-shortlist.json")
    abstract_policy = load_abstract_review_policy(catalog_root)
    abstract_review, fulltext_plan = build_abstract_review(
        abstract_receipts,
        shortlist,
        payload_dir=abstract_payload,
        policy=abstract_policy,
    )
    if int(fulltext_plan.get("item_count") or 0) > maximum_fulltext_items:
        raise ValueError("generated full-text plan exceeds delivery maximum")

    fulltext_receipts = acquire_fulltext_plan(
        fulltext_plan,
        payload_dir=fulltext_payload,
        maximum_items=maximum_fulltext_items,
        response_limit=int(abstract_policy["fulltext_response_limit_bytes"]),
        crossref_mailto=crossref_mailto,
        open_license_hosts=list(abstract_policy["crossref_open_license_hosts"]),
    )
    fulltext_vault = validate_fulltext_payload_vault(fulltext_receipts, fulltext_payload)

    evidence_policy = load_evidence_evaluation_policy(catalog_root)
    evidence_evaluation = evaluate_fulltext(
        fulltext_receipts,
        abstract_review,
        payload_dir=fulltext_payload,
        policy=evidence_policy,
    )
    evaluated_edition = build_evaluated_edition(evidence_evaluation, policy=evidence_policy)

    attach_review_fulltext(site, abstract_review, fulltext_receipts, abstract_policy)
    _attach_evidence(site, evidence_evaluation, evaluated_edition, evidence_policy)

    material = {
        "abstract-fetch-plan.json": abstract_plan,
        RECEIPTS_FILENAME: abstract_receipts,
        ABSTRACT_REVIEW_FILENAME: abstract_review,
        ABSTRACT_REVIEW_POLICY_FILENAME: abstract_policy,
        FULLTEXT_FETCH_PLAN_FILENAME: fulltext_plan,
        FULLTEXT_RECEIPTS_FILENAME: fulltext_receipts,
        EVIDENCE_REVIEW_PLAN_FILENAME: fulltext_receipts["evidence_review_plan"],
        EVIDENCE_POLICY_FILENAME: evidence_policy,
        EVALUATION_FILENAME: evidence_evaluation,
        EDITORIAL_FILENAME: evaluated_edition,
    }
    files: dict[str, dict[str, Any]] = {}
    for name, value in material.items():
        _assert_safe(value)
        path = work / name
        path.write_text(json_text(value), encoding="utf-8")
        files[name] = _entry(path)

    abstract_disposition = {
        "schema_version": "1.2",
        "artifact_type": "EvidenceRadar_Editions_AbstractPayloadDisposition",
        "generated_at": utc_now_iso(),
        "plan_binding_sha256": abstract_plan["plan_binding_sha256"],
        "receipt_binding_sha256": abstract_receipts["receipt_binding_sha256"],
        "payload_object_count_verified": abstract_vault["payload_object_count"],
        "payload_bytes_verified": abstract_vault["payload_bytes"],
        "disposition": "DELETED_BEFORE_ARTIFACT_UPLOAD",
        "abstract_text_published": False,
        "abstract_text_committed_to_git": False,
        "abstract_text_added_to_pages": False,
        "abstract_text_used_for_structural_review_before_deletion": True,
    }
    fulltext_disposition = {
        "schema_version": "1.1",
        "artifact_type": "EvidenceRadar_Editions_FulltextPayloadDisposition",
        "generated_at": utc_now_iso(),
        "plan_binding_sha256": fulltext_plan["plan_binding_sha256"],
        "receipt_binding_sha256": fulltext_receipts["receipt_binding_sha256"],
        "evidence_evaluation_binding_sha256": evidence_evaluation["evidence_evaluation_binding_sha256"],
        "payload_object_count_verified": fulltext_vault["payload_object_count"],
        "payload_bytes_verified": fulltext_vault["payload_bytes"],
        "disposition": "DELETED_BEFORE_ARTIFACT_UPLOAD",
        "fulltext_published": False,
        "fulltext_committed_to_git": False,
        "fulltext_added_to_pages": False,
        "structural_audit_completed_before_deletion": True,
        "evidence_reporting_audit_completed_before_deletion": True,
        "evidence_evaluated_count": int((evidence_evaluation.get("counts") or {}).get("evidence_evaluated") or 0),
        "limited_no_machine_text_count": int((evidence_evaluation.get("counts") or {}).get("limited_no_machine_text") or 0),
    }
    for name, value in ((DISPOSITION_FILENAME, abstract_disposition), (FULLTEXT_DISPOSITION_FILENAME, fulltext_disposition)):
        path = work / name
        path.write_text(json_text(value), encoding="utf-8")
        files[name] = _entry(path)

    delete_payload_vault(abstract_payload)
    delete_fulltext_payload_vault(fulltext_payload)
    if abstract_payload.exists() or fulltext_payload.exists():
        raise ValueError("ephemeral payload vault still exists after deletion")

    manifest = {
        "schema_version": "1.0",
        "artifact_type": "EvidenceRadar_Editions_CompleteEditionManifest",
        "generated_at": utc_now_iso(),
        "abstract_plan_binding_sha256": abstract_plan["plan_binding_sha256"],
        "abstract_receipt_binding_sha256": abstract_receipts["receipt_binding_sha256"],
        "abstract_review_binding_sha256": abstract_review["abstract_review_binding_sha256"],
        "fulltext_plan_binding_sha256": fulltext_plan["plan_binding_sha256"],
        "fulltext_receipt_binding_sha256": fulltext_receipts["receipt_binding_sha256"],
        "evidence_review_plan_binding_sha256": fulltext_receipts["evidence_review_plan"]["evidence_review_plan_binding_sha256"],
        "evidence_evaluation_binding_sha256": evidence_evaluation["evidence_evaluation_binding_sha256"],
        "evaluated_edition_binding_sha256": evaluated_edition["evaluated_edition_binding_sha256"],
        "abstract_payload_disposition": abstract_disposition["disposition"],
        "fulltext_payload_disposition": fulltext_disposition["disposition"],
        "files": files,
    }
    manifest_path = work / COMPLETE_MANIFEST_FILENAME
    manifest_path.write_text(json_text(manifest), encoding="utf-8")

    return {
        "abstract_receipts": abstract_receipts,
        "abstract_review": abstract_review,
        "fulltext_receipts": fulltext_receipts,
        "evidence_evaluation": evidence_evaluation,
        "evaluated_edition": evaluated_edition,
        "abstract_disposition": abstract_disposition,
        "fulltext_disposition": fulltext_disposition,
        "manifest": manifest,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the default end-to-end Edition evidence lane.")
    parser.add_argument("--site-dir", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--abstract-payload-dir", type=Path, required=True)
    parser.add_argument("--fulltext-payload-dir", type=Path, required=True)
    parser.add_argument("--catalog-root", type=Path, default=Path("catalog"))
    parser.add_argument("--maximum-abstract-items", type=int, default=300)
    parser.add_argument("--maximum-fulltext-items", type=int, default=120)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = run_delivery(
        site_dir=args.site_dir,
        work_dir=args.work_dir,
        abstract_payload_dir=args.abstract_payload_dir,
        fulltext_payload_dir=args.fulltext_payload_dir,
        catalog_root=args.catalog_root,
        maximum_abstract_items=args.maximum_abstract_items,
        maximum_fulltext_items=args.maximum_fulltext_items,
        crossref_mailto=os.environ.get("CROSSREF_MAILTO"),
    )
    abstract = result["abstract_receipts"]
    fulltext = result["fulltext_receipts"]
    evaluation = result["evidence_evaluation"]
    editorial = result["evaluated_edition"]
    print(
        json.dumps(
            {
                "abstract_planned": abstract["plan_item_count"],
                "abstract_acquired": abstract["counts"]["abstract_acquired"],
                "abstract_reviewed": result["abstract_review"]["counts"]["abstract_acquired"],
                "fulltext_planned": fulltext["plan_item_count"],
                "fulltext_acquired": fulltext["counts"]["fulltext_acquired"],
                "evidence_evaluated": evaluation["counts"]["evidence_evaluated"],
                "limited_no_machine_text": evaluation["counts"]["limited_no_machine_text"],
                "featured": editorial["counts"]["featured"],
                "evidence_reserve": editorial["counts"]["evidence_reserve"],
                "abstract_payload_disposition": result["abstract_disposition"]["disposition"],
                "fulltext_payload_disposition": result["fulltext_disposition"]["disposition"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
