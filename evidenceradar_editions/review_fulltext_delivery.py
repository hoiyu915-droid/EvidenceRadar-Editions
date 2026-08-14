from __future__ import annotations
import argparse,html,json,os,shutil
from pathlib import Path
from typing import Any,Mapping
from .abstract_acquisition import DISPOSITION_FILENAME,RECEIPTS_FILENAME,acquire_plan,delete_payload_vault,validate_payload_vault,validate_plan
from .abstract_acquisition_delivery import attach_acquisition_to_site
from .abstract_review import ABSTRACT_REVIEW_FILENAME,ABSTRACT_REVIEW_PAGE_FILENAME,ABSTRACT_REVIEW_POLICY_FILENAME,FULLTEXT_FETCH_PLAN_FILENAME,build_abstract_review,load_abstract_review_policy
from .fulltext_acquisition import EVIDENCE_REVIEW_PLAN_FILENAME,FULLTEXT_DISPOSITION_FILENAME,FULLTEXT_RECEIPTS_FILENAME,acquire_fulltext_plan,delete_fulltext_payload_vault,validate_fulltext_payload_vault
from .serialization import json_text
from .utils import sha256_file,utc_now_iso

FULLTEXT_PAGE_FILENAME="fulltext-acquisition.html"
FULLTEXT_PUBLIC_FILENAME="fulltext-acquisition.json"
PIPELINE_MANIFEST_FILENAME="abstract-review-fulltext-manifest.json"
FORBIDDEN={"abstract","abstract_text","abstractText","payload_text","raw_response","fulltext","full_text","fulltext_text","full_text_text","raw_fulltext"}

def readj(path):
    v=json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(v,dict): raise ValueError(f"expected JSON object: {path}")
    return v

def safe(v):
    if isinstance(v,Mapping):
        bad=set(map(str,v)).intersection(FORBIDDEN)
        if bad: raise ValueError(f"forbidden raw content fields: {sorted(bad)}")
        for x in v.values(): safe(x)
    elif isinstance(v,list):
        for x in v: safe(x)

