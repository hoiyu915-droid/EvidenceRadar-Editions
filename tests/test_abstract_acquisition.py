import json
import tempfile
import unittest
from pathlib import Path

from evidenceradar_editions.abstract_acquisition import acquire_plan, parse_crossref_result, parse_europe_pmc_result, parse_pubmed_abstracts, validate_payload_vault

PUBMED_XML = b'''<?xml version="1.0"?><PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>123</PMID><Article><Abstract><AbstractText Label="BACKGROUND">Background text.</AbstractText><AbstractText Label="RESULTS">Results text.</AbstractText></Abstract></Article></MedlineCitation><PubmedData><ArticleIdList><ArticleId IdType="pubmed">123</ArticleId><ArticleId IdType="doi">10.1000/example</ArticleId><ArticleId IdType="pmc">PMC123</ArticleId></ArticleIdList></PubmedData></PubmedArticle><PubmedArticle><MedlineCitation><PMID>456</PMID><Article /></MedlineCitation><PubmedData><ArticleIdList /></PubmedData></PubmedArticle></PubmedArticleSet>'''

class FakeClient:
    def __init__(self): self.bytes_calls=[]; self.json_calls=[]
    def get_bytes(self, url, *, params=None, limit=None): self.bytes_calls.append((url,dict(params or {}))); return PUBMED_XML
    def get_json(self, url, *, params=None, limit=None):
        params=dict(params or {}); self.json_calls.append((url,params))
        if "europepmc" in url:
            query=params.get("query","")
            if "PMC999" in query: return {"resultList":{"result":[{"pmcid":"PMC999","pmid":"999","doi":"10.1000/pmc","abstractText":"PMC abstract."}]}}
            if "10.1000/noabstract" in query: return {"resultList":{"result":[{"doi":"10.1000/noabstract","pmid":"777"}]}}
            return {"resultList":{"result":[]}}
        if "crossref" in url: return {"message":{"DOI":"10.1000/crossref","abstract":"<jats:p>Crossref abstract.</jats:p>"}}
        raise AssertionError(url)

def plan(items):
    return {"schema_version":"1.0","artifact_type":"EvidenceRadar_Editions_AbstractFetchPlan","plan_binding_sha256":"a"*64,"item_count":len(items),"items":[{"ordinal":i+1,"record_key":f"journal|2026-08|1|{item['canonical_id']}","canonical_id":item["canonical_id"],"journal":"Example Journal","journal_slug":"example-journal","period_key":"2026-08","revision":1,"title_original":f"Example {i}","identifiers":item["identifiers"],"source_order":item["source_order"],"status":"PLANNED","abstract_fetch_requested":False,"abstract_acquired":False,"abstract_reviewed":False,"full_text_fetched":False,"evidence_evaluated":False} for i,item in enumerate(items)]}

class AbstractAcquisitionTests(unittest.TestCase):
    def test_pubmed_parser_preserves_sections_without_markup(self):
        values=parse_pubmed_abstracts(PUBMED_XML)
        self.assertEqual(values["123"]["abstract"],"BACKGROUND: Background text.\n\nRESULTS: Results text.")
        self.assertEqual(values["123"]["doi"],"10.1000/example"); self.assertIsNone(values["456"]["abstract"])
    def test_exact_europe_pmc_and_crossref_parsers(self):
        epmc=parse_europe_pmc_result({"resultList":{"result":[{"pmcid":"PMC123","pmid":"123","doi":"10.1000/example","abstractText":"Exact abstract."}]}},kind="pmcid",value="PMC123")
        self.assertTrue(epmc["record_found"]); self.assertEqual(epmc["abstract"],"Exact abstract.")
        crossref=parse_crossref_result({"message":{"DOI":"10.1000/example","abstract":"<jats:p>Deposited abstract.</jats:p>"}},doi="10.1000/example")
        self.assertEqual(crossref["abstract"],"Deposited abstract.")
    def test_plan_execution_distinguishes_acquired_absent_and_not_found(self):
        value=plan([{"canonical_id":"pmid:123","identifiers":{"pmid":"123","pmcid":None,"doi":"10.1000/example"},"source_order":["PUBMED_PMID","EUROPE_PMC_DOI","CROSSREF_DOI"]},{"canonical_id":"doi:10.1000/noabstract","identifiers":{"pmid":None,"pmcid":None,"doi":"10.1000/noabstract"},"source_order":["EUROPE_PMC_DOI"]},{"canonical_id":"doi:10.1000/missing","identifiers":{"pmid":None,"pmcid":None,"doi":"10.1000/missing"},"source_order":["EUROPE_PMC_DOI"]},{"canonical_id":"doi:10.1000/crossref","identifiers":{"pmid":None,"pmcid":None,"doi":"10.1000/crossref"},"source_order":["EUROPE_PMC_DOI","CROSSREF_DOI"]}])
        with tempfile.TemporaryDirectory() as tmp:
            payload=Path(tmp)/"payload"; receipts=acquire_plan(value,payload_dir=payload,client=FakeClient(),generated_at="2026-08-15T00:00:00Z")
            self.assertEqual([x["status"] for x in receipts["items"]],["ABSTRACT_ACQUIRED","ABSTRACT_NOT_PRESENT","RECORD_NOT_FOUND","ABSTRACT_ACQUIRED"])
            self.assertEqual(receipts["counts"]["abstract_acquired"],2); self.assertTrue(all(x["abstract_reviewed"] is False for x in receipts["items"])); self.assertTrue(all(x["full_text_fetched"] is False for x in receipts["items"])); self.assertEqual(validate_payload_vault(receipts,payload)["payload_object_count"],2)
    def test_pmcid_source_precedes_cached_pubmed(self):
        value=plan([{"canonical_id":"pmcid:PMC999","identifiers":{"pmid":"123","pmcid":"PMC999","doi":"10.1000/pmc"},"source_order":["EUROPE_PMC_PMCID","PUBMED_PMID","EUROPE_PMC_PMID","EUROPE_PMC_DOI","CROSSREF_DOI"]}])
        with tempfile.TemporaryDirectory() as tmp:
            item=acquire_plan(value,payload_dir=Path(tmp)/"payload",client=FakeClient(),generated_at="2026-08-15T00:00:00Z")["items"][0]
            self.assertEqual(item["status"],"ABSTRACT_ACQUIRED"); self.assertEqual(item["acquired_source"],"EUROPE_PMC_PMCID"); self.assertEqual(item["attempts"][0]["source"],"EUROPE_PMC_PMCID")
    def test_public_receipt_never_contains_abstract_text(self):
        value=plan([{"canonical_id":"pmid:123","identifiers":{"pmid":"123","pmcid":None,"doi":None},"source_order":["PUBMED_PMID"]}])
        with tempfile.TemporaryDirectory() as tmp:
            serialized=json.dumps(acquire_plan(value,payload_dir=Path(tmp)/"payload",client=FakeClient(),generated_at="2026-08-15T00:00:00Z"),ensure_ascii=False)
            self.assertNotIn("Background text.",serialized); self.assertNotIn("Results text.",serialized); self.assertNotIn('"abstract_text"',serialized); self.assertNotIn('"abstractText"',serialized)

if __name__ == "__main__": unittest.main()
