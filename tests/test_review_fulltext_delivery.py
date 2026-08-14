import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evidenceradar_editions import review_fulltext_delivery as delivery


def _abstract_plan():
    return {
        "schema_version": "2.0",
        "artifact_type": "EvidenceRadar_Editions_AbstractFetchPlan",
        "plan_binding_sha256": "a" * 64,
        "item_count": 1,
        "items": [{
            "ordinal": 1,
            "record_key": "k1",
            "canonical_id": "doi:10.1000/example",
            "journal": "Example Journal",
            "journal_slug": "example-journal",
            "period_key": "2026-08",
            "revision": 1,
            "title_original": "Example",
            "identifiers": {"doi": "10.1000/example", "pmid": "123", "pmcid": "PMC1234567"},
            "source_order": ["PUBMED_PMID"],
            "status": "PLANNED",
            "abstract_fetch_requested": False,
            "abstract_acquired": False,
            "abstract_reviewed": False,
            "full_text_fetched": False,
            "evidence_evaluated": False,
        }],
    }


def _abstract_receipts(payload_dir):
    text = "METHODS: 120 participants. RESULTS: 95% CI 1 to 2."
    payload = text.encode()
    digest = hashlib.sha256(payload).hexdigest()
    payload_dir.mkdir(parents=True, exist_ok=True)
    (payload_dir / f"{digest}.txt").write_bytes(payload)
    return {
        "artifact_type": "EvidenceRadar_Editions_AbstractAcquisitionReceipts",
        "plan_binding_sha256": "a" * 64,
        "receipt_binding_sha256": "b" * 64,
        "plan_item_count": 1,
        "receipt_count": 1,
        "counts": {"abstract_acquired": 1},
        "items": [{
            "record_key": "k1",
            "canonical_id": "doi:10.1000/example",
            "journal": "Example Journal",
            "journal_slug": "example-journal",
            "period_key": "2026-08",
            "revision": 1,
            "title_original": "Example",
            "identifiers": {"doi": "10.1000/example", "pmid": "123", "pmcid": "PMC1234567"},
            "status": "ABSTRACT_ACQUIRED",
            "acquired_source": "PUBMED_PMID",
            "source_record_id": "PMC1234567",
            "abstract_sha256": digest,
            "abstract_bytes": len(payload),
            "abstract_characters": len(text),
            "abstract_reviewed": False,
            "full_text_fetched": False,
            "evidence_evaluated": False,
        }],
    }


def _review_and_plan():
    plan = {
        "artifact_type": "EvidenceRadar_Editions_FulltextFetchPlan",
        "plan_binding_sha256": "d" * 64,
        "item_count": 1,
        "items": [],
    }
    review = {
        "artifact_type": "EvidenceRadar_Editions_AbstractReview",
        "policy_id": "abstract-review-fulltext-v1",
        "policy_sha256": "c" * 64,
        "abstract_receipt_binding_sha256": "b" * 64,
        "abstract_review_binding_sha256": "e" * 64,
        "counts": {"abstract_acquired": 1, "fulltext_now_count": 1, "fulltext_reserve_count": 0, "no_abstract_count": 0},
        "items": [],
        "fulltext_fetch_plan": plan,
    }
    return review, plan


def _fulltext_receipts(payload_dir):
    payload = b"<article><body><sec><title>Methods</title></sec></body></article>"
    digest = hashlib.sha256(payload).hexdigest()
    payload_dir.mkdir(parents=True, exist_ok=True)
    name = f"{digest}.xml"
    (payload_dir / name).write_bytes(payload)
    evidence = {
        "artifact_type": "EvidenceRadar_Editions_EvidenceReviewPlan",
        "evidence_review_plan_binding_sha256": "f" * 64,
        "item_count": 1,
        "items": [],
    }
    return {
        "artifact_type": "EvidenceRadar_Editions_FulltextAcquisitionReceipts",
        "plan_binding_sha256": "d" * 64,
        "receipt_binding_sha256": "1" * 64,
        "plan_item_count": 1,
        "receipt_count": 1,
        "counts": {"fulltext_acquired": 1, "route_not_found": 0, "access_denied": 0, "not_found": 0, "acquisition_inconclusive": 0, "skipped_no_fulltext_source": 0},
        "items": [{
            "record_key": "k1",
            "status": "FULLTEXT_ACQUIRED",
            "fulltext_sha256": digest,
            "fulltext_bytes": len(payload),
            "payload_object_name": name,
            "evidence_evaluated": False,
        }],
        "evidence_review_plan": evidence,
    }


class ReviewFulltextDeliveryTests(unittest.TestCase):
    def test_end_to_end_delivery_deletes_both_payload_vaults_and_publishes_safe_surfaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            site, work = root / "site", root / "work"
            abstract_payload, fulltext_payload = root / "abstract", root / "fulltext"
            site.mkdir()
            (site / "abstract-fetch-plan.json").write_text(json.dumps(_abstract_plan()), encoding="utf-8")
            (site / "editorial-shortlist.json").write_text(json.dumps({"items": []}), encoding="utf-8")
            (site / "index.html").write_text('<html><body><main class="shell">portal</main></body></html>', encoding="utf-8")
            (site / "index.json").write_text("{}", encoding="utf-8")
            (site / "links.json").write_text(json.dumps({"base_url": "https://example.test/"}), encoding="utf-8")

            abs_receipts = _abstract_receipts(abstract_payload)
            review, fulltext_plan = _review_and_plan()
            full_receipts = _fulltext_receipts(fulltext_payload)
            policy = {
                "artifact_type": "EvidenceRadar_Editions_AbstractReviewPolicy",
                "policy_id": "abstract-review-fulltext-v1",
                "fulltext_response_limit_bytes": 1024 * 1024,
                "crossref_open_license_hosts": ["creativecommons.org"],
            }

            with patch.object(delivery, "acquire_plan", return_value=abs_receipts), \
                 patch.object(delivery, "validate_payload_vault", return_value={"payload_object_count": 1, "payload_bytes": 50}), \
                 patch.object(delivery, "attach_acquisition_to_site"), \
                 patch.object(delivery, "load_abstract_review_policy", return_value=policy), \
                 patch.object(delivery, "build_abstract_review", return_value=(review, fulltext_plan)), \
                 patch.object(delivery, "acquire_fulltext_plan", return_value=full_receipts), \
                 patch.object(delivery, "validate_fulltext_payload_vault", return_value={"payload_object_count": 1, "payload_bytes": 66}):
                result = delivery.run_delivery(
                    site_dir=site,
                    work_dir=work,
                    abstract_payload_dir=abstract_payload,
                    fulltext_payload_dir=fulltext_payload,
                    catalog_root=root / "catalog",
                    maximum_abstract_items=300,
                    maximum_fulltext_items=120,
                )

            self.assertFalse(abstract_payload.exists())
            self.assertFalse(fulltext_payload.exists())
            self.assertTrue((site / "abstract-review.html").is_file())
            self.assertTrue((site / "fulltext-acquisition.html").is_file())
            self.assertTrue((site / "evidence-review-plan.json").is_file())
            self.assertTrue((work / delivery.PIPELINE_MANIFEST_FILENAME).is_file())
            self.assertEqual(result["abstract_disposition"]["disposition"], "DELETED_BEFORE_ARTIFACT_UPLOAD")
            self.assertEqual(result["fulltext_disposition"]["disposition"], "DELETED_BEFORE_ARTIFACT_UPLOAD")


if __name__ == "__main__":
    unittest.main()
