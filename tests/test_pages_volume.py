import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from evidenceradar_editions.pages_volume import (
    build_projected_browse_index,
    enhance_revision_pages,
)
from evidenceradar_editions.processing_policy import policy_for_slug


def publication_with_articles(count: int):
    articles = []
    for index in range(count):
        articles.append(
            {
                "canonical_id": f"doi:10.1000/{index}",
                "title_original": f"Research article {index}",
                "title_zh_tw": f"研究文章 {index}",
                "summary_zh_tw": "依題名整理的繁中導讀。",
                "publication_date": "2026-08-13",
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
        "edition_id": "example-journal__2026-08__r01",
        "scope": {
            "journal": "Example Journal",
            "period_key": "2026-08",
            "period_label_zh_tw": "2026 年 8 月",
            "revision": 1,
        },
        "artifacts": {
            "report_html": "EvidenceRadar_Editions__example-journal__2026-08__r01.html",
        },
        "articles": articles,
    }
    return SimpleNamespace(
        journal_slug="example-journal",
        edition=edition,
        relative_path="journals/example-journal/2026-08/r01/",
    )


class PagesVolumeTests(unittest.TestCase):
    def test_4397_record_edition_is_projected_without_claiming_ranking(self):
        publication = publication_with_articles(4397)
        policy = policy_for_slug("example-journal", catalog_root=Path("catalog"))
        browse, effective = build_projected_browse_index(publication, policy)
        self.assertEqual(effective.effective_mode, "TRIAGE")
        self.assertTrue(effective.volume_guard_triggered)
        self.assertEqual(browse["article_count"], 4397)
        self.assertEqual(len(browse["articles"]), 250)
        self.assertEqual(browse["projection"]["projected_article_count"], 250)
        self.assertEqual(browse["projection"]["omitted_article_count"], 4147)
        self.assertTrue(browse["projection"]["canonical_json_complete"])
        self.assertIn("not a quality", browse["projection"]["selection_basis"])

    def test_small_edition_remains_inline_all(self):
        publication = publication_with_articles(10)
        policy = policy_for_slug("example-journal", catalog_root=Path("catalog"))
        browse, effective = build_projected_browse_index(publication, policy)
        self.assertEqual(effective.effective_mode, "FULL")
        self.assertEqual(browse["projection"]["mode"], "INLINE_ALL")
        self.assertEqual(len(browse["articles"]), 10)
        self.assertEqual(browse["projection"]["omitted_article_count"], 0)

    def test_revision_page_discloses_projection_and_keeps_canonical_count(self):
        publication = publication_with_articles(4397)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            revision = root / publication.relative_path
            revision.mkdir(parents=True)
            stats = enhance_revision_pages(
                output_dir=root,
                publications=[publication],
                catalog_root=Path("catalog"),
            )
            browse = json.loads((revision / "browse.json").read_text(encoding="utf-8"))
            page = (revision / "index.html").read_text(encoding="utf-8")
            self.assertEqual(stats["canonical_article_count"], 4397)
            self.assertEqual(stats["projected_article_count"], 250)
            self.assertEqual(stats["omitted_article_count"], 4147)
            self.assertEqual(len(browse["articles"]), 250)
            self.assertIn("250 / 4397", page)
            self.assertIn("不是品質、證據力或相關性排名", page)
            self.assertIn("完整 canonical JSON", page)


if __name__ == "__main__":
    unittest.main()
