import hashlib
import tempfile
import unittest
from pathlib import Path

from evidenceradar_editions.abstract_review import (
    build_abstract_review,
    builtin_abstract_review_policy,
)


def _receipt(index, *, journal="Journal A", slug="journal-a", acquired=True, pmcid=None):
    text = (
        "METHODS: We randomized 240 participants across four sites. "
        "RESULTS: The intervention reduced the primary outcome, mean difference 3.2 "
        "(95% CI 1.1 to 5.3, p=0.003). Trial registration NCT01234567. "
        "LIMITATIONS: Follow-up was 12 months."
    )
    payload = text.encode()
    digest = hashlib.sha256(payload).hexdigest()
    return {
        "ordinal": index,
        "record_key": f"{slug}|2026-08|1|doi:10.1000/{slug}.{index}",
        "canonical_id": f"doi:10.1000/{slug}.{index}",
        "journal": journal,
        "journal_slug": slug,
        "period_key": "2026-08",
        "revision": 1,
        "title_original": f"Randomized trial {index}",
        "identifiers": {"doi": f"10.1000/{slug}.{index}", "pmid": str(1000 + index), "pmcid": pmcid},
        "status": "ABSTRACT_ACQUIRED" if acquired else "ABSTRACT_NOT_PRESENT",
        "acquired_source": "PUBMED_PMID" if acquired else None,
        "source_record_id": pmcid or str(1000 + index) if acquired else None,
        "abstract_sha256": digest if acquired else None,
        "abstract_bytes": len(payload) if acquired else 0,
        "abstract_characters": len(text) if acquired else 0,
        "_payload": payload,
    }


def _shortlist_item(receipt, *, path="RANDOMIZED_TRIAL", prefetch_route="FETCH_CANDIDATE", percentile=80, mode="FULL"):
    return {
        "record_key": receipt["record_key"],
        "journal": receipt["journal"],
        "journal_slug": receipt["journal_slug"],
        "primary_path": path,
        "prefetch_route": prefetch_route,
        "prefetch_score": 94,
        "processing_mode": mode,
        "topic_signature": f"topic-{receipt['ordinal']}",
        "journal_impact_prior": {"registry_category_percentile": percentile},
    }


class AbstractReviewTests(unittest.TestCase):
    def test_review_reads_hash_bound_payloads_and_builds_bounded_fulltext_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload_dir = Path(tmp)
            receipts = []
            shortlist = []
            for i in range(1, 7):
                slug = "journal-a" if i <= 3 else "journal-b"
                r = _receipt(i, journal=slug.title(), slug=slug, pmcid=f"PMC{i:07d}" if i % 2 else None)
                receipts.append(r)
                (payload_dir / f"{r['abstract_sha256']}.txt").write_bytes(r.pop("_payload"))
                shortlist.append(_shortlist_item(r, percentile=90 if slug == "journal-a" else 55))
            missing = _receipt(7, journal="Journal C", slug="journal-c", acquired=False)
            missing.pop("_payload")
            receipts.append(missing)
            receipts_artifact = {
                "artifact_type": "EvidenceRadar_Editions_AbstractAcquisitionReceipts",
                "receipt_binding_sha256": "a" * 64,
                "plan_item_count": 7,
                "items": receipts,
            }
            policy = builtin_abstract_review_policy()
            policy["fulltext_fetch_target"] = 4
            policy["journal_fetch_caps"] = {"FULL": 2, "TRIAGE": 3, "INDEX_ONLY": 1, "SUSPENDED": 0}
            review, plan = build_abstract_review(
                receipts_artifact,
                {"items": shortlist},
                payload_dir=payload_dir,
                policy=policy,
                generated_at="2026-08-15T00:00:00Z",
            )
            self.assertEqual(review["counts"]["abstract_acquired"], 6)
            self.assertEqual(review["counts"]["no_abstract_count"], 1)
            self.assertEqual(review["counts"]["fulltext_now_count"], 4)
            self.assertEqual(plan["item_count"], 4)
            self.assertTrue(all(x["abstract_reviewed"] for x in review["items"] if x["fulltext_route"] != "NO_ABSTRACT"))
            self.assertTrue(all(x["evidence_evaluated"] is False for x in review["items"]))
            self.assertTrue(any("RESULTS_SECTION" in x.get("abstract_signals", []) for x in review["items"]))
            self.assertTrue(any("EUROPE_PMC_FULLTEXT_XML" in x["source_order"] for x in plan["items"]))
            self.assertTrue(all(x["full_text_fetched"] is False for x in plan["items"]))

    def test_tampered_abstract_payload_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload_dir = Path(tmp)
            r = _receipt(1)
            original = r.pop("_payload")
            (payload_dir / f"{r['abstract_sha256']}.txt").write_bytes(original + b"tamper")
            artifact = {
                "artifact_type": "EvidenceRadar_Editions_AbstractAcquisitionReceipts",
                "receipt_binding_sha256": "a" * 64,
                "plan_item_count": 1,
                "items": [r],
            }
            with self.assertRaises(ValueError):
                build_abstract_review(
                    artifact,
                    {"items": [_shortlist_item(r)]},
                    payload_dir=payload_dir,
                    policy=builtin_abstract_review_policy(),
                )


if __name__ == "__main__":
    unittest.main()
