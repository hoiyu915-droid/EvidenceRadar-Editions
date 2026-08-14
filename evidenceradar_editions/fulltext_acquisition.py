from __future__ import annotations
import hashlib,json,re,shutil
from collections import Counter
from pathlib import Path
from typing import Any,Mapping
from urllib.parse import quote,urlsplit
import requests
from defusedxml import ElementTree as ET
from .http import HttpClient
from .utils import clean_text,normalize_doi,utc_now_iso

EUROPE_PMC="https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
CROSSREF="https://api.crossref.org/works/{doi}"
RECEIPTS_FILE="fulltext-acquisition-receipts.json"
DISPOSITION_FILE="fulltext-payload-disposition.json"
EVIDENCE_PLAN_FILE="evidence-review-plan.json"
SOURCES={"EUROPE_PMC_FULLTEXT_XML","CROSSREF_OPEN_TDM_LINK"}
FINAL={"FULLTEXT_ACQUIRED","FULLTEXT_ROUTE_NOT_FOUND","FULLTEXT_ACCESS_DENIED","FULLTEXT_NOT_FOUND","FULLTEXT_ACQUISITION_INCONCLUSIVE","SKIPPED_NO_FULLTEXT_SOURCE"}
FORMATS={"text/xml":".xml","application/xml":".xml","text/plain":".txt","application/pdf":".pdf"}
SECTIONS={"methods":("method","materials and methods","methodology","experimental procedures"),"results":("result","findings"),"discussion":("discussion",),"limitations":("limitation","strengths and limitations"),"data_availability":("data availability","availability of data","data and code availability"),"funding":("funding","financial support"),"conflict_of_interest":("conflict of interest","competing interests","declaration of interests")}

def canon(v): return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"))
def digest(v): return hashlib.sha256(canon(v).encode()).hexdigest()
def local(tag): return str(tag or "").rsplit("}",1)[-1].casefold()
def pmcid(v):
    x=str(v or "").strip().upper()
    return x if re.fullmatch(r"PMC\d+",x) else None

def validate_plan(plan,maximum_items=120):
    p=dict(plan); items=p.get("items")
    if p.get("artifact_type")!="EvidenceRadar_Editions_FulltextFetchPlan" or not isinstance(items,list): raise ValueError("bad fulltext plan")
    if int(p.get("item_count") or -1)!=len(items) or len(items)>maximum_items: raise ValueError("fulltext plan count")
    if len(str(p.get("plan_binding_sha256") or ""))!=64: raise ValueError("fulltext plan binding")
    seen=set()
    for x in items:
        k=str(x.get("record_key") or "")
        if not k or k in seen or x.get("status")!="PLANNED": raise ValueError("invalid fulltext plan item")
        seen.add(k)
        if x.get("full_text_fetched") is not False or x.get("evidence_evaluated") is not False: raise ValueError("invalid fulltext plan state")
        if not isinstance(x.get("source_order"),list) or any(s not in SOURCES for s in x["source_order"]): raise ValueError("unsupported fulltext source")
    return p

def xml_ids(root):
    out={}
    for n in root.iter():
        if local(n.tag)!="article-id": continue
        kind=str(n.attrib.get("pub-id-type") or "").casefold(); text=clean_text("".join(n.itertext()))
        if kind in {"pmc","pmcid"}: out["pmcid"]=text.upper()
        elif kind=="pmid": out["pmid"]=text
        elif kind=="doi": out["doi"]=normalize_doi(text) or ""
    return out

def identity_ok(data,item):
    root=ET.fromstring(data); got=xml_ids(root); ids=item.get("identifiers") or {}
    p=pmcid(item.get("pmcid_discovered") or ids.get("pmcid"))
    if p and got.get("pmcid")==p: return True,got
    if ids.get("pmid") and got.get("pmid")==str(ids["pmid"]): return True,got
    d=normalize_doi(str(ids.get("doi") or ""))
    return bool(d and got.get("doi")==d),got

def audit_xml(data):
    root=ET.fromstring(data); titles=[]
    for sec in root.iter():
        if local(sec.tag)!="sec": continue
        title=next((c for c in list(sec) if local(c.tag)=="title"),None)
        if title is not None:
            t=clean_text("".join(title.itertext())).casefold()
            if t: titles.append(t)
    text=clean_text(" ".join(root.itertext()))
    out={"format":"JATS_XML" if local(root.tag)=="article" else "PUBLISHER_XML","text_characters":len(text),"section_title_count":len(titles),"reference_count":sum(local(n.tag)=="ref" for n in root.iter()),"table_count":sum(local(n.tag)=="table-wrap" for n in root.iter()),"figure_count":sum(local(n.tag)=="fig" for n in root.iter())}
    for k,aliases in SECTIONS.items(): out[f"has_{k}_section"]=any(any(a in t for a in aliases) for t in titles)
    return out

