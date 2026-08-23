from __future__ import annotations

import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from evidenceradar_editions.bundle import write_bundle
from evidenceradar_editions.pages import build_pages_site
from evidenceradar_editions.store_v3 import store_bundle
from evidenceradar_editions.translation import apply_translation_response
from test_delivery import translation_response
from test_store_v3 import month_run


ROOT = Path(__file__).resolve().parents[1]
COVERAGE_ROOT = ROOT / "catalog" / "coverage"


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

    def test_committed_coverage_aggregates_match_journal_rows(self):
        coverage_files = sorted(COVERAGE_ROOT.glob("*.json"))
        self.assertTrue(coverage_files, "expected at least one period coverage file")
        registry = json.loads(
            (ROOT / "catalog" / "journals.json").read_text(encoding="utf-8")
        )
        registry_slugs = {row["slug"] for row in registry["journals"]}

        latest_coverage_path = coverage_files[-1]
        for path in coverage_files:
            with self.subTest(path=path.name):
                payload = json.loads(path.read_text(encoding="utf-8"))
                journals = payload["journals"]
                observed = Counter(row["coverage_status"] for row in journals)
                declared = {
                    str(status): int(count)
                    for status, count in payload["status_counts"].items()
                }

                self.assertEqual(payload["registry_count"], len(journals))
                self.assertEqual(payload["processed_journal_count"], len(journals))
                self.assertEqual(sum(declared.values()), len(journals))

                for status, count in observed.items():
                    self.assertIn(status, declared)
                    self.assertEqual(declared[status], count)
                for status, count in declared.items():
                    self.assertEqual(count, observed.get(status, 0))

                published = observed.get("PUBLISHED", 0)
                self.assertEqual(payload["published_journal_count"], published)
                self.assertEqual(payload["no_edition_count"], len(journals) - published)

                slugs = [row["slug"] for row in journals]
                self.assertEqual(len(slugs), len(set(slugs)))
                if path == latest_coverage_path:
                    self.assertEqual(set(slugs), registry_slugs)
                for row in journals:
                    self.assertIsInstance(row["article_count"], int)
                    self.assertGreaterEqual(row["article_count"], 0)
                    if row["coverage_status"] != "PUBLISHED":
                        self.assertEqual(row["article_count"], 0)


if __name__ == "__main__":
    unittest.main()
