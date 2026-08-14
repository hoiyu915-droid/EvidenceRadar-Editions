import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evidenceradar_editions import abstract_acquisition_delivery as delivery

def planned_item():
    return {"ordinal":1,"record_key":"example|2026-08|1|doi:10.1000/example","canonical_id":"doi:10.1000/example","journal":"Example Journal","journal_slug":"example-journal","period_key":"2026-08","revision":1,"title_original":"Example abstract acquisition record","identifiers":{"doi":"10.1000/example","pmid":None,"pmcid":None},"source_order":["CROSSREF_DOI"],"status":"PLANNED","abstract_fetch_requested":False,"abstract_acquired":False,"abstract_reviewed":False,"full_text_fetched":False,"evidence_evaluated":False}

def fake_receipts():
    return {"schema_version":"1.0","artifact_type":"EvidenceRadar_Editions_AbstractAcquisitionReceipts","generated_at":"2026-08-15T00:00:00Z","plan_binding_sha256":"a"*64,"receipt_binding_sha256":"b"*64,"plan_item_count":1,"receipt_count":1,"counts":{"abstract_acquired":1,"abstract_not_present":0,"record_not_found":0,"acquisition_inconclusive":0,"skipped_no_identifier":0,"by_status":{"ABSTRACT_ACQUIRED":1}},"scientific_boundary":"No review.","payload_policy":{"storage":"EPHEMERAL_CONTENT_ADDRESSED_VAULT","public_receipts_contain_abstract_text":False,"delete_before_artifact_upload":True},"items":[{"ordinal":1,"record_key":planned_item()["record_key"],"canonical_id":"doi:10.1000/example","journal":"Example Journal","journal_slug":"example-journal","period_key":"2026-08","revision":1,"title_original":"Example abstract acquisition record","identifiers":{"doi":"10.1000/example","pmid":None,"pmcid":None},"planned_source_order":["CROSSREF_DOI"],"status":"ABSTRACT_ACQUIRED","attempts":[{"source":"CROSSREF_DOI","status":"FOUND_WITH_ABSTRACT"}],"acquired_source":"CROSSREF_DOI","source_record_id":"10.1000/example","abstract_sha256":"c"*64,"abstract_bytes":20,"abstract_characters":20,"abstract_fetch_requested":True,"abstract_acquired":True,"abstract_reviewed":False,"full_text_fetched":False,"evidence_evaluated":False}]}

class AbstractAcquisitionDeliveryTests(unittest.TestCase):
    def test_attach_site_publishes_only_sanitized_receipts(self):
        with tempfile.TemporaryDirectory() as tmp:
            site=Path(tmp); (site/"index.html").write_text('<html><body><main class="shell">portal</main></body></html>',encoding="utf-8"); (site/"index.json").write_text("{}",encoding="utf-8"); (site/"links.json").write_text(json.dumps({"base_url":"https://example.test/"}),encoding="utf-8")
            delivery.attach_acquisition_to_site(site,fake_receipts()); public=json.loads((site/"abstract-acquisition.json").read_text(encoding="utf-8")); self.assertEqual(public["counts"]["abstract_acquired"],1); self.assertFalse(public["payload_policy"]["public_receipts_contain_abstract_text"]); serialized=json.dumps(public,ensure_ascii=False); self.assertNotIn("abstract_text",serialized); self.assertNotIn("payload_text",serialized); self.assertIn("abstract-acquisition.html",(site/"index.html").read_text(encoding="utf-8")); self.assertEqual(json.loads((site/"links.json").read_text(encoding="utf-8"))["abstract_acquisition_url"],"https://example.test/abstract-acquisition.html")
    def test_run_delivery_deletes_payload_before_safe_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); site=root/"site"; work=root/"work"; payload=root/"payload"; site.mkdir(); plan={"schema_version":"1.0","artifact_type":"EvidenceRadar_Editions_AbstractFetchPlan","plan_binding_sha256":"a"*64,"item_count":1,"items":[planned_item()]}; (site/"abstract-fetch-plan.json").write_text(json.dumps(plan),encoding="utf-8"); (site/"index.html").write_text('<html><body><main class="shell">portal</main></body></html>',encoding="utf-8"); (site/"index.json").write_text("{}",encoding="utf-8"); (site/"links.json").write_text(json.dumps({"base_url":"https://example.test/"}),encoding="utf-8")
            def fake_acquire(*args,**kwargs): payload.mkdir(parents=True,exist_ok=True); (payload/("c"*64+".txt")).write_text("x"*20,encoding="utf-8"); return fake_receipts()
            with patch.object(delivery,"acquire_plan",side_effect=fake_acquire), patch.object(delivery,"validate_payload_vault",return_value={"payload_object_count":1,"payload_bytes":20}): result=delivery.run_delivery(site_dir=site,work_dir=work,payload_dir=payload)
            self.assertFalse(payload.exists()); self.assertEqual(result["disposition"]["disposition"],"DELETED_BEFORE_ARTIFACT_UPLOAD"); self.assertTrue((work/"abstract-acquisition-receipts.json").is_file()); self.assertTrue((work/"abstract-acquisition-manifest.json").is_file()); self.assertTrue((work/"abstract-payload-disposition.json").is_file()); self.assertTrue((site/"abstract-acquisition.json").is_file())

if __name__ == "__main__": unittest.main()