def open_license(url,hosts):
    try: host=(urlsplit(str(url)).hostname or "").casefold().strip(".")
    except Exception: return False
    return any(host==h or host.endswith("."+h) for h in hosts)

def crossref_links(payload,doi,hosts):
    m=payload.get("message")
    if not isinstance(m,Mapping): raise ValueError("Crossref message")
    if normalize_doi(str(m.get("DOI") or ""))!=normalize_doi(doi): return {"record_found":False,"open_license":False,"links":[]}
    licenses=[str(x.get("URL") or "").strip() for x in m.get("license") or [] if isinstance(x,Mapping) and x.get("URL")]
    is_open=any(open_license(u,hosts) for u in licenses); links=[]
    if is_open:
        for x in m.get("link") or []:
            if not isinstance(x,Mapping): continue
            ct=str(x.get("content-type") or "").casefold(); app=str(x.get("intended-application") or "").casefold(); url=str(x.get("URL") or "").strip()
            if url and ct in FORMATS and app=="text-mining": links.append({"url":url,"content_type":ct,"content_version":str(x.get("content-version") or "unspecified").casefold()})
    rank={"text/xml":0,"application/xml":1,"text/plain":2,"application/pdf":3}; links.sort(key=lambda x:(rank[x["content_type"]],0 if x["content_version"]=="vor" else 1,x["url"]))
    return {"record_found":True,"open_license":is_open,"license_urls":licenses,"links":links}

