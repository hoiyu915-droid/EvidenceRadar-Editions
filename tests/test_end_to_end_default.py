import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evidenceradar_editions import complete_edition_delivery as delivery
from evidenceradar_editions.evidence_evaluation import (
    build_evaluated_edition,
    builtin_policy,
    evaluate_fulltext,
)


class EvidenceEvaluationTests(unittest.TestCase):
    def _receipt(self, payload_dir: Path, payload: bytes, *, content_type: str = "application/xml", fmt: str = "JATS_XML"):
        digest = hashlib.sha256(payload).hexdigest()
        suffix = ".pdf" if content_type == "application/pdf" else ".xml"
        name = f"{digest}{suffix}"
        (payload_dir / name).write_bytes(payload)
        return {
            "record_key": "k1", "canonical_id": "doi:10.1000/example", "journal": "Example Journal",
            "journal_slug": "example-journal", "period_key": "2026-08", "revision": 1,
            "title_original": "Randomized example", "identifiers": {"doi": "10.1000/example"},
            "status": "FULLTEXT_ACQUIRED", "abstract_sha256": "a" * 64,
            "acquired_source": "EUROPE_PMC_FULLTEXT_XML", "content_type": content_type,
            "fulltext_sha256": digest, "fulltext_bytes": len(payload), "payload_object_name": name,
            "fulltext_structural_audit": {
                "format": fmt, "has_methods_section": fmt != "PDF",
                "has_results_section": fmt != "PDF", "has_limitations_section": fmt != "PDF",
            },
        }

    def test_hash_bound_xml_gets_design_aware_reporting_audit_and_editorial_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = b'''<article><body>
            <sec><title>Methods</title><p>We randomized 120 participants. The primary outcome was prespecified. Trial registration NCT12345678. Allocation concealment used sealed opaque envelopes. Participants were blinded.</p></sec>
            <sec><title>Results</title><p>120 participants were analyzed. Risk ratio 0.80, 95% CI 0.70 to 0.92. Intention-to-treat analysis. Missing data were handled by multiple imputation.</p></sec>
            <sec><title>Limitations</title><p>Limitations are discussed.</p></sec>
            </body></article>'''
            receipt = self._receipt(root, payload)
            receipts = {"artifact_type": "EvidenceRadar_Editions_FulltextAcquisitionReceipts", "receipt_binding_sha256": "b" * 64, "items": [receipt]}
            abstract_review = {"items": [{
                "record_key": "k1", "primary_path": "RANDOMIZED_TRIAL", "abstract_information_class": "HIGH_INFORMATION",
                "fulltext_priority_score": 90, "processing_mode": "FULL",
            }]}
            evaluation = evaluate_fulltext(receipts, abstract_review, payload_dir=root, policy=builtin_policy())
            row = evaluation["items"][0]
            self.assertTrue(row["evidence_evaluated"])
            self.assertEqual(row["evaluation_status"], "EVALUATED_TEXT_FULLTEXT")
            self.assertGreaterEqual(row["reporting_coverage_fraction"], 0.75)
            self.assertFalse(row["risk_of_bias_evaluated"])
            edition = build_evaluated_edition(evaluation, policy=builtin_policy())
            self.assertEqual(edition["counts"]["featured"], 1)
            self.assertEqual(edition["items"][0]["editorial_route"], "FEATURED")

    def test_pdf_without_machine_text_ends_in_limited_review_not_fake_evaluation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            receipt = self._receipt(root, b"%PDF-1.7\nexample", content_type="application/pdf", fmt="PDF")
            receipts = {"artifact_type": "EvidenceRadar_Editions_FulltextAcquisitionReceipts", "receipt_binding_sha256": "b" * 64, "items": [receipt]}
            evaluation = evaluate_fulltext(receipts, {"items": []}, payload_dir=root, policy=builtin_policy())
            self.assertFalse(evaluation["items"][0]["evidence_evaluated"])
            self.assertEqual(evaluation["counts"]["limited_no_machine_text"], 1)
            edition = build_evaluated_edition(evaluation, policy=builtin_policy())
            self.assertEqual(edition["items"][0]["editorial_route"], "LIMITED_REVIEW")

    def test_payload_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            receipt = self._receipt(root, b"<article/>")
            receipt["fulltext_sha256"] = "0" * 64
            receipts = {"artifact_type": "EvidenceRadar_Editions_FulltextAcquisitionReceipts", "receipt_binding_sha256": "b" * 64, "items": [receipt]}
            with self.assertRaises(ValueError):
                evaluate_fulltext(receipts, {"items": []}, payload_dir=root, policy=builtin_policy())


