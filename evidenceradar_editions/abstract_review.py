from __future__ import annotations
import hashlib,json,re,unicodedata
from collections import Counter,defaultdict
from pathlib import Path
from typing import Any,Mapping
from .utils import utc_now_iso

POLICY_FILE="abstract-review-policy.json"
REVIEW_FILE="abstract-review.json"
REVIEW_PAGE="abstract-review.html"
FULLTEXT_PLAN_FILE="fulltext-fetch-plan.json"
MODES=("FULL","TRIAGE","INDEX_ONLY","SUSPENDED")
PATH_BASE={"GUIDANCE":80,"EVIDENCE_SYNTHESIS":80,"RANDOMIZED_TRIAL":80,"SAFETY_SIGNAL":78,"REPLICATION_VALIDATION":76,"PROSPECTIVE_LONGITUDINAL":70,"RESOURCE_BENCHMARK":68,"OBSERVATIONAL_DESIGN":64,"SURVEY":55,"PROTOCOL":40,"CASE_REPORT":45}
SIG_WEIGHT={"METHODS_SECTION":5,"RESULTS_SECTION":7,"SAMPLE_SIZE":5,"EFFECT_ESTIMATE":5,"REGISTRATION":4,"MULTICENTER_OR_EXTERNAL_VALIDATION":4,"LIMITATIONS":2,"DATA_OR_CODE_AVAILABILITY":2,"SHORT_ABSTRACT":-8,"NO_RESULT_SIGNAL":-6}
PATTERNS={
"METHODS_SECTION":re.compile(r"(?i)(?:^|\n|\b)(?:methods?|methodology|materials and methods?)\s*[:.\-]"),
"RESULTS_SECTION":re.compile(r"(?i)(?:^|\n|\b)(?:results?|findings?)\s*[:.\-]"),
"SAMPLE_SIZE":re.compile(r"(?i)(?:\bn\s*=\s*\d{2,}\b|\b(?:included|enrolled|randomi[sz]ed|participants?|patients?|subjects?|samples?)\s+(?:were\s+)?\d{2,}\b|\b\d{2,}\s+(?:participants?|patients?|subjects?|samples?)\b)"),
"EFFECT_ESTIMATE":re.compile(r"(?i)(?:95\s*%\s*CI|confidence interval|hazard ratio|odds ratio|risk ratio|relative risk|mean difference|\bSMD\b|\bHR\s*[=:]|\bOR\s*[=:]|\bRR\s*[=:]|\bp\s*[<=>]\s*0?\.\d+)"),
"REGISTRATION":re.compile(r"(?i)(?:clinicaltrials\.gov|trial registration|registered at|prospero|preregister|pre-registr)"),
"MULTICENTER_OR_EXTERNAL_VALIDATION":re.compile(r"(?i)(?:multi[- ]?cent(?:er|re)|multi[- ]?site|external validation|independent validation|held[- ]?out (?:cohort|dataset|test set))"),
"LIMITATIONS":re.compile(r"(?i)\blimitations?\b"),
"DATA_OR_CODE_AVAILABILITY":re.compile(r"(?i)(?:data availability|code (?:is|are) available|github\.com|open source|publicly available dataset)"),
}
RESULT_SIGNAL=re.compile(r"(?i)(?:\bresults?\b|\bfindings?\b|\bwe found\b|\bwas associated\b|\bwere associated\b|\bsignificantly\b|95\s*%\s*CI|\bp\s*[<=>]\s*0?\.\d+)")
WORD=re.compile(r"[A-Za-z0-9]+")
STOP=set("a an the of in on for to and or with from by study analysis effect impact association using based results methods randomized trial review meta cohort prospective retrospective validation safety data".split())

def canon(v): return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"))
def digest(v): return hashlib.sha256(canon(v).encode()).hexdigest()

def builtin_policy():
    return {"schema_version":"1.0","artifact_type":"EvidenceRadar_Editions_AbstractReviewPolicy","policy_id":"abstract-review-fulltext-v1","semantics":"Deterministic structural review of acquired abstract text for allocating bounded full-text acquisition. It is not evidence-quality grading, clinical recommendation, novelty assessment, or full-text evidence evaluation.","fulltext_fetch_target":120,"journal_fetch_caps":{"FULL":20,"TRIAGE":30,"INDEX_ONLY":4,"SUSPENDED":0},"minimum_abstract_characters":250,"impact_percentile_weight":0.1,"prefetch_candidate_bonus":8,"path_base_priority":PATH_BASE,"signal_weights":SIG_WEIGHT,"near_duplicate_jaccard_threshold":0.85,"crossref_open_license_hosts":["creativecommons.org"],"fulltext_response_limit_bytes":67108864}

