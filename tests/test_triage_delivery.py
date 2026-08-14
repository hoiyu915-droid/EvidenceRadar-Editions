import json
import tempfile
import unittest
from pathlib import Path

from evidenceradar_editions.triage_delivery import build_triage_delivery


class TriageDeliveryTests(unittest.TestCase):
    def test_empty_store_builds_complete_triage_surface(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            editions = root / "editions"
            site = root / "site"
            editions.mkdir()
            links = build_triage_delivery(
                output_dir=site,
                repository="hoiyu915-droid/EvidenceRadar-Editions",
                editions_root=editions,
                catalog_root=Path("catalog"),
            )
            for relative in (
                "index.html",
                "index.json",
                "search-index.json",
                "metadata-triage.json",
                "metadata-triage-policy.json",
                "metadata-triage/index.html",
                "links.json",
            ):
                self.assertTrue((site / relative).is_file(), relative)
            triage = json.loads(
                (site / "metadata-triage.json").read_text(encoding="utf-8")
            )
            search = json.loads(
                (site / "search-index.json").read_text(encoding="utf-8")
            )
            public_links = json.loads(
                (site / "links.json").read_text(encoding="utf-8")
            )
            self.assertEqual(triage["canonical_article_count"], 0)
            self.assertEqual(search["projected_article_count"], 0)
            self.assertEqual(search["metadata_triage_policy_id"], "metadata-title-triage-v1")
            self.assertEqual(
                public_links["search_projection"]["semantics"],
                "latest_revision_per_journal_period_metadata_triage_projected",
            )
            self.assertEqual(
                links["metadata_triage_url"],
                "https://hoiyu915-droid.github.io/EvidenceRadar-Editions/metadata-triage/",
            )
            home = (site / "index.html").read_text(encoding="utf-8")
            self.assertIn("Metadata triage 已套用", home)
            self.assertIn("開啟全站 triage dashboard", home)


if __name__ == "__main__":
    unittest.main()