def _abstract_plan():
    return {
        "schema_version": "2.0", "artifact_type": "EvidenceRadar_Editions_AbstractFetchPlan",
        "plan_binding_sha256": "a" * 64, "item_count": 1,
        "items": [{
            "ordinal": 1, "record_key": "k1", "canonical_id": "doi:10.1000/example",
            "journal": "Example Journal", "journal_slug": "example-journal", "period_key": "2026-08", "revision": 1,
            "title_original": "Randomized example", "identifiers": {"doi": "10.1000/example", "pmid": "123", "pmcid": "PMC1234567"},
            "source_order": ["PUBMED_PMID"], "status": "PLANNED", "abstract_fetch_requested": False,
            "abstract_acquired": False, "abstract_reviewed": False, "full_text_fetched": False, "evidence_evaluated": False,
        }],
    }


def _abstract_receipts(payload_dir: Path):
    text = "METHODS: 120 participants. RESULTS: 95% CI 1 to 2."
    data = text.encode(); digest = hashlib.sha256(data).hexdigest()
    payload_dir.mkdir(parents=True, exist_ok=True); (payload_dir / f"{digest}.txt").write_bytes(data)
    return {
        "artifact_type": "EvidenceRadar_Editions_AbstractAcquisitionReceipts", "plan_binding_sha256": "a" * 64,
        "receipt_binding_sha256": "b" * 64, "plan_item_count": 1, "receipt_count": 1, "counts": {"abstract_acquired": 1},
        "items": [{
            "record_key": "k1", "canonical_id": "doi:10.1000/example", "journal": "Example Journal",
            "journal_slug": "example-journal", "period_key": "2026-08", "revision": 1,
            "title_original": "Randomized example", "identifiers": {"doi": "10.1000/example", "pmid": "123", "pmcid": "PMC1234567"},
            "status": "ABSTRACT_ACQUIRED", "acquired_source": "PUBMED_PMID", "source_record_id": "PMC1234567",
            "abstract_sha256": digest, "abstract_bytes": len(data), "abstract_characters": len(text),
            "abstract_reviewed": False, "full_text_fetched": False, "evidence_evaluated": False,
        }],
    }


def _review_and_plan():
    plan = {"artifact_type": "EvidenceRadar_Editions_FulltextFetchPlan", "plan_binding_sha256": "d" * 64, "item_count": 1, "items": [{"record_key": "k1", "status": "PLANNED", "full_text_fetched": False, "evidence_evaluated": False}]}
    review = {
        "artifact_type": "EvidenceRadar_Editions_AbstractReview", "policy_id": "abstract-review-fulltext-v1",
        "policy_sha256": "c" * 64, "abstract_receipt_binding_sha256": "b" * 64, "abstract_review_binding_sha256": "e" * 64,
        "counts": {"abstract_acquired": 1, "fulltext_now_count": 1, "fulltext_reserve_count": 0, "no_abstract_count": 0},
        "items": [{"record_key": "k1", "primary_path": "RANDOMIZED_TRIAL", "abstract_information_class": "HIGH_INFORMATION", "fulltext_priority_score": 90, "processing_mode": "FULL", "fulltext_route": "FULLTEXT_NOW", "abstract_reviewed": True}],
        "fulltext_fetch_plan": plan,
    }
    return review, plan


def _fulltext_receipts(payload_dir: Path):
    payload = b'''<article><body><sec><title>Methods</title><p>We randomized 120 participants. Primary outcome. NCT123.</p></sec><sec><title>Results</title><p>Risk ratio 0.8, 95% CI 0.7 to 0.9.</p></sec><sec><title>Limitations</title><p>Limitations.</p></sec></body></article>'''
    digest = hashlib.sha256(payload).hexdigest(); payload_dir.mkdir(parents=True, exist_ok=True)
    name = f"{digest}.xml"; (payload_dir / name).write_bytes(payload)
    evidence = {"artifact_type": "EvidenceRadar_Editions_EvidenceReviewPlan", "evidence_review_plan_binding_sha256": "f" * 64, "item_count": 1, "items": []}
    return {
        "artifact_type": "EvidenceRadar_Editions_FulltextAcquisitionReceipts", "plan_binding_sha256": "d" * 64,
        "receipt_binding_sha256": "1" * 64, "plan_item_count": 1, "receipt_count": 1,
        "counts": {"fulltext_acquired": 1, "route_not_found": 0, "access_denied": 0, "not_found": 0, "acquisition_inconclusive": 0, "skipped_no_fulltext_source": 0},
        "items": [{
            "record_key": "k1", "canonical_id": "doi:10.1000/example", "journal": "Example Journal", "journal_slug": "example-journal",
            "period_key": "2026-08", "revision": 1, "title_original": "Randomized example", "identifiers": {"doi": "10.1000/example"},
            "status": "FULLTEXT_ACQUIRED", "abstract_sha256": "a" * 64, "acquired_source": "EUROPE_PMC_FULLTEXT_XML", "content_type": "application/xml",
            "fulltext_sha256": digest, "fulltext_bytes": len(payload), "payload_object_name": name,
            "fulltext_structural_audit": {"format": "JATS_XML", "has_methods_section": True, "has_results_section": True, "has_limitations_section": True},
            "evidence_evaluated": False,
        }],
        "evidence_review_plan": evidence,
    }