def validate_policy(raw):
    p=dict(raw)
    if p.get("artifact_type")!="EvidenceRadar_Editions_AbstractReviewPolicy": raise ValueError("unexpected abstract review policy")
    p["fulltext_fetch_target"]=int(p["fulltext_fetch_target"]); p["minimum_abstract_characters"]=int(p["minimum_abstract_characters"])
    if not 1<=p["fulltext_fetch_target"]<=1000: raise ValueError("invalid fulltext target")
    caps={k:int(v) for k,v in dict(p["journal_fetch_caps"]).items()}
    if set(caps)!=set(MODES): raise ValueError("invalid journal caps")
    p["journal_fetch_caps"]=caps; p["impact_percentile_weight"]=float(p.get("impact_percentile_weight",.1))
    p["prefetch_candidate_bonus"]=int(p.get("prefetch_candidate_bonus",8)); p["near_duplicate_jaccard_threshold"]=float(p.get("near_duplicate_jaccard_threshold",.85))
    p["path_base_priority"]={str(k):int(v) for k,v in dict(p["path_base_priority"]).items()}; p["signal_weights"]={str(k):int(v) for k,v in dict(p["signal_weights"]).items()}
    p["crossref_open_license_hosts"]=[str(x).casefold().strip(".") for x in p.get("crossref_open_license_hosts",["creativecommons.org"])]
    p["fulltext_response_limit_bytes"]=int(p.get("fulltext_response_limit_bytes",67108864))
    return p

def load_policy(root=Path("catalog")):
    path=Path(root)/POLICY_FILE
    return validate_policy(json.loads(path.read_text()) if path.is_file() else builtin_policy())

def _tokens(s):
    return {x for x in WORD.findall(unicodedata.normalize("NFKD",str(s or "")).casefold()) if len(x)>2 and x not in STOP}
def _jac(a,b):
    x,y=_tokens(a),_tokens(b); return len(x&y)/len(x|y) if x and y else 0.0

def _text(receipt,payload_dir):
    h=str(receipt.get("abstract_sha256") or ""); path=Path(payload_dir)/f"{h}.txt"
    data=path.read_bytes()
    if len(h)!=64 or hashlib.sha256(data).hexdigest()!=h: raise ValueError("abstract payload hash mismatch")
    text=data.decode()
    if len(data)!=int(receipt.get("abstract_bytes") or -1) or len(text)!=int(receipt.get("abstract_characters") or -1): raise ValueError("abstract payload size mismatch")
    return text

def _signals(text,p):
    sig=[name for name,rx in PATTERNS.items() if rx.search(text)]
    if len(text)<p["minimum_abstract_characters"]: sig.append("SHORT_ABSTRACT")
    if not RESULT_SIGNAL.search(text): sig.append("NO_RESULT_SIGNAL")
    return sig,sum(p["signal_weights"].get(x,0) for x in sig)

def _review(receipt,meta,text,p):
    path=str(meta.get("primary_path") or "UNKNOWN"); base=p["path_base_priority"].get(path,50)
    if meta.get("prefetch_route")=="FETCH_CANDIDATE": base+=p["prefetch_candidate_bonus"]; basis="METRIC_INDEPENDENT_PREFETCH_CANDIDATE"
    else: basis="METRIC_AWARE_RESERVE"
    sig,adj=_signals(text,p); prior=meta.get("journal_impact_prior") or {}
    try: pct=max(0,min(100,float(prior.get("registry_category_percentile",50))))
    except Exception: pct=50.0
    metric=round((pct-50)*p["impact_percentile_weight"]); score=base+adj+metric
    info="HIGH_INFORMATION" if "RESULTS_SECTION" in sig and ("METHODS_SECTION" in sig or "SAMPLE_SIZE" in sig) and "NO_RESULT_SIGNAL" not in sig else "LOW_INFORMATION" if "SHORT_ABSTRACT" in sig or "NO_RESULT_SIGNAL" in sig else "MODERATE_INFORMATION"
    return {"record_key":receipt["record_key"],"canonical_id":receipt.get("canonical_id"),"journal":receipt.get("journal"),"journal_slug":receipt.get("journal_slug"),"period_key":receipt.get("period_key"),"revision":receipt.get("revision"),"title_original":receipt.get("title_original"),"identifiers":dict(receipt.get("identifiers") or {}),"abstract_sha256":receipt.get("abstract_sha256"),"abstract_bytes":receipt.get("abstract_bytes"),"abstract_characters":receipt.get("abstract_characters"),"abstract_source_record_id":receipt.get("source_record_id"),"abstract_reviewed":True,"review_basis":"RULE_BASED_STRUCTURAL_ABSTRACT_TEXT","abstract_information_class":info,"abstract_signals":sig,"fulltext_priority_score":score,"priority_components":{"path_base_and_prefetch":base,"abstract_signal_adjustment":adj,"journal_metric_adjustment":metric},"primary_path":path,"prefetch_route":meta.get("prefetch_route"),"prefetch_score":int(meta.get("prefetch_score") or 0),"processing_mode":meta.get("processing_mode") or "FULL","journal_registry_category_percentile":pct,"selection_basis":basis,"topic_signature":meta.get("topic_signature"),"full_text_fetch_requested":False,"full_text_fetched":False,"evidence_evaluated":False}

