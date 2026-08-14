import unittest
from pathlib import Path
from types import SimpleNamespace

from evidenceradar_editions.pages_search import (
    build_projected_search_index,
    latest_publications,
)


def publication(slug: str, count: int, *, revision: int = 1, period: str = "2026-08"):
    articles = []
    for index in range(count):
        articles.append(
            {
                "canonical_id": f"doi:10.1000/{slug}.{revision}.{index}",
                "title_original": f"{slug} research article {index}",
                "title_zh_tw": f"{slug} 研究文章 {index}",
                "summary_zh_tw": "依題名整理的繁中導讀。",
                "publication_date": "2026-08-13",
                "publication_date_precision": "DAY",
                "article_type": "journal-article",
                "authors": ["A Author"],
                "doi": f"10.1000/{slug}.{revision}.{index}",
                "pmid": None,
                "pmcid": None,
                "source_records": [{"source": "crossref"}],
            }
        )
    return SimpleNamespace(
        journal_slug=slug,
        period_key=period,
        revision=revision,
        relative_path=f"journals/{slug}/{period}/r{revision:02d}/",
        edition={
            "scope": {
                "journal": slug.replace("-", " ").title(),
                "period_key": period,
                "period_label_zh_tw": "2026 年 8 月",
                "revision": revision,
                "end_date": "2026-08-31",
            },
            "articles": articles,
        },
    )


class PagesSearchProjectionTests(unittest.TestCase):
    def test_global_search_does_not_reexpand_4397_record_edition(self):
        large = publication("example-journal", 4397)
        small = publication("small-journal", 10)
        search = build_projected_search_index(
            [large, small],
            catalog_root=Path("catalog"),
            generated_at="2026-08-14T00:00:00Z",
        )
        self.assertEqual(search["canonical_article_count"], 4407)
        self.assertEqual(search["projected_article_count"], 260)
        self.assertEqual(search["article_count"], 260)
        self.assertEqual(search["omitted_article_count"], 4147)
        self.assertEqual(search["processing_mode_counts"]["TRIAGE"], 1)
        self.assertEqual(search["processing_mode_counts"]["FULL"], 1)
        self.assertIn("not quality or relevance ranking", search["projection_semantics"])
        self.assertEqual(len(search["articles"]), 260)

    def test_only_highest_revision_enters_global_search(self):
        old = publication("example-journal", 100, revision=1)
        current = publication("example-journal", 20, revision=2)
        latest = latest_publications([old, current])
        self.assertEqual(len(latest), 1)
        self.assertEqual(latest[0].revision, 2)
        search = build_projected_search_index(
            [old, current],
            catalog_root=Path("catalog"),
            generated_at="2026-08-14T00:00:00Z",
        )
        self.assertEqual(search["canonical_article_count"], 20)
        self.assertEqual(search["article_count"], 20)
        self.assertTrue(all(item["revision"] == 2 for item in search["articles"]))


if __name__ == "__main__":
    unittest.main()
