import json
import tempfile
import unittest
from pathlib import Path

from evidenceradar_editions.pages_v15 import _publish_provider_edition_surface


def provider_payload():
    return {
        "artifact_type": "EvidenceRadar_Editions_ProviderCatalog",
        "schema_version": "1.0",
        "provider": "cambridge",
        "publisher": "Cambridge University Press",
        "scope": "fully_open_access_journals",
        "source_url": "https://www.cambridge.org/core/publications/open-access/listing",
        "observed_at": "2026-08-16T03:45:00Z",
        "journal_count": 2,
        "journals": [
            {
                "provider": "cambridge",
                "publisher": "Cambridge University Press",
                "name": "AI EDAM",
                "slug": "ai-edam",
                "oa": "fully_oa",
                "status": "active",
                "sources": ["cambridge_core"],
                "url": "https://www.cambridge.org/core/journals/ai-edam",
            },
            {
                "provider": "cambridge",
                "publisher": "Cambridge University Press",
                "name": "Animal Welfare",
                "slug": "animal-welfare",
                "oa": "fully_oa",
                "status": "active",
                "sources": ["cambridge_core"],
                "url": "https://www.cambridge.org/core/journals/animal-welfare",
            },
        ],
    }


class ProviderPublishedPagesTests(unittest.TestCase):
    def test_homepage_exposes_only_provider_journals_with_published_editions(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            (output / "index.html").write_text(
                '<html><body><main class="shell"><h1>Journals</h1></main></body></html>',
                encoding="utf-8",
            )
            root_index = {
                "latest_editions": [
                    {
                        "journal": "AI EDAM",
                        "journal_slug": "ai-edam",
                        "period_key": "2026-08",
                        "period_label_zh_tw": "2026 年 8 月（MTD 至 8 月 16 日）",
                        "period_status": "MTD",
                        "period_url": "journals/ai-edam/2026-08/",
                        "revision_url": "journals/ai-edam/2026-08/r01/",
                        "article_count": 0,
                        "created_at": "2026-08-16T04:50:00Z",
                    },
                    {
                        "journal": "Unrelated Journal",
                        "journal_slug": "unrelated-journal",
                        "period_key": "2026-08",
                        "period_url": "journals/unrelated-journal/2026-08/",
                    },
                ],
                "publisher_providers": {
                    "artifact_type": "EvidenceRadar_Editions_ProviderIndex",
                    "schema_version": "1.0",
                    "provider_count": 1,
                    "journal_count": 2,
                    "providers": [],
                },
            }
            (output / "index.json").write_text(
                json.dumps(root_index, ensure_ascii=False),
                encoding="utf-8",
            )
            links = {"base_url": "https://example.test/", "publisher_providers": {}}

            published = _publish_provider_edition_surface(
                output=output,
                catalogs=[provider_payload()],
                links=links,
            )

            self.assertEqual(len(published), 1)
            self.assertEqual(published[0]["journal_slug"], "ai-edam")
            self.assertEqual(published[0]["article_count"], 0)

            home = (output / "index.html").read_text(encoding="utf-8")
            self.assertIn("data-provider-editions", home)
            self.assertIn("Cambridge University Press Editions（1）", home)
            self.assertIn('href="journals/ai-edam/2026-08/"', home)
            self.assertIn("AI EDAM", home)
            self.assertNotIn("Animal Welfare", home)

            root = json.loads((output / "index.json").read_text(encoding="utf-8"))
            provider_index = root["publisher_providers"]
            self.assertEqual(provider_index["published_edition_count"], 1)
            self.assertEqual(provider_index["published_editions"][0]["journal_slug"], "ai-edam")

            public_provider_index = json.loads(
                (output / "providers.json").read_text(encoding="utf-8")
            )
            self.assertEqual(public_provider_index, provider_index)
            self.assertEqual(links["published_provider_edition_count"], 1)
            self.assertEqual(links["publisher_providers"], provider_index)


if __name__ == "__main__":
    unittest.main()