class Acquirer:
    def __init__(self,client=None,*,payload_dir,response_limit=67108864,crossref_mailto=None,open_license_hosts=None):
        self.client=client or HttpClient(timeout=30,response_limit=response_limit); self.root=Path(payload_dir); self.root.mkdir(parents=True,exist_ok=True)
        self.limit=int(response_limit); self.mailto=str(crossref_mailto or "").strip() or None; self.hosts={str(x).casefold().strip(".") for x in (open_license_hosts or ["creativecommons.org"])}
    def store(self,data,suffix):
        h=hashlib.sha256(data).hexdigest(); path=self.root/f"{h}{suffix}"
        if path.exists() and path.read_bytes()!=data: raise ValueError("fulltext hash collision")
        if not path.exists(): path.write_bytes(data)
        return h,len(data),path.name
    def epmc(self,item):
        p=pmcid(item.get("pmcid_discovered") or (item.get("identifiers") or {}).get("pmcid"))
        if not p: return {"status":"NOT_APPLICABLE","detail":"missing PMCID"}
        try:
            data=self.client.get_bytes(EUROPE_PMC.format(pmcid=p),limit=self.limit); ok,got=identity_ok(data,item)
            if not ok: return {"status":"FAILED","detail":f"identity mismatch {got}"}
            audit=audit_xml(data)
        except requests.HTTPError as e:
            code=getattr(e.response,"status_code",None)
            return {"status":"ACCESS_DENIED" if code in {401,403} else "NOT_FOUND" if code==404 else "FAILED","detail":f"HTTP {code}"}
        except Exception as e: return {"status":"FAILED","detail":f"{type(e).__name__}: {e}"}
        h,n,name=self.store(data,".xml")
        return {"status":"FOUND","source_record_id":p,"source_url":EUROPE_PMC.format(pmcid=p),"content_type":"application/xml","fulltext_sha256":h,"fulltext_bytes":n,"payload_object_name":name,"structural_audit":audit}
    def crossref(self,item):
        doi=str((item.get("identifiers") or {}).get("doi") or "").strip()
        if not doi: return {"status":"NOT_APPLICABLE","detail":"missing DOI"}
        try:
            meta=self.client.get_json(CROSSREF.format(doi=quote(doi,safe="/")),params={"mailto":self.mailto} if self.mailto else None,limit=4*1024*1024); found=crossref_links(meta,doi,self.hosts)
        except requests.HTTPError as e:
            code=getattr(e.response,"status_code",None); return {"status":"NOT_FOUND" if code==404 else "FAILED","detail":f"HTTP {code}"}
        except Exception as e: return {"status":"FAILED","detail":f"{type(e).__name__}: {e}"}
        if not found["record_found"]: return {"status":"NOT_FOUND"}
        if not found["open_license"]: return {"status":"NO_ROUTE","detail":"no recognized open license","license_urls":found.get("license_urls",[])}
        if not found["links"]: return {"status":"NO_ROUTE","detail":"open license but no text-mining link","license_urls":found.get("license_urls",[])}
        denied=missing=False; errors=[]
        for link in found["links"]:
            try:
                data=self.client.get_bytes(link["url"],limit=self.limit); ct=link["content_type"]
                if ct=="application/pdf":
                    if not data.startswith(b"%PDF-"): raise ValueError("invalid PDF header")
                    audit={"format":"PDF","bytes":len(data),"pdf_header_valid":True,"structural_sections_not_parsed":True}
                elif ct in {"text/xml","application/xml"}:
                    ET.fromstring(data); audit=audit_xml(data)
                else:
                    text=data.decode("utf-8",errors="replace")
                    if not text.strip(): raise ValueError("empty text fulltext")
                    low=text.casefold(); audit={"format":ct,"text_characters":len(text),**{f"has_{k}_section":any(a in low for a in aliases) for k,aliases in SECTIONS.items()}}
                h,n,name=self.store(data,FORMATS[ct]); return {"status":"FOUND","source_record_id":normalize_doi(doi),"source_url":link["url"],"content_type":ct,"content_version":link["content_version"],"license_urls":found.get("license_urls",[]),"fulltext_sha256":h,"fulltext_bytes":n,"payload_object_name":name,"structural_audit":audit}
            except requests.HTTPError as e:
                code=getattr(e.response,"status_code",None); denied|=code in {401,403}; missing|=code==404
                if code not in {401,403,404}: errors.append(f"HTTP {code}")
            except Exception as e: errors.append(f"{type(e).__name__}: {e}")
        if errors: return {"status":"FAILED","detail":" | ".join(errors[:5])}
        if denied: return {"status":"ACCESS_DENIED"}
        if missing: return {"status":"NOT_FOUND"}
        return {"status":"NO_ROUTE"}
    def acquire(self,item):
        attempts=[]; got=None
        for source in item.get("source_order") or []:
            r=self.epmc(item) if source=="EUROPE_PMC_FULLTEXT_XML" else self.crossref(item); status=r["status"]; attempts.append({"source":source,"status":status,"detail":r.get("detail")})
            if status=="FOUND": got={"source":source,**r}; break
        meaningful=[x for x in attempts if x["status"]!="NOT_APPLICABLE"]
        if got: final="FULLTEXT_ACQUIRED"
        elif not meaningful: final="SKIPPED_NO_FULLTEXT_SOURCE"
        elif any(x["status"]=="FAILED" for x in attempts): final="FULLTEXT_ACQUISITION_INCONCLUSIVE"
        elif any(x["status"]=="ACCESS_DENIED" for x in attempts): final="FULLTEXT_ACCESS_DENIED"
        elif any(x["status"]=="NO_ROUTE" for x in attempts): final="FULLTEXT_ROUTE_NOT_FOUND"
        elif any(x["status"]=="NOT_FOUND" for x in attempts): final="FULLTEXT_NOT_FOUND"
        else: final="FULLTEXT_ROUTE_NOT_FOUND"
        return {"ordinal":int(item.get("ordinal") or 0),"record_key":item.get("record_key"),"canonical_id":item.get("canonical_id"),"journal":item.get("journal"),"journal_slug":item.get("journal_slug"),"period_key":item.get("period_key"),"revision":item.get("revision"),"title_original":item.get("title_original"),"identifiers":dict(item.get("identifiers") or {}),"pmcid_discovered":item.get("pmcid_discovered"),"abstract_sha256":item.get("abstract_sha256"),"status":final,"attempts":attempts,"acquired_source":got.get("source") if got else None,"source_record_id":got.get("source_record_id") if got else None,"source_url":got.get("source_url") if got else None,"content_type":got.get("content_type") if got else None,"content_version":got.get("content_version") if got else None,"license_urls":list(got.get("license_urls") or []) if got else [],"fulltext_sha256":got.get("fulltext_sha256") if got else None,"fulltext_bytes":int(got.get("fulltext_bytes") or 0) if got else 0,"payload_object_name":got.get("payload_object_name") if got else None,"fulltext_structural_audit":dict(got.get("structural_audit") or {}) if got else None,"full_text_fetch_requested":True,"full_text_fetched":bool(got),"evidence_evaluated":False}

