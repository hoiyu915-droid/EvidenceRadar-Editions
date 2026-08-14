import tempfile
import unittest
from pathlib import Path

from evidenceradar_editions.fulltext_acquisition import (
    acquire_fulltext_plan,
    audit_fulltext_xml,
    parse_crossref_open_tdm_links,
    validate_fulltext_payload_vault,
)


PMC_XML = b"""<?xml version="1.0"?>
<article>
 <front><article-meta>
  <article-id pub-id-type="pmcid">PMC1234567</article-id>
  <article-id pub-id-type="pmid">123456</article-id>
  <article-id pub-id-type="doi">10.1000/example</article-id>
 </article-meta></front>
 <body>
  <sec><title>Methods</title><p>Methods text.</p></sec>
  <sec><title>Results</title><p>Results text.</p></sec>
  <sec><title>Discussion</title><p>Discussion text.</p></sec>
  <sec><title>Data availability</title><p>Data text.</p></sec>
 </body>
 <back><ref-list><ref id="r1"/></ref-list></back>
</article>
"""


class FakeClient:
    def __init__(self):
        self.calls = []
    def get_bytes(self, url, *, params=None, limit=None):
        self.calls.append(("bytes", url, params))
        if "fullTextXML" in url:
            return PMC_XML
        if "publisher.example/full.xml" in url:
            return PMC_XML.replace(b"PMC1234567", b"PMC7654321").replace(b"10.1000/example", b"10.1000/other")
        raise AssertionError(url)
    def get_json(self, url, *, params=None, limit=None):
        self.calls.append(("json", url, params))
        return {
            "message": {
                "DOI": "10.1000/other",
                "license": [{"URL": "https://creativecommons.org/licenses/by/4.0/"}],
                "link": [{
                    "URL": "https://publisher.example/full.xml",
                    "content-type": "text/xml",
                    "content-version": "vor",
                    "intended-application": "text-mining",
                }],
            }
        }


def plan_item(index, *, doi="10.1000/example", pmcid="PMC1234567"):
    return {
        "ordinal": index,
        "record_key": f"k{index}",
        "canonical_id": f"doi:{doi}",
        "journal": "Example Journal",
        "journal_slug": "example-journal",
        "period_key": "2026-08",
        "revision": 1,
        "title_original": "Example full text",
        "identifiers": {"doi": doi, "pmid": "123456", "pmcid": pmcid},
        "pmcid_discovered": pmcid,
        "abstract_sha256": "a" * 64,
        "abstract_review_binding_sha256": "b" * 64,
        "source_order": ["EUROPE_PMC_FULLTEXT_XML"] if pmcid else ["CROSSREF_OPEN_TDM_LINK"],
        "status": "PLANNED",
        "full_text_fetch_requested": False,
        "full_text_fetched": False,
        "evidence_evaluated": False,
    }


class FulltextAcquisitionTests(unittest.TestCase):
    def test_europe_pmc_fulltext_is_identity_checked_hash_bound_and_structurally_audited(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = {
                "artifact_type": "EvidenceRadar_Editions_FulltextFetchPlan",
                "plan_binding_sha256": "c" * 64,
                "item_count": 1,
                "items": [plan_item(1)],
            }
            receipts = acquire_fulltext_plan(
                plan,
                payload_dir=Path(tmp),
                client=FakeClient(),
                maximum_items=2,
                generated_at="2026-08-15T00:00:00Z",
            )
            self.assertEqual(receipts["counts"]["fulltext_acquired"], 1)
            item = receipts["items"][0]
            self.assertTrue(item["full_text_fetched"])
            self.assertFalse(item["evidence_evaluated"])
            self.assertTrue(item["fulltext_structural_audit"]["has_methods_section"])
            self.assertTrue(item["fulltext_structural_audit"]["has_results_section"])
            self.assertEqual(receipts["evidence_review_plan"]["item_count"], 1)
            vault = validate_fulltext_payload_vault(receipts, Path(tmp))
            self.assertEqual(vault["payload_object_count"], 1)

    def test_crossref_requires_recognized_open_license_before_tdm_link(self):
        parsed = parse_crossref_open_tdm_links(
            {
                "message": {
                    "DOI": "10.1000/example",
                    "license": [{"URL": "https://publisher.example/license"}],
                    "link": [{
                        "URL": "https://publisher.example/full.xml",
                        "content-type": "text/xml",
                        "intended-application": "text-mining",
                    }],
                }
            },
            doi="10.1000/example",
            allowed_license_hosts={"creativecommons.org"},
        )
        self.assertFalse(parsed["open_license"])
        self.assertEqual(parsed["links"], [])

    def test_structural_xml_audit_does_not_claim_evidence_quality(self):
        audit = audit_fulltext_xml(PMC_XML)
        self.assertEqual(audit["format"], "JATS_XML")
        self.assertTrue(audit["has_methods_section"])
        self.assertTrue(audit["has_results_section"])
        self.assertNotIn("quality", audit)
        self.assertNotIn("risk_of_bias", audit)


if __name__ == "__main__":
    unittest.main()