def page(title,lede,notice,metrics,links,binding):
    cards="".join(f'<div class="m"><span>{html.escape(str(k))}</span><strong>{int(v or 0):,}</strong></div>' for k,v in metrics)
    nav=" · ".join(f'<a href="{html.escape(u)}">{html.escape(t)}</a>' for t,u in links)
    return f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title><style>body{{margin:0;background:#f6f8fb;color:#18212f;font:15px/1.55 system-ui,sans-serif}}main{{max-width:1050px;margin:auto;padding:32px 18px}}h1{{font-size:42px;margin:0 0 10px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:20px 0}}.m{{background:white;border:1px solid #d8dee9;border-radius:14px;padding:15px}}.m strong{{display:block;font-size:28px}}.n{{padding:14px;background:#fff8e8;border:1px solid #efc66d;border-radius:12px}}a{{color:#2457d6}}code{{word-break:break-all}}</style></head><body><main><h1>{html.escape(title)}</h1><p>{html.escape(lede)}</p><p class="n">{html.escape(notice)}</p><section class="grid">{cards}</section><p>{nav}</p><footer>binding <code>{html.escape(str(binding or ""))}</code></footer></main></body></html>'''

def public_fulltext(receipts):
    out=json.loads(json.dumps(receipts,ensure_ascii=False)); safe(out)
    out["payload_policy"]={"storage":"NOT_PUBLISHED","public_receipts_contain_fulltext":False,"disposition":"EPHEMERAL_PAYLOADS_DELETED_BEFORE_UPLOAD"}
    return out

def inject_banner(path,review,fulltext):
    p=Path(path); text=p.read_text(encoding="utf-8"); marker='<main class="shell">'
    if marker not in text or 'href="abstract-review.html"' in text: return
    a=(review.get("counts") or {}).get("abstract_acquired",0); f=(fulltext.get("counts") or {}).get("fulltext_acquired",0); n=fulltext.get("plan_item_count",0)
    b=marker+f'<p style="padding:13px 15px;background:#eef7ff;border:1px solid #b8d0e8;border-radius:12px"><strong>Review → full text：</strong>{a} 篇摘要已結構審讀；{f} / {n} 篇全文取得。 <a href="abstract-review.html">摘要審讀</a> · <a href="fulltext-acquisition.html">全文取得</a></p>'
    p.write_text(text.replace(marker,b,1),encoding="utf-8")

def attach(site,review,fulltext,policy):
    site=Path(site); pub=public_fulltext(fulltext); safe(review); safe(policy); safe(fulltext["evidence_review_plan"])
    files={ABSTRACT_REVIEW_FILENAME:review,ABSTRACT_REVIEW_POLICY_FILENAME:policy,FULLTEXT_FETCH_PLAN_FILENAME:review["fulltext_fetch_plan"],FULLTEXT_PUBLIC_FILENAME:pub,EVIDENCE_REVIEW_PLAN_FILENAME:fulltext["evidence_review_plan"]}
    for name,v in files.items(): (site/name).write_text(json_text(v),encoding="utf-8")
    rc=review.get("counts") or {}; fc=fulltext.get("counts") or {}
    (site/ABSTRACT_REVIEW_PAGE_FILENAME).write_text(page("Abstract review","對已取得摘要做 deterministic structural review，再分配全文取得預算。","abstract_reviewed=true 不是研究品質、效果可信度或 risk-of-bias 評分。",[("Abstract acquired",rc.get("abstract_acquired")),("FULLTEXT_NOW",rc.get("fulltext_now_count")),("Reserve",rc.get("fulltext_reserve_count")),("No abstract",rc.get("no_abstract_count"))],[("review JSON",ABSTRACT_REVIEW_FILENAME),("full-text plan",FULLTEXT_FETCH_PLAN_FILENAME),("policy",ABSTRACT_REVIEW_POLICY_FILENAME)],review.get("abstract_review_binding_sha256")),encoding="utf-8")
    (site/FULLTEXT_PAGE_FILENAME).write_text(page("Full-text acquisition","只執行 bounded FULLTEXT_NOW；全文 payload 不公開。","FULLTEXT_ACQUIRED 只代表 exact allowed route 回傳 hash-bound bytes；evidence_evaluated 仍為 false。",[("Planned",fulltext.get("plan_item_count")),("Acquired",fc.get("fulltext_acquired")),("No route",fc.get("route_not_found")),("Denied",fc.get("access_denied")),("Inconclusive",fc.get("acquisition_inconclusive"))],[("receipts JSON",FULLTEXT_PUBLIC_FILENAME),("evidence-review plan",EVIDENCE_REVIEW_PLAN_FILENAME)],fulltext.get("receipt_binding_sha256")),encoding="utf-8")
    inject_banner(site/"index.html",review,fulltext)
    idx=readj(site/"index.json"); idx["abstract_review"]={"policy_id":review.get("policy_id"),"policy_sha256":review.get("policy_sha256"),"abstract_receipt_binding_sha256":review.get("abstract_receipt_binding_sha256"),"abstract_review_binding_sha256":review.get("abstract_review_binding_sha256"),"counts":dict(rc),"page_file":ABSTRACT_REVIEW_PAGE_FILENAME,"review_file":ABSTRACT_REVIEW_FILENAME,"fulltext_plan_file":FULLTEXT_FETCH_PLAN_FILENAME}; idx["fulltext_acquisition"]={"plan_binding_sha256":fulltext.get("plan_binding_sha256"),"receipt_binding_sha256":fulltext.get("receipt_binding_sha256"),"counts":dict(fc),"page_file":FULLTEXT_PAGE_FILENAME,"receipts_file":FULLTEXT_PUBLIC_FILENAME,"evidence_review_plan_file":EVIDENCE_REVIEW_PLAN_FILENAME,"evidence_review_ready_count":int((fulltext.get("evidence_review_plan") or {}).get("item_count") or 0)}; (site/"index.json").write_text(json_text(idx),encoding="utf-8")
    links=readj(site/"links.json"); base=str(links.get("base_url") or ""); links["abstract_review"]=idx["abstract_review"]; links["abstract_review_url"]=base+ABSTRACT_REVIEW_PAGE_FILENAME; links["abstract_review_json_url"]=base+ABSTRACT_REVIEW_FILENAME; links["fulltext_fetch_plan_url"]=base+FULLTEXT_FETCH_PLAN_FILENAME; links["fulltext_acquisition"]=idx["fulltext_acquisition"]; links["fulltext_acquisition_url"]=base+FULLTEXT_PAGE_FILENAME; links["fulltext_acquisition_receipts_url"]=base+FULLTEXT_PUBLIC_FILENAME; links["evidence_review_plan_url"]=base+EVIDENCE_REVIEW_PLAN_FILENAME; (site/"links.json").write_text(json_text(links),encoding="utf-8")

def entry(path): return {"sha256":sha256_file(path),"bytes":Path(path).stat().st_size}

def run_delivery(*,site_dir,work_dir,abstract_payload_dir,fulltext_payload_dir,catalog_root,maximum_abstract_items=300,maximum_fulltext_items=120,crossref_mailto=None):
    site,work,ap,fp=map(Path,(site_dir,work_dir,abstract_payload_dir,fulltext_payload_dir)); work.mkdir(parents=True,exist_ok=True)
    aplan=validate_plan(readj(site/"abstract-fetch-plan.json"),maximum_items=maximum_abstract_items)
    ar=acquire_plan(aplan,payload_dir=ap,maximum_items=maximum_abstract_items,crossref_mailto=crossref_mailto); av=validate_payload_vault(ar,ap); attach_acquisition_to_site(site,ar)
    shortlist=readj(site/"editorial-shortlist.json"); policy=load_abstract_review_policy(catalog_root); review,fplan=build_abstract_review(ar,shortlist,payload_dir=ap,policy=policy)
    if int(fplan.get("item_count") or 0)>maximum_fulltext_items: raise ValueError("generated fulltext plan exceeds delivery maximum")
    fr=acquire_fulltext_plan(fplan,payload_dir=fp,maximum_items=maximum_fulltext_items,response_limit=int(policy["fulltext_response_limit_bytes"]),crossref_mailto=crossref_mailto,open_license_hosts=list(policy["crossref_open_license_hosts"])); fv=validate_fulltext_payload_vault(fr,fp); attach(site,review,fr,policy)
    material={"abstract-fetch-plan.json":aplan,RECEIPTS_FILENAME:ar,ABSTRACT_REVIEW_FILENAME:review,FULLTEXT_FETCH_PLAN_FILENAME:fplan,FULLTEXT_RECEIPTS_FILENAME:fr,EVIDENCE_REVIEW_PLAN_FILENAME:fr["evidence_review_plan"],ABSTRACT_REVIEW_POLICY_FILENAME:policy}; files={}
    for name,v in material.items(): safe(v); path=work/name; path.write_text(json_text(v),encoding="utf-8"); files[name]=entry(path)
    ad={"schema_version":"1.1","artifact_type":"EvidenceRadar_Editions_AbstractPayloadDisposition","generated_at":utc_now_iso(),"plan_binding_sha256":aplan["plan_binding_sha256"],"receipt_binding_sha256":ar["receipt_binding_sha256"],"payload_object_count_verified":av["payload_object_count"],"payload_bytes_verified":av["payload_bytes"],"disposition":"DELETED_BEFORE_ARTIFACT_UPLOAD","abstract_text_published":False,"abstract_text_committed_to_git":False,"abstract_text_added_to_pages":False,"abstract_text_used_for_structural_review_before_deletion":True}
    fd={"schema_version":"1.0","artifact_type":"EvidenceRadar_Editions_FulltextPayloadDisposition","generated_at":utc_now_iso(),"plan_binding_sha256":fplan["plan_binding_sha256"],"receipt_binding_sha256":fr["receipt_binding_sha256"],"payload_object_count_verified":fv["payload_object_count"],"payload_bytes_verified":fv["payload_bytes"],"disposition":"DELETED_BEFORE_ARTIFACT_UPLOAD","fulltext_published":False,"fulltext_committed_to_git":False,"fulltext_added_to_pages":False,"structural_audit_completed_before_deletion":True,"evidence_evaluated":False}
    for name,v in ((DISPOSITION_FILENAME,ad),(FULLTEXT_DISPOSITION_FILENAME,fd)):
        path=work/name; path.write_text(json_text(v),encoding="utf-8"); files[name]=entry(path)
    delete_payload_vault(ap); delete_fulltext_payload_vault(fp)
    if ap.exists() or fp.exists(): raise ValueError("ephemeral payload vault still exists after deletion")
    m={"schema_version":"1.0","artifact_type":"EvidenceRadar_Editions_AbstractReviewFulltextManifest","generated_at":utc_now_iso(),"abstract_plan_binding_sha256":aplan["plan_binding_sha256"],"abstract_receipt_binding_sha256":ar["receipt_binding_sha256"],"abstract_review_binding_sha256":review["abstract_review_binding_sha256"],"fulltext_plan_binding_sha256":fplan["plan_binding_sha256"],"fulltext_receipt_binding_sha256":fr["receipt_binding_sha256"],"evidence_review_plan_binding_sha256":fr["evidence_review_plan"]["evidence_review_plan_binding_sha256"],"abstract_payload_disposition":ad["disposition"],"fulltext_payload_disposition":fd["disposition"],"files":files}; (work/PIPELINE_MANIFEST_FILENAME).write_text(json_text(m),encoding="utf-8")
    return {"abstract_receipts":ar,"abstract_review":review,"fulltext_receipts":fr,"abstract_disposition":ad,"fulltext_disposition":fd,"manifest":m}

def parser():
    p=argparse.ArgumentParser(); p.add_argument("--site-dir",type=Path,required=True); p.add_argument("--work-dir",type=Path,required=True); p.add_argument("--abstract-payload-dir",type=Path,required=True); p.add_argument("--fulltext-payload-dir",type=Path,required=True); p.add_argument("--catalog-root",type=Path,default=Path("catalog")); p.add_argument("--maximum-abstract-items",type=int,default=300); p.add_argument("--maximum-fulltext-items",type=int,default=120); return p

def main(argv=None):
    a=parser().parse_args(argv); r=run_delivery(site_dir=a.site_dir,work_dir=a.work_dir,abstract_payload_dir=a.abstract_payload_dir,fulltext_payload_dir=a.fulltext_payload_dir,catalog_root=a.catalog_root,maximum_abstract_items=a.maximum_abstract_items,maximum_fulltext_items=a.maximum_fulltext_items,crossref_mailto=os.environ.get("CROSSREF_MAILTO")); rv=r["abstract_review"]; ft=r["fulltext_receipts"]; print(json.dumps({"abstract_reviewed":rv["counts"]["abstract_acquired"],"fulltext_planned":ft["plan_item_count"],"fulltext_acquired":ft["counts"]["fulltext_acquired"],"fulltext_route_not_found":ft["counts"]["route_not_found"],"fulltext_access_denied":ft["counts"]["access_denied"],"fulltext_inconclusive":ft["counts"]["acquisition_inconclusive"],"evidence_review_ready":ft["evidence_review_plan"]["item_count"],"abstract_payload_disposition":r["abstract_disposition"]["disposition"],"fulltext_payload_disposition":r["fulltext_disposition"]["disposition"]},sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