def acquire_plan(plan,*,payload_dir,client=None,maximum_items=120,response_limit=67108864,generated_at=None,crossref_mailto=None,open_license_hosts=None):
    p=validate_plan(plan,maximum_items); a=Acquirer(client,payload_dir=payload_dir,response_limit=response_limit,crossref_mailto=crossref_mailto,open_license_hosts=open_license_hosts); rows=[a.acquire(x) for x in p["items"]]
    if [x["record_key"] for x in rows]!=[x["record_key"] for x in p["items"]]: raise ValueError("fulltext receipt ordering")
    c=Counter(x["status"] for x in rows)
    if any(k not in FINAL for k in c): raise ValueError("bad fulltext status")
    rb=digest({"plan_binding_sha256":p["plan_binding_sha256"],"items":[{"record_key":x["record_key"],"status":x["status"],"attempts":x["attempts"],"acquired_source":x["acquired_source"],"source_record_id":x["source_record_id"],"fulltext_sha256":x["fulltext_sha256"],"fulltext_bytes":x["fulltext_bytes"],"audit":x["fulltext_structural_audit"]} for x in rows]})
    ready=[{"record_key":x["record_key"],"canonical_id":x["canonical_id"],"journal":x["journal"],"journal_slug":x["journal_slug"],"title_original":x["title_original"],"identifiers":x["identifiers"],"abstract_sha256":x["abstract_sha256"],"fulltext_sha256":x["fulltext_sha256"],"fulltext_bytes":x["fulltext_bytes"],"fulltext_source":x["acquired_source"],"fulltext_source_record_id":x["source_record_id"],"fulltext_structural_audit":x["fulltext_structural_audit"],"evidence_review_status":"READY","evidence_evaluated":False} for x in rows if x["status"]=="FULLTEXT_ACQUIRED"]
    eb=digest({"fulltext_receipt_binding_sha256":rb,"items":[{"record_key":x["record_key"],"fulltext_sha256":x["fulltext_sha256"]} for x in ready]}); now=generated_at or utc_now_iso()
    evidence={"schema_version":"1.0","artifact_type":"EvidenceRadar_Editions_EvidenceReviewPlan","generated_at":now,"fulltext_receipt_binding_sha256":rb,"evidence_review_plan_binding_sha256":eb,"item_count":len(ready),"scientific_boundary":"READY means full text was acquired and hash-bound; no risk-of-bias or evidence-strength judgment has been made.","items":ready}
    return {"schema_version":"1.0","artifact_type":"EvidenceRadar_Editions_FulltextAcquisitionReceipts","generated_at":now,"plan_binding_sha256":p["plan_binding_sha256"],"receipt_binding_sha256":rb,"plan_item_count":len(rows),"receipt_count":len(rows),"counts":{"fulltext_acquired":c["FULLTEXT_ACQUIRED"],"route_not_found":c["FULLTEXT_ROUTE_NOT_FOUND"],"access_denied":c["FULLTEXT_ACCESS_DENIED"],"not_found":c["FULLTEXT_NOT_FOUND"],"acquisition_inconclusive":c["FULLTEXT_ACQUISITION_INCONCLUSIVE"],"skipped_no_fulltext_source":c["SKIPPED_NO_FULLTEXT_SOURCE"],"by_status":dict(sorted(c.items())),"by_acquired_source":dict(Counter(x["acquired_source"] for x in rows if x["acquired_source"]))},"scientific_boundary":"FULLTEXT_ACQUIRED means an allowed exact-source route returned hash-bound bytes; evidence has not been evaluated.","payload_policy":{"storage":"EPHEMERAL_CONTENT_ADDRESSED_VAULT","public_receipts_contain_fulltext":False,"delete_before_artifact_upload":True},"items":rows,"evidence_review_plan":evidence}

def validate_vault(receipts,payload_dir):
    root=Path(payload_dir); expected={}
    for x in receipts.get("items") or []:
        if x.get("status")!="FULLTEXT_ACQUIRED": continue
        h=str(x.get("fulltext_sha256") or ""); name=str(x.get("payload_object_name") or "")
        if len(h)!=64 or not name.startswith(h+"."): raise ValueError("bad fulltext payload object")
        expected[name]=(int(x.get("fulltext_bytes") or 0),h)
    files=list(root.iterdir()) if root.exists() else []
    if {x.name for x in files if x.is_file()}!=set(expected): raise ValueError("fulltext vault set mismatch")
    for path in files:
        if not path.is_file(): continue
        data=path.read_bytes(); n,h=expected[path.name]
        if len(data)!=n or hashlib.sha256(data).hexdigest()!=h: raise ValueError("fulltext vault hash/size mismatch")
    return {"payload_object_count":len(expected),"payload_bytes":sum(x.stat().st_size for x in files if x.is_file())}

def delete_vault(path):
    p=Path(path)
    if p.exists():
        if p.is_symlink() or not p.is_dir(): raise ValueError("unsafe fulltext vault")
        shutil.rmtree(p)

# compatibility names
FULLTEXT_RECEIPTS_FILENAME=RECEIPTS_FILE
FULLTEXT_DISPOSITION_FILENAME=DISPOSITION_FILE
EVIDENCE_REVIEW_PLAN_FILENAME=EVIDENCE_PLAN_FILE
FulltextAcquirer=Acquirer
acquire_fulltext_plan=acquire_plan
audit_fulltext_xml=audit_xml
def parse_crossref_open_tdm_links(payload, *, doi, allowed_license_hosts):
    return crossref_links(payload, doi, allowed_license_hosts)
validate_fulltext_payload_vault=validate_vault
delete_fulltext_payload_vault=delete_vault
validate_fulltext_plan=validate_plan
