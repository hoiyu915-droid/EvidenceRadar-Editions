import json
import tempfile
import unittest
from pathlib import Path

from evidenceradar_editions.abstract_acquisition_delivery import _inject_portal_banner
from evidenceradar_editions.complete_edition_delivery import _inject_final_banner
from evidenceradar_editions.pages_v16 import (
    _build_portal_registry,
    _portal_counts,
    _published_provider_journals,
    _render_clean_homepage,
)
from evidenceradar_editions.review_fulltext_delivery import inject_banner


class PortalV16Tests(unittest.TestCase):
    def _core_registry(self):
        return {
            "artifact_type": "EvidenceRadar_Editions_JournalRegistry",
            "category_labels": {"llm_research": "AI／LLM"},
            "journals": [
                {
                    "name": "Core AI Journal",
                    "slug": "core-ai-journal",
                    "publisher": "Core Publisher",
                    "status": "active",
                    "oa": "fully_oa",
                    "categories": ["llm_research"],
                }
            ],
        }

    def _provider_catalog(self):
        return {
            "provider": "cambridge",
            "publisher": "Cambridge University Press",
            "journals": [
                {
                    "provider": "cambridge",
                    "publisher": "Cambridge University Press",
                    "name": "AI EDAM",
                    "slug": "ai-edam",
                    "oa": "fully_oa",
                    "status": "active",
                    "sources": ["cambridge_core"],
                },
                {
                    "provider": "cambridge",
                    "publisher": "Cambridge University Press",
                    "name": "Discovery Only",
                    "slug": "discovery-only",
                    "oa": "fully_oa",
                    "status": "active",
                    "sources": ["cambridge_core"],
                },
            ],
        }

    def _catalog(self):
        return {
            "latest_editions": [
                {
                    "journal": "Core AI Journal",
                    "journal_slug": "core-ai-journal",
                    "period_kind": "month",
                    "period_key": "2026-08",
                    "period_end": "2026-08-16",
                    "period_status": "MTD",
                    "article_count": 3,
                    "revision_url": "journals/core-ai-journal/2026-08/r01/",
                },
                {
                    "journal": "AI EDAM",
                    "journal_slug": "ai-edam",
                    "period_kind": "month",
                    "period_key": "2026-08",
                    "period_end": "2026-08-16",
                    "period_status": "MTD",
                    "article_count": 2,
                    "revision_url": "journals/ai-edam/2026-08/r01/",
                },
            ]
        }

    def test_provider_discovery_only_journals_do_not_enter_reader_portal(self):
        core = self._core_registry()
        catalog = self._catalog()
        provider = _published_provider_journals(
            [self._provider_catalog()],
            catalog,
            core_slugs={"core-ai-journal"},
        )
        self.assertEqual([item["slug"] for item in provider], ["ai-edam"])
        self.assertEqual(provider[0]["status"], "provider")
        self.assertEqual(provider[0]["origin"], "provider:cambridge")

        projection = _build_portal_registry(core, provider)
        self.assertEqual(projection["core_registry_count"], 1)
        self.assertEqual(projection["published_provider_journal_count"], 1)
        self.assertEqual(projection["journal_count"], 2)
        self.assertEqual(
            _portal_counts(projection, catalog),
            {
                "journal_count": 2,
                "published_journal_count": 2,
                "latest_month_journal_count": 2,
            },
        )

    def test_reader_home_is_clean_and_immune_to_legacy_pipeline_banners(self):
        core = self._core_registry()
        catalog = self._catalog()
        provider = _published_provider_journals(
            [self._provider_catalog()],
            catalog,
            core_slugs={"core-ai-journal"},
        )
        projection = _build_portal_registry(core, provider)

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            (output / "index.json").write_text(
                json.dumps(catalog, ensure_ascii=False), encoding="utf-8"
            )
            (output / "search-index.json").write_text(
                json.dumps({"article_count": 5, "articles": []}, ensure_ascii=False),
                encoding="utf-8",
            )
            _render_clean_homepage(output=output, projection=projection)

            home = output / "index.html"
            text = home.read_text(encoding="utf-8")
            self.assertIn('data-reader-portal', text)
            self.assertNotIn('<main class="shell">', text)
            self.assertIn("期刊入口", text)
            self.assertIn("AI EDAM", text)
            self.assertIn("Cambridge University Press", text)
            self.assertIn("provider", text)
            self.assertNotIn("Discovery Only", text)

            _inject_portal_banner(
                home,
                {"counts": {"abstract_acquired": 205}, "plan_item_count": 300},
            )
            inject_banner(
                home,
                {"counts": {"abstract_acquired": 205}},
                {"counts": {"fulltext_acquired": 69}, "plan_item_count": 120},
            )
            _inject_final_banner(
                home,
                {"counts": {"evidence_evaluated": 62}},
                {"counts": {"featured": 36}},
            )

            text = home.read_text(encoding="utf-8")
            self.assertNotIn("Abstract acquisition：", text)
            self.assertNotIn("Review → full text：", text)
            self.assertNotIn("Default end-to-end evidence lane：", text)
            self.assertNotIn("Publisher providers：", text)
            self.assertNotIn("已出版 Cambridge University Press Editions", text)


if __name__ == "__main__":
    unittest.main()
