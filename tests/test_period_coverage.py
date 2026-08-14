import json
import tempfile
import unittest
from pathlib import Path

from evidenceradar_editions.bundle import write_bundle
from evidenceradar_editions.pages import build_pages_site
from evidenceradar_editions.store_v3 import store_bundle
from evidenceradar_editions.translation import apply_translation_response
from test_delivery import translation_response
from test_store_v3 import month_run


class PeriodCoverageTests(unittest.TestCase):
    def test_pages_publishes_latest_period_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            bundle = base / "bundle"
            editions = base / "editions"
            catalog = base / "catalog"
            site = base / "site"
            (catalog / "coverage").mkdir(parents=True)

            run = month_run()
            enriched = apply_translation_response(run, translation_response(run))
            write_bundle(enriched, bundle)
            store_bundle(bundle, editions)
            (catalog / "journals.json").write_text(
                json.dumps(
                    {
                        "schema_version": "2.0",
                        "artifact_type": "EvidenceRadar_Editions_JournalRegistry",
                        "journal_count": 1,
                        "journals": [
                            {
                                "name": "JAMA Network Open",
                                "slug": "jama-network-open",
                                "issn": "2574-3805",
                                "publisher": "JAMA Network",
                                "categories": ["clinical_medicine"],
                                "oa": "fully_oa",
                                "status": "active",
                                "sources": ["pubmed"],
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            coverage = {
                "schema_version": "1.0",
                "artifact_type": "EvidenceRadar_Editions_PeriodCoverage",
                "period_key": "2026-08",
                "coverage_through": "2026-08-14",
                "registry_count": 1,
                "processed_journal_count": 1,
                "published_journal_count": 1,
                "no_edition_count": 0,
                "status_counts": {"PUBLISHED": 1},
                "journals": [],
            }
            (catalog / "coverage" / "2026-08.json").write_text(
                json.dumps(coverage, ensure_ascii=False), encoding="utf-8"
            )

            links = build_pages_site(
                editions_root=editions,
                catalog_root=catalog,
                output_dir=site,
                repository="hoiyu915-droid/EvidenceRadar-Editions",
            )
            self.assertTrue((site / "coverage/2026-08.json").is_file())
            self.assertTrue(links["period_coverage_url"].endswith("coverage/2026-08.json"))
            self.assertEqual(links["processed_journal_count"], 1)
            index = json.loads((site / "index.json").read_text())
            self.assertEqual(index["period_coverage_summary"]["processed_journal_count"], 1)


if __name__ == "__main__":
    unittest.main()
