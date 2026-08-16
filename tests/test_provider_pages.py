import json
import tempfile
import unittest
from pathlib import Path

from evidenceradar_editions.pages_v14 import _publish_provider_catalogs


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


class ProviderPagesTests(unittest.TestCase):
    def test_provider_snapshot_gets_public_browse_and_machine_surfaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog = root / "catalog"
            providers = catalog / "providers"
            output = root / "site"
            providers.mkdir(parents=True)
            output.mkdir()
            (providers / "cambridge.json").write_text(
                json.dumps(provider_payload(), ensure_ascii=False),
                encoding="utf-8",
            )
            (output / "index.html").write_text(
                '<html><body><main class="shell"><h1>Journals</h1></main></body></html>',
                encoding="utf-8",
            )
            (output / "index.json").write_text("{}", encoding="utf-8")
            links = {"base_url": "https://example.test/"}

            index = _publish_provider_catalogs(
                output=output,
                catalog_root=catalog,
                links=links,
            )

            self.assertIsNotNone(index)
            assert index is not None
            self.assertEqual(index["provider_count"], 1)
            self.assertEqual(index["journal_count"], 2)
            self.assertTrue((output / "providers.json").is_file())
            self.assertTrue((output / "providers" / "cambridge.json").is_file())
            self.assertTrue((output / "providers" / "index.html").is_file())
            provider_page = output / "providers" / "cambridge" / "index.html"
            self.assertTrue(provider_page.is_file())
            html = provider_page.read_text(encoding="utf-8")
            self.assertIn("AI EDAM", html)
            self.assertIn("--provider cambridge --journal-slug ai-edam", html)
            self.assertIn("discovery snapshot", html)
            home = (output / "index.html").read_text(encoding="utf-8")
            self.assertIn('href="providers/"', home)
            root_index = json.loads((output / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(root_index["publisher_providers"]["journal_count"], 2)
            self.assertEqual(
                links["publisher_providers_url"],
                "https://example.test/providers/",
            )


if __name__ == "__main__":
    unittest.main()