def _ordered(rows):
    groups=defaultdict(list)
    for x in rows: groups[str(x.get("journal_slug") or "")].append(x)
    for v in groups.values(): v.sort(key=lambda x:(-x["fulltext_priority_score"],-x["journal_registry_category_percentile"],-x["prefetch_score"],str(x.get("title_original") or "").casefold()))
    order=sorted(groups,key=lambda s:(-groups[s][0]["fulltext_priority_score"],-groups[s][0]["journal_registry_category_percentile"],s))
    out=[]
    while any(groups.values()):
        for s in order:
            if groups[s]: out.append(groups[s].pop(0))
    return out

def _select(rows,p):
    out=[]; why={}; jc=Counter(); titles=defaultdict(list)
    for x in _ordered(rows):
        if len(out)>=min(p["fulltext_fetch_target"],len(rows)): break
        slug=str(x.get("journal_slug") or ""); cap=p["journal_fetch_caps"].get(str(x.get("processing_mode") or "FULL"),0)
        if jc[slug]>=cap: why[x["record_key"]]=["JOURNAL_FULLTEXT_CAP"]; continue
        title=str(x.get("title_original") or "")
        if any(_jac(title,t)>=p["near_duplicate_jaccard_threshold"] for t in titles[slug]): why[x["record_key"]]=["NEAR_DUPLICATE_ABSTRACT_CANDIDATE"]; continue
        out.append(x); jc[slug]+=1; titles[slug].append(title); why[x["record_key"]]=["ABSTRACT_STRUCTURAL_REVIEW",f"INFORMATION_CLASS:{x['abstract_information_class']}",f"PRIMARY_PATH:{x['primary_path']}"]
    return out,why

def _pmcid(r):
    v=str((r.get("identifiers") or {}).get("pmcid") or "").upper().strip()
    if v.startswith("PMC"): return v
    v=str(r.get("source_record_id") or "").upper().strip()
    return v if v.startswith("PMC") else None

