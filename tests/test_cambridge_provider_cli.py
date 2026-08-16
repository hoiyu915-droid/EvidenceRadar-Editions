import unittest

from evidenceradar_editions.cli_v6 import (
    _provider_spec,
    _resolve_provider_journal,
    build_parser,
)


JOURNAL = {
    "provider": "cambridge",
    "publisher": "Cambridge University Press",
    "name": "AI EDAM",
    "slug": "ai-edam",
    "issn": "1469-1760",
    "sources": ["cambridge_core"],
    "url": "https://www.cambridge.org/core/journals/ai-edam",
}


class FakeProvider:
    def __init__(self):
        self.resolve_calls = []
        self.list_calls = 0

    def resolve_journal(self, slug):
        self.resolve_calls.append(slug)
        return dict(JOURNAL)

    def list_journals(self):
        self.list_calls += 1
        return [dict(JOURNAL)]


class CambridgeProviderCliTests(unittest.TestCase):
    def _args(self):
        return build_parser().parse_args(
            [
                "run",
                "--provider",
                "cambridge",
                "--journal-slug",
                "ai-edam",
                "--start",
                "2026-08-01",
                "--end",
                "2026-08-16",
                "--output-dir",
                "out",
            ]
        )

    def test_slug_selection_resolves_directly_without_catalog_scan(self):
        provider = FakeProvider()
        journal = _resolve_provider_journal(self._args(), provider)
        self.assertEqual(journal["slug"], "ai-edam")
        self.assertEqual(provider.resolve_calls, ["ai-edam"])
        self.assertEqual(provider.list_calls, 0)

    def test_provider_spec_uses_only_cambridge_source_by_default(self):
        spec = _provider_spec(self._args(), dict(JOURNAL))
        self.assertEqual(spec.journal, "AI EDAM")
        self.assertEqual(spec.issn, "1469-1760")
        self.assertEqual(spec.sources, ("cambridge_core",))


if __name__ == "__main__":
    unittest.main()
