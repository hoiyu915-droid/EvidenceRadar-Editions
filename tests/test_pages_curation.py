import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from evidenceradar_editions.pages_curation import (
    build_browse_index,
    classify_publication_role,
    enhance_revision_pages,
)


def publication_with_articles(count: int):
    articles = []
    for index in range(count):
        title = f"Research article {index}"
        if index == count - 3:
            title = "Correction: Research article"
        elif index == count - 2:
            title = "Editorial Expression of Concern: Research article"
        elif index == count - 1:
            title = "Editorial: Research article"
        articles.append(
            {
                "canonical_id": f"doi:10.1000/{index}",
                "title_original": title,
                "title_zh_tw": f"研究文章 {index}",
                "summary_zh_tw": "依題名整理的繁中導讀。",
                "publication_date": "2026-08-14",
                "publication_date_precision": "DAY",
                "article_type": "journal-article",
                "authors": ["A Author"],
                "doi": f"10.1000/{index}",
                "pmid": None,
                "pmcid": None,
                "source_records": [{"source": "crossref"}],
            }
        )
    edition = {
        "edition_id": "example__2026-08__r01",
        "scope": {
            "journal": "Example Journal",
            "period_key": "2026-08",
            "period_label_zh_tw": "2026 年 8 月",
            "revision": 1,
        },
        "artifacts": {
            "report_html": "EvidenceRadar_Editions__example__2026-08__r01.html",
        },
        "articles": articles,
    }
    return SimpleNamespace(
        edition=edition,
        relative_path="journals/example/2026-08/r01/",
    )


class PagesCurationTests(unittest.TestCase):
    def test_conservative_role_classifier(self):
        self.assertEqual(classify_publication_role("Correction: Example"), "correction")
        self.assertEqual(classify_publication_role("Author Correction: Example"), "correction")
        self.assertEqual(classify_publication_role("Corrigendum to Example"), "correction")
        self.assertEqual(
            classify_publication_role("Editorial Expression of Concern: Example"),
            "concern",
        )
        self.assertEqual(classify_publication_role("Retraction Note: Example"), "concern")
        self.assertEqual(classify_publication_role("Editorial: Special collection"), "editorial")
        self.assertEqual(classify_publication_role("Preface to the special issue"), "editorial")
        self.assertEqual(
            classify_publication_role("Editorial quality as a predictor of uptake"),
            "primary",
        )

    def test_large_revision_defaults_to_primary_without_deleting_records(self):
        publication = publication_with_articles(205)
        browse = build_browse_index(publication)
        self.assertEqual(browse["article_count"], 205)
        self.assertEqual(browse["default_role"], "primary")
        self.assertEqual(browse["role_counts"]["primary"], 202)
        self.assertEqual(browse["role_counts"]["correction"], 1)
        self.assertEqual(browse["role_counts"]["concern"], 1)
        self.assertEqual(browse["role_counts"]["editorial"], 1)
        self.assertEqual(len(browse["articles"]), 205)

    def test_small_revision_defaults_to_all(self):
        browse = build_browse_index(publication_with_articles(10))
        self.assertEqual(browse["default_role"], "all")
        self.assertEqual(len(browse["articles"]), 10)

    def test_enhancement_writes_light_index_and_full_browse_json(self):
        publication = publication_with_articles(205)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            revision = root / publication.relative_path
            revision.mkdir(parents=True)
            count = enhance_revision_pages(
                output_dir=root,
                publications=[publication],
            )
            self.assertEqual(count, 1)
            browse_path = revision / "browse.json"
            page_path = revision / "index.html"
            self.assertTrue(browse_path.is_file())
            self.assertTrue(page_path.is_file())
            browse = json.loads(browse_path.read_text(encoding="utf-8"))
            self.assertEqual(browse["article_count"], 205)
            self.assertEqual(len(browse["articles"]), 205)
            page = page_path.read_text(encoding="utf-8")
            self.assertIn("非破壞式 curation", page)
            self.assertIn('id="filter-role"', page)
            self.assertIn('id="page-size"', page)
            self.assertIn("顯示全部角色", page)
            self.assertIn("完整 canonical HTML", page)
            self.assertNotIn("Research article 0", page)


if __name__ == "__main__":
    unittest.main()
