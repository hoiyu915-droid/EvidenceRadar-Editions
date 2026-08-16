import json
import tempfile
import unittest
from pathlib import Path

from evidenceradar_editions.bundle import write_bundle
from evidenceradar_editions.journal_catalog import (
    get_journal,
    list_journals,
    load_journal_registry,
    spec_defaults,
)
from evidenceradar_editions.pages import build_pages_site
from evidenceradar_editions.store_v3 import store_bundle
from evidenceradar_editions.translation import apply_translation_response
from test_delivery import translation_response
from test_store_v3 import month_run


class JournalRegistryTests(unittest.TestCase):
    def test_repository_registry_is_self_contained(self):
        registry = load_journal_registry(Path("catalog"))
        self.assertEqual(registry["journal_count"], 58)
        self.assertEqual(
            registry["upstream"]["commit"],
            "6da659df845e4b76072dae016120ca76ed9c27c4",
        )
        jama = get_journal("jama-network-open", catalog_root=Path("catalog"))
        defaults = spec_defaults(jama)
        self.assertEqual(defaults["journal"], "JAMA Network Open")
        self.assertEqual(defaults["issn"], "2574-3805")
        self.assertIn("crossref", defaults["sources"])
        self.assertNotIn("radar_rss", defaults["sources"])

    def test_registry_filters_without_radar(self):
        ai = list_journals(
            catalog_root=Path("catalog"),
            category="llm_research",
            enabled_only=True,
        )
        self.assertTrue(any(item["slug"] == "artificial-intelligence" for item in ai))
        planned = list_journals(
            catalog_root=Path("catalog"),
            status="planned",
        )
        self.assertTrue(any(item["slug"] == "tacl" for item in planned))

    def test_pages_home_uses_registry_filters_and_placeholders(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run = month_run()
            enriched = apply_translation_response(run, translation_response(run))
            bundle = base / "bundle"
            editions = base / "editions"
            catalog = base / "catalog"
            site = base / "site"
            catalog.mkdir()
            write_bundle(enriched, bundle)
            store_bundle(bundle, editions)
            (catalog / "journals.json").write_text(
                json.dumps(
                    {
                        "schema_version": "2.0",
                        "artifact_type": "EvidenceRadar_Editions_JournalRegistry",
                        "category_labels": {"clinical_medicine": "臨床醫學", "llm_research": "AI／LLM"},
                        "journal_count": 2,
                        "journals": [
                            {
                                "name": "JAMA Network Open",
                                "slug": "jama-network-open",
                                "issn": "2574-3805",
                                "publisher": "JAMA Network",
                                "categories": ["clinical_medicine"],
                                "oa": "fully_oa",
                                "status": "active",
                                "sources": ["pubmed", "europe_pmc", "crossref"],
                            },
                            {
                                "name": "Nature Machine Intelligence",
                                "slug": "nature-machine-intelligence",
                                "issn": "2522-5839",
                                "publisher": "Nature Portfolio",
                                "categories": ["llm_research"],
                                "oa": "mixed",
                                "status": "active",
                                "sources": ["crossref"],
                            },
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            links = build_pages_site(
                editions_root=editions,
                catalog_root=catalog,
                output_dir=site,
                repository="hoiyu915-droid/EvidenceRadar-Editions",
            )
            home = (site / "index.html").read_text(encoding="utf-8")
            self.assertIn('id="journal-category"', home)
            self.assertIn('id="journal-publisher"', home)
            self.assertIn('id="journal-month"', home)
            self.assertIn('data-letter="N"', home)
            self.assertIn("Core Registry JSON", home)
            self.assertIn("期刊入口", home)
            self.assertTrue((site / "journals.json").is_file())
            self.assertTrue((site / "portal-journals.json").is_file())
            self.assertTrue(
                (site / "journals/nature-machine-intelligence/index.html").is_file()
            )
            self.assertEqual(links["registered_journal_count"], 2)
            self.assertEqual(links["published_journal_count"], 1)


if __name__ == "__main__":
    unittest.main()
