import unittest
from datetime import date

from evidenceradar_editions.adapters.crossref import CrossrefAdapter
from evidenceradar_editions.adapters.rsc_chemical_science import (
    RscChemicalScienceAdapter,
    SURROGATE_SOURCE,
)
from evidenceradar_editions.models import EditionSpec


class FakeClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get_json(self, url, *, params=None):
        self.calls.append((url, params))
        return self.payload


def raw_item(
    title="A real Chemical Science article",
    *,
    doi="10.1039/D6SC05688A",
    created=(2026, 8, 11),
    publisher="Royal Society of Chemistry (RSC)",
):
    return {
        "DOI": doi,
        "title": [title],
        "container-title": ["Chemical Science"],
        "created": {"date-parts": [list(created)]},
        "ISSN": ["2041-6520", "2041-6539"],
        "author": [{"given": "Ada", "family": "Lovelace"}],
        "URL": f"https://doi.org/{doi}",
        "type": "journal-article",
        "publisher": publisher,
        "prefix": "10.1039",
    }


class RscChemicalScienceTests(unittest.TestCase):
    def setUp(self):
        self.spec = EditionSpec(
            "Chemical Science",
            date(2026, 8, 1),
            date(2026, 8, 14),
            "chemical-science",
            issn="2041-6539",
            sources=("rsc_chemical_science",),
            period_kind="month",
        )

    def test_generic_crossref_does_not_treat_created_as_publication_date(self):
        self.assertIsNone(CrossrefAdapter._article(raw_item()))

    def test_created_day_is_used_only_by_narrow_rsc_adapter(self):
        article = RscChemicalScienceAdapter._article(raw_item())
        self.assertIsNotNone(article)
        assert article is not None
        self.assertEqual(article.publication_date, date(2026, 8, 11))
        self.assertEqual(article.publication_date_precision, "DAY")
        self.assertEqual(article.doi, "10.1039/d6sc05688a")
        self.assertEqual(
            {record.source for record in article.source_records},
            {"crossref", SURROGATE_SOURCE},
        )

    def test_issue_furniture_is_excluded_but_correction_is_retained(self):
        self.assertIsNone(RscChemicalScienceAdapter._article(raw_item("Front cover")))
        correction = RscChemicalScienceAdapter._article(
            raw_item("Correction: A useful scientific correction", doi="10.1039/D6SC90161A")
        )
        self.assertIsNotNone(correction)
        assert correction is not None
        self.assertEqual(correction.article_type, "Correction")

    def test_adapter_fails_closed_outside_exact_journal_scope(self):
        client = FakeClient({"message": {"total-results": 0, "items": []}})
        wrong = EditionSpec(
            "Other Journal",
            date(2026, 8, 1),
            date(2026, 8, 14),
            "other-journal",
            issn="2041-6539",
            sources=("rsc_chemical_science",),
        )
        result = RscChemicalScienceAdapter(client).fetch(wrong)
        self.assertEqual(result.check.status, "FAILED")
        self.assertEqual(client.calls, [])

    def test_full_source_success_allows_only_known_issue_furniture_exclusions(self):
        items = [
            raw_item(),
            raw_item("Front cover", doi="10.1039/D6SC90157C", created=(2026, 8, 5)),
            raw_item(
                "Correction: A useful scientific correction",
                doi="10.1039/D6SC90161A",
                created=(2026, 8, 13),
            ),
        ]
        client = FakeClient(
            {
                "message": {
                    "total-results": len(items),
                    "items": items,
                    "next-cursor": "",
                }
            }
        )
        result = RscChemicalScienceAdapter(client).fetch(self.spec)
        self.assertEqual(result.check.status, "SUCCESS")
        self.assertEqual(result.check.returned_count, 3)
        self.assertEqual(len(result.articles), 2)
        self.assertIn("issue furniture excluded=1", result.check.detail or "")
        self.assertIn("unexpected records rejected=0", result.check.detail or "")

    def test_unexpected_publisher_metadata_downgrades_to_partial(self):
        bad = raw_item(publisher="Unexpected Publisher")
        client = FakeClient(
            {
                "message": {
                    "total-results": 1,
                    "items": [bad],
                    "next-cursor": "",
                }
            }
        )
        result = RscChemicalScienceAdapter(client).fetch(self.spec)
        self.assertEqual(result.check.status, "PARTIAL")
        self.assertEqual(len(result.articles), 0)
        self.assertIn("unexpected records rejected=1", result.check.detail or "")


if __name__ == "__main__":
    unittest.main()