def build_review(receipts,shortlist,*,payload_dir,policy=None,generated_at=None):
    p=validate_policy(policy or builtin_policy())
    if receipts.get("artifact_type")!="EvidenceRadar_Editions_AbstractAcquisitionReceipts": raise ValueError("bad acquisition receipts")
    meta={str(x.get("record_key") or ""):x for x in shortlist.get("items") or [] if isinstance(x,Mapping)}
    rows=[]; bykey={}
    for r in receipts.get("items") or []:
        key=str(r.get("record_key") or ""); bykey[key]=r
        if r.get("status")!="ABSTRACT_ACQUIRED":
            rows.append({"record_key":key,"canonical_id":r.get("canonical_id"),"journal":r.get("journal"),"journal_slug":r.get("journal_slug"),"period_key":r.get("period_key"),"revision":r.get("revision"),"title_original":r.get("title_original"),"identifiers":dict(r.get("identifiers") or {}),"acquisition_status":r.get("status"),"abstract_reviewed":False,"fulltext_route":"NO_ABSTRACT","full_text_fetch_requested":False,"full_text_fetched":False,"evidence_evaluated":False}); continue
        if key not in meta: raise ValueError(f"shortlist missing {key}")
        rows.append(_review(r,meta[key],_text(r,payload_dir),p))
    reviewed=[x for x in rows if x["abstract_reviewed"]]; selected,why=_select(reviewed,p); keys={x["record_key"] for x in selected}
    for x in reviewed:
        x["fulltext_route"]="FULLTEXT_NOW" if x["record_key"] in keys else "FULLTEXT_RESERVE"
        x["decision_reasons"]=why.get(x["record_key"],["FULLTEXT_GLOBAL_TARGET_OR_RELATIVE_PRIORITY"])
    pb=digest(p); rb=digest({"policy_sha256":pb,"abstract_receipt_binding_sha256":receipts.get("receipt_binding_sha256"),"items":[{"record_key":x["record_key"],"abstract_sha256":x.get("abstract_sha256"),"abstract_reviewed":x["abstract_reviewed"],"fulltext_route":x["fulltext_route"],"score":x.get("fulltext_priority_score"),"signals":x.get("abstract_signals"),"reasons":x.get("decision_reasons")} for x in sorted(rows,key=lambda z:z["record_key"])]})
    plan=[]
    for i,x in enumerate(selected,1):
        r=bykey[x["record_key"]]; sources=[]
        pmc=_pmcid(r)
        if pmc: sources.append("EUROPE_PMC_FULLTEXT_XML")
        if (r.get("identifiers") or {}).get("doi"): sources.append("CROSSREF_OPEN_TDM_LINK")
        plan.append({"ordinal":i,"record_key":x["record_key"],"canonical_id":x.get("canonical_id"),"journal":x.get("journal"),"journal_slug":x.get("journal_slug"),"period_key":x.get("period_key"),"revision":x.get("revision"),"title_original":x.get("title_original"),"identifiers":dict(x.get("identifiers") or {}),"pmcid_discovered":pmc,"abstract_sha256":x.get("abstract_sha256"),"abstract_review_binding_sha256":rb,"source_order":sources,"fulltext_priority_score":x["fulltext_priority_score"],"abstract_information_class":x["abstract_information_class"],"primary_path":x["primary_path"],"status":"PLANNED","full_text_fetch_requested":False,"full_text_fetched":False,"evidence_evaluated":False})
    fb=digest({"abstract_review_binding_sha256":rb,"items":[{"record_key":x["record_key"],"abstract_sha256":x["abstract_sha256"],"source_order":x["source_order"],"pmcid_discovered":x["pmcid_discovered"]} for x in plan]}); now=generated_at or utc_now_iso()
    fp={"schema_version":"1.0","artifact_type":"EvidenceRadar_Editions_FulltextFetchPlan","generated_at":now,"abstract_review_binding_sha256":rb,"plan_binding_sha256":fb,"item_count":len(plan),"target":p["fulltext_fetch_target"],"semantics":"Bounded full-text acquisition plan produced after structural abstract review. Selection is independent of full-text accessibility.","items":plan}
    c=Counter(x["fulltext_route"] for x in rows)
    review={"schema_version":"1.0","artifact_type":"EvidenceRadar_Editions_AbstractReview","generated_at":now,"policy_id":p["policy_id"],"policy_sha256":pb,"abstract_receipt_binding_sha256":receipts.get("receipt_binding_sha256"),"abstract_review_binding_sha256":rb,"semantics":p["semantics"],"scientific_boundary":"abstract_reviewed=true means deterministic structural signals were read from the acquired abstract text; it is not evidence-quality or risk-of-bias evaluation.","counts":{"planned_abstracts":int(receipts.get("plan_item_count") or 0),"abstract_acquired":sum(x["abstract_reviewed"] for x in rows),"abstract_not_reviewed":sum(not x["abstract_reviewed"] for x in rows),"fulltext_now_target":p["fulltext_fetch_target"],"fulltext_now_count":c["FULLTEXT_NOW"],"fulltext_reserve_count":c["FULLTEXT_RESERVE"],"no_abstract_count":c["NO_ABSTRACT"]},"fulltext_now_path_counts":dict(Counter(x.get("primary_path") for x in rows if x["fulltext_route"]=="FULLTEXT_NOW")),"items":sorted(rows,key=lambda x:({"FULLTEXT_NOW":0,"FULLTEXT_RESERVE":1,"NO_ABSTRACT":2}[x["fulltext_route"]],-int(x.get("fulltext_priority_score") or -9999),str(x.get("journal") or "").casefold())),"fulltext_fetch_plan":fp}
    return review,fp

# compatibility names used by delivery
ABSTRACT_REVIEW_POLICY_FILENAME=POLICY_FILE
ABSTRACT_REVIEW_FILENAME=REVIEW_FILE
ABSTRACT_REVIEW_PAGE_FILENAME=REVIEW_PAGE
FULLTEXT_FETCH_PLAN_FILENAME=FULLTEXT_PLAN_FILE
builtin_abstract_review_policy=builtin_policy
validate_abstract_review_policy=validate_policy
load_abstract_review_policy=load_policy
build_abstract_review=build_review