class CompleteEditionDeliveryTests(unittest.TestCase):
    def test_default_pipeline_reaches_evidence_evaluation_and_final_editorial_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); site, work = root / "site", root / "work"; ap, fp = root / "abstract", root / "fulltext"
            site.mkdir(); (site / "abstract-fetch-plan.json").write_text(json.dumps(_abstract_plan()), encoding="utf-8")
            (site / "editorial-shortlist.json").write_text(json.dumps({"items": []}), encoding="utf-8")
            (site / "index.html").write_text('<html><body><main class="shell">portal</main></body></html>', encoding="utf-8")
            (site / "index.json").write_text("{}", encoding="utf-8"); (site / "links.json").write_text(json.dumps({"base_url": "https://example.test/"}), encoding="utf-8")
            ar = _abstract_receipts(ap); review, fplan = _review_and_plan(); fr = _fulltext_receipts(fp)
            abstract_policy = {"artifact_type": "EvidenceRadar_Editions_AbstractReviewPolicy", "policy_id": "abstract-review-fulltext-v1", "fulltext_response_limit_bytes": 1024 * 1024, "crossref_open_license_hosts": ["creativecommons.org"]}
            with patch.object(delivery, "acquire_plan", return_value=ar), patch.object(delivery, "validate_payload_vault", return_value={"payload_object_count": 1, "payload_bytes": 50}), patch.object(delivery, "attach_acquisition_to_site"), patch.object(delivery, "load_abstract_review_policy", return_value=abstract_policy), patch.object(delivery, "build_abstract_review", return_value=(review, fplan)), patch.object(delivery, "acquire_fulltext_plan", return_value=fr), patch.object(delivery, "validate_fulltext_payload_vault", return_value={"payload_object_count": 1, "payload_bytes": fr["items"][0]["fulltext_bytes"]}), patch.object(delivery, "load_evidence_evaluation_policy", return_value=builtin_policy()):
                result = delivery.run_delivery(site_dir=site, work_dir=work, abstract_payload_dir=ap, fulltext_payload_dir=fp, catalog_root=root / "catalog")
            self.assertFalse(ap.exists()); self.assertFalse(fp.exists())
            self.assertEqual(result["evidence_evaluation"]["counts"]["evidence_evaluated"], 1)
            self.assertEqual(result["evaluated_edition"]["counts"]["featured"], 1)
            self.assertTrue((site / "evidence-evaluation.html").is_file()); self.assertTrue((site / "evaluated-edition.html").is_file())
            self.assertTrue((work / delivery.COMPLETE_MANIFEST_FILENAME).is_file())
            self.assertEqual(result["fulltext_disposition"]["evidence_evaluated_count"], 1)


class EndToEndWorkflowContractTests(unittest.TestCase):
    def test_live_edition_publishes_merges_and_dispatches_default_pipeline(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / ".github" / "workflows" / "live-edition.yml").read_text(encoding="utf-8")
        for token in ("contents: write", "pull-requests: write", "actions: write", "python -m evidenceradar_editions publish", "gh pr create", "/pulls/$pr_number/merge", "actions/workflows/pages.yml/dispatches", "gh run watch"):
            self.assertIn(token, text)

    def test_pages_uses_complete_delivery_by_default(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
        for token in ("complete_edition_delivery", "--allow-untranslated", "evidence-evaluation.json", "evaluated-edition.json", "evidence_evaluated"):
            self.assertIn(token, text)


if __name__ == "__main__":
    unittest.main()
