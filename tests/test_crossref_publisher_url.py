import unittest

from evidenceradar_editions.adapters.crossref import CrossrefAdapter, _publisher_url


def raw_item() -> dict:
    return {
        "title": ["Example"],
        "container-title": ["Computers in Human Behavior: Artificial Humans"],
        "published-online": {"date-parts": [[2026, 8, 1]]},
        "DOI": "10.1016/j.chbah.2026.100338",
        "ISSN": ["2949-8821"],
        "author": [],
        "URL": "https://doi.org/10.1016/j.chbah.2026.100338",
        "type": "journal-article",
        "resource": {
            "primary": {
                "URL": "https://linkinghub.elsevier.com/retrieve/pii/S2949882126000903"
            }
        },
    }


class CrossrefPublisherUrlTests(unittest.TestCase):
    def test_linkinghub_pii_is_normalized_to_sciencedirect(self):
        self.assertEqual(
            _publisher_url(raw_item()),
            "https://www.sciencedirect.com/science/article/pii/S2949882126000903",
        )

    def test_article_prefers_crossref_primary_resource(self):
        article = CrossrefAdapter._article(raw_item())

        self.assertIsNotNone(article)
        self.assertEqual(
            article.urls,
            ["https://www.sciencedirect.com/science/article/pii/S2949882126000903"],
        )
        self.assertEqual(article.source_records[0].url, article.urls[0])


if __name__ == "__main__":
    unittest.main()
