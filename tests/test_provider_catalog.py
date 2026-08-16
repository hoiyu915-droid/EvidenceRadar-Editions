import json
import tempfile
import unittest
from pathlib import Path

from evidenceradar_editions.provider_catalog import (
    ProviderCatalogError,
    load_provider_catalogs,
    validate_provider_catalog,
)


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


class ProviderCatalogTests(unittest.TestCase):
    def test_valid_catalog_is_normalized_and_sorted(self):
        value = provider_payload()
        value["journals"].reverse()
        catalog = validate_provider_catalog(value)
        self.assertEqual(catalog["provider"], "cambridge")
        self.assertEqual(catalog["journal_count"], 2)
        self.assertEqual(
            [item["slug"] for item in catalog["journals"]],
            ["ai-edam", "animal-welfare"],
        )

    def test_duplicate_slug_fails_closed(self):
        value = provider_payload()
        value["journals"][1]["slug"] = "ai-edam"
        with self.assertRaises(ProviderCatalogError):
            validate_provider_catalog(value)

    def test_declared_count_must_match_records(self):
        value = provider_payload()
        value["journal_count"] = 200
        with self.assertRaises(ProviderCatalogError):
            validate_provider_catalog(value)

    def test_catalog_directory_is_independent_from_local_journal_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            providers = root / "providers"
            providers.mkdir()
            (providers / "cambridge.json").write_text(
                json.dumps(provider_payload(), ensure_ascii=False),
                encoding="utf-8",
            )
            catalogs = load_provider_catalogs(root)
            self.assertEqual(len(catalogs), 1)
            self.assertEqual(catalogs[0]["journal_count"], 2)
            self.assertFalse((root / "journals.json").exists())


if __name__ == "__main__":
    unittest.main()
