import unittest
from pathlib import Path
from types import SimpleNamespace

from evidenceradar_editions.metadata_triage import load_metadata_triage_policy
from evidenceradar_editions.processing_policy import (
    load_processing_policy_catalog,
    policy_for_slug,
)
from evidenceradar_editions.triage_index import build_metadata_triage_indices
from evidenceradar_editions.triage_pages import (
    build_triaged_browse_index,
    render_triaged_revision_page,
)
from evidenceradar_editions.triage_render import (
    render_metadata_triage_dashboard,
)


def publication(slug: str, count: int, *, high_last: bool = False):
    articles = []
    for index in range(count):
        title = f"Ordinary primary research record {index}"
        if high_last and index == count - 1:
            title = "Systematic review of an important intervention"
        articles.append(
            {
                "canonical_id": f"doi:10.1000/{slug}.{index}",
                "title_original": title,
                "title_zh_tw": f"研究文章 {index}",
                "summary_zh_tw": "依題名整理的繁中導讀。",
                "publication_date": "2026-08-13",
                "publication_date_precision": "DAY",
                "article_type": "journal-article",
                "authors": ["A Author"],
                "doi": f"10.1000/{slug}.{index}",
                "pmid": None,
                "pmcid": None,
                "source_records": [{"source": "crossref"}],
            }
        )
    return SimpleNamespace(
        journal_slug=slug,
        period_key="2026-08",
        revision=1,
        relative_path=f"journals/{slug}/2026-08/r01/",
        edition={
            "edition_id": f"{slug}__2026-08__r01",
            "publication_id": f"{slug}__2026-08__r01",
            "scope": {
                "journal": slug.replace("-", " ").title(),
                "period_key": "2026-08",
                "period_label_zh_tw": "2026 年 8 月",
                "revision": 1,
                "end_date": "2026-08-31",
            },
            "artifacts": {
                "report_html": f"EvidenceRadar_Editions__{slug}__2026-08__r01.html"
            },
            "articles": articles,
        },
    )


class TriagePagesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.triage_policy = load_metadata_triage_policy(Path("catalog"))
        cls.processing_catalog = load_processing_policy_catalog(Path("catalog"))

    def triage(self, item):
        processing = policy_for_slug(
            item.journal_slug,
            catalog_root=Path("catalog"),
            catalog=self.processing_catalog,
        )
        return build_triaged_browse_index(
            item,
            processing_policy=processing,
            triage_policy=self.triage_policy,
        )

    def test_4397_existing_records_are_all_triaged_before_projection(self):
        item = publication("example-journal", 4397, high_last=True)
        browse, effective, all_articles = self.triage(item)
        self.assertEqual(effective.effective_mode, "TRIAGE")
        self.assertTrue(effective.volume_guard_triggered)
        self.assertEqual(len(all_articles), 4397)
        self.assertEqual(browse["projection"]["canonical_article_count"], 4397)
        self.assertEqual(browse["projection"]["projected_article_count"], 250)
        self.assertEqual(browse["projection"]["omitted_article_count"], 4147)
        self.assertEqual(len(browse["articles"]), 250)
        self.assertTrue(
            all("metadata_triage" in value for value in all_articles)
        )
        self.assertTrue(
            any(
                value["title_original"]
                == "Systematic review of an important intervention"
                for value in browse["articles"]
            )
        )
        self.assertEqual(
            browse["metadata_triage"]["policy_id"],
            "metadata-title-triage-v1",
        )

    def test_latest_corpus_gets_all_record_index_and_bounded_search(self):
        large = publication("example-journal", 4397, high_last=True)
        small = publication("small-journal", 10)
        large_browse, large_effective, large_all = self.triage(large)
        small_browse, small_effective, small_all = self.triage(small)
        results = {
            "large": {
                "publication": large,
                "browse": large_browse,
                "effective_processing_policy": large_effective,
                "all_articles": large_all,
            },
            "small": {
                "publication": small,
                "browse": small_browse,
                "effective_processing_policy": small_effective,
                "all_articles": small_all,
            },
        }
        registry = {
            "example-journal": {
                "publisher": "Example",
                "categories": ["interdisciplinary"],
            },
            "small-journal": {
                "publisher": "Example",
                "categories": ["clinical_medicine"],
            },
        }
        triage_index, search_index = build_metadata_triage_indices(
            [large, small],
            triage_results=results,
            registry_by_slug=registry,
            policy_id="metadata-title-triage-v1",
            generated_at="2026-08-14T00:00:00Z",
        )
        self.assertEqual(triage_index["canonical_article_count"], 4407)
        self.assertEqual(len(triage_index["articles"]), 4407)
        self.assertEqual(triage_index["default_projected_article_count"], 260)
        self.assertEqual(triage_index["default_omitted_article_count"], 4147)
        self.assertEqual(search_index["article_count"], 260)
        self.assertEqual(len(search_index["articles"]), 260)
        self.assertEqual(search_index["omitted_article_count"], 4147)
        self.assertTrue(
            any(
                (value.get("metadata_triage") or {}).get("tier") == "HIGH"
                for value in search_index["articles"]
            )
        )
        self.assertIn("operational", search_index["projection_semantics"])
        dashboard = render_metadata_triage_dashboard(triage_index)
        self.assertIn("Metadata Triage", dashboard)
        self.assertIn("4,407", dashboard)
        self.assertIn("這不是論文評分", dashboard)

    def test_revision_page_exposes_reasons_and_canonical_downloads(self):
        item = publication("example-journal", 12, high_last=True)
        browse, _, _ = self.triage(item)
        page = render_triaged_revision_page(item, browse)
        self.assertIn("這是候選分流，不是論文評分", page)
        self.assertIn("完整 canonical HTML", page)
        self.assertIn("理由碼", page)
        self.assertIn("Triage tier", page)


if __name__ == "__main__":
    unittest.main()
