import unittest
from datetime import date

from evidenceradar_editions.adapters import CambridgeCoreAdapter
from evidenceradar_editions.models import EditionSpec


CATALOG_PAGE_1 = b"""
<html><body>
<h2>3 results in Open Access</h2>
<div>Page 1 of 2</div>
<a href="/core/journals/acta-neuropsychiatrica">Acta Neuropsychiatrica</a>
<a href="/core/journals/ai-edam">AI EDAM</a>
<a href="/core/journals/shared-navigation-journal">Navigation journal link</a>
</body></html>
"""
CATALOG_PAGE_2 = b"""
<html><body>
<h2>3 results in Open Access</h2>
<div>Page 2 of 2</div>
<a href="/core/journals/animal-welfare">Animal Welfare</a>
<a href="/core/journals/shared-navigation-journal">Navigation journal link</a>
</body></html>
"""
AI_EDAM_HOME = b"""
<html><head><title>AI EDAM | Cambridge Core</title></head><body>
<div>Access: Full</div><div>Open access</div>
<div>ISSN: 0890-0604 (Print), 1469-1760 (Online)</div>
</body></html>
"""
HYBRID_HOME = b"""
<html><head><title>Nutrition Research Reviews | Cambridge Core</title></head><body>
<div>Get access</div><div>Contains open access</div>
<div>ISSN: 0954-4224 (Print), 1475-2700 (Online)</div>
</body></html>
"""
ARTICLE_PAGE = b"""
<html><body>
<div>Page 1 of 1</div>
<a href="/core/journals/ai-edam/article/new-work/abc">New work</a>
<div>Published online by Cambridge University Press: 20 August 2026</div>
<a href="/core/journals/ai-edam/article/in-window/def">In-window work</a>
<div>Published online by Cambridge University Press: 15 August 2026</div>
<a href="/core/journals/ai-edam/article/old-work/ghi">Old work</a>
<div>Published online by Cambridge University Press: 01 July 2026</div>
</body></html>
"""


class FakeClient:
    def __init__(self):
        self.calls = []

    def get_bytes(self, url, *, params=None, limit=None):
        self.calls.append((url, params))
        if "/publications/open-access/listing" in url:
            return CATALOG_PAGE_2 if (params or {}).get("pageNum") == 2 else CATALOG_PAGE_1
        if url.endswith("/core/journals/ai-edam"):
            return AI_EDAM_HOME
        if url.endswith("/core/journals/nutrition-research-reviews"):
            return HYBRID_HOME
        if url.endswith("/core/journals/ai-edam/open-access"):
            return ARTICLE_PAGE
        raise AssertionError(f"unexpected URL: {url}")


class CambridgeCoreTests(unittest.TestCase):
    def test_catalog_reconciles_declared_results_and_cross_page_navigation(self):
        client = FakeClient()
        journals = CambridgeCoreAdapter(client).list_journals()
        self.assertEqual(
            [item["slug"] for item in journals],
            ["acta-neuropsychiatrica", "ai-edam", "animal-welfare"],
        )
        self.assertNotIn(
            "shared-navigation-journal",
            {item["slug"] for item in journals},
        )
        self.assertEqual(len(client.calls), 2)
        self.assertTrue(
            all("/publications/open-access/listing" in call[0] for call in client.calls)
        )

    def test_catalog_fails_closed_when_declared_count_does_not_reconcile(self):
        class BadCountClient(FakeClient):
            def get_bytes(self, url, *, params=None, limit=None):
                payload = super().get_bytes(url, params=params, limit=limit)
                return payload.replace(b"3 results in Open Access", b"4 results in Open Access")

        with self.assertRaisesRegex(ValueError, "reconciliation mismatch"):
            CambridgeCoreAdapter(BadCountClient()).list_journals()

    def test_resolve_selected_journal_is_direct_and_rejects_hybrid(self):
        client = FakeClient()
        adapter = CambridgeCoreAdapter(client)
        journal = adapter.resolve_journal("ai-edam")
        self.assertEqual(journal["name"], "AI EDAM")
        self.assertEqual(journal["issn"], "1469-1760")
        self.assertEqual(journal["sources"], ["cambridge_core"])
        with self.assertRaises(KeyError):
            adapter.resolve_journal("nutrition-research-reviews")

    def test_fetch_traverses_only_selected_journal(self):
        client = FakeClient()
        spec = EditionSpec(
            "AI EDAM",
            date(2026, 8, 1),
            date(2026, 8, 16),
            "ai-edam",
            issn="1469-1760",
            sources=("cambridge_core",),
            period_kind="month",
        )
        result = CambridgeCoreAdapter(client).fetch(spec)
        self.assertEqual(result.check.status, "SUCCESS")
        self.assertFalse(result.check.truncated)
        self.assertEqual([article.title for article in result.articles], ["In-window work"])
        self.assertEqual(result.articles[0].publication_date, date(2026, 8, 15))
        self.assertEqual(result.articles[0].publication_date_precision, "DAY")
        self.assertEqual(result.articles[0].source_records[0].source, "cambridge_core")
        article_calls = [url for url, _ in client.calls if url.endswith("/open-access")]
        self.assertEqual(
            article_calls,
            ["https://www.cambridge.org/core/journals/ai-edam/open-access"],
        )
        self.assertFalse(any("acta-neuropsychiatrica/open-access" in url for url, _ in client.calls))


if __name__ == "__main__":
    unittest.main()
