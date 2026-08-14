import json
import tempfile
import unittest
from pathlib import Path

from evidenceradar_editions.journal_catalog_v2 import (
    list_journals,
    load_journal_registry,
)
from evidenceradar_editions.processing_policy import ProcessingPolicyError


class JournalPolicyCatalogTests(unittest.TestCase):
    def test_registry_listing_exposes_resolved_processing_policy(self):
        triage = list_journals(
            catalog_root=Path("catalog"),
            processing_mode="TRIAGE",
        )
        slugs = {item["slug"] for item in triage}
        self.assertIn("scientific-reports", slugs)
        scientific_reports = next(
            item for item in triage if item["slug"] == "scientific-reports"
        )
        self.assertEqual(
            scientific_reports["processing_policy"]["translation_mode"],
            "DEFERRED",
        )

    def test_policy_override_must_reference_registered_slug(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "journals.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "EvidenceRadar_Editions_JournalRegistry",
                        "journal_count": 1,
                        "journals": [
                            {
                                "name": "Example Journal",
                                "slug": "example-journal",
                                "status": "active",
                                "categories": [],
                                "sources": ["crossref"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (root / "processing-policies.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "EvidenceRadar_Editions_ProcessingPolicies",
                        "defaults": {"mode": "FULL"},
                        "journals": {
                            "missing-journal": {"mode": "SUSPENDED"}
                        },
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ProcessingPolicyError):
                load_journal_registry(root)


if __name__ == "__main__":
    unittest.main()
