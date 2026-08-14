import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from evidenceradar_editions import pages_v9
from evidenceradar_editions.pages_v10 import build_pages_site


def publication():
    articles = [
        {
            "canonical_id": "doi:10.1000/systematic",
            "title": "Systematic review and meta-analysis of intervention X",
            "title_original": "Systematic review and meta-analysis of intervention X",
            "title_zh_tw": "介入 X 的系統性回顧與統合分析",
            "summary_zh_tw": "依題名整理的繁中導讀。",
            "publication_date": "2026-08-13",
            "publication_date_precision": "DAY",
            "article_type": "journal-article",
            "authors": ["A Author"],
            "doi": "10.1000/systematic",
            "pmid": None,
            "pmcid": None,
            "urls": ["https://doi.org/10.1000/systematic"],
            "source_records": [{"source": "crossref"}],
        },
        {
            "canonical_id": "doi:10.1000/correction",
            "title": "Correction: Example primary study",
            "title_original": "Correction: Example primary study",
            "title_zh_tw": "修正：範例原始研究",
            "summary_zh_tw": "依題名整理的繁中導讀。",
            "publication_date": "2026-08-13",
            "publication_date_precision": "DAY",
            "article_type": "journal-article",
            "authors": ["B Author"],
            "doi": "10.1000/correction",
            "pmid": None,
            "pmcid": None,
            "urls": ["https://doi.org/10.1000/correction"],
            "source_records": [{"source": "crossref"}],
        },
    ]
    return SimpleNamespace(
        journal_slug="jama-network-open",
        period_key="2026-08",
        revision=1,
        relative_path="journals/jama-network-open/2026-08/r01/",
        manifest={"publication_id": "jama-network-open__2026-08__r01"},
        edition={
            "edition_id": "jama-network-open__2026-08__r01",
            "publication_id": "jama-network-open__2026-08__r01",
            "scope": {
                "journal": "JAMA Network Open",
                "period_key": "2026-08",
                "period_label_zh_tw": "2026 年 8 月",
                "revision": 1,
                "end_date": "2026-08-31",
            },
            "articles": articles,
        },
    )


class PagesTriageTests(unittest.TestCase):
    def test_pages_writes_portfolio_and_full_edition_triage(self):
        pub = publication()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "site"
            editions = root / "editions"

            def fake_base(**kwargs):
                output.mkdir(parents=True)
                (output / "index.html").write_text(
                    '<html><body><main class="shell">portal</main></body></html>',
                    encoding="utf-8",
                )
                (output / "index.json").write_text("{}", encoding="utf-8")
                (output / "links.json").write_text("{}", encoding="utf-8")
                revision = output / pub.relative_path
                revision.mkdir(parents=True)
                (revision / "index.html").write_text(
                    '<html><body><main><a href="browse.json">browse JSON</a></main></body></html>',
                    encoding="utf-8",
                )
                return {"base_url": "https://example.test/"}

            with patch.object(
                pages_v9,
                "build_v8_pages_site",
                side_effect=fake_base,
            ), patch.object(
                pages_v9,
                "discover_stored_publications",
                return_value=[pub],
            ):
                links = build_pages_site(
                    output_dir=output,
                    repository="owner/repo",
                    editions_root=editions,
                    catalog_root=Path("catalog"),
                )

            self.assertTrue((output / "prefetch-triage.html").is_file())
            self.assertTrue((output / "prefetch-triage-index.json").is_file())
            self.assertTrue((output / "prefetch-triage-policy.json").is_file())
            revision = output / pub.relative_path
            self.assertTrue((revision / "triage.json").is_file())

            index = json.loads(
                (output / "prefetch-triage-index.json").read_text(encoding="utf-8")
            )
            self.assertEqual(index["counts"]["canonical_article_count"], 2)
            self.assertEqual(index["counts"]["fetch_candidate_count"], 1)
            self.assertEqual(index["counts"]["integrity_review_count"], 1)
            self.assertEqual(index["item_count"], 2)

            audit = json.loads((revision / "triage.json").read_text(encoding="utf-8"))
            self.assertEqual(len(audit["articles"]), 2)
            self.assertTrue(
                all(record["full_text_fetched"] is False for record in audit["articles"])
            )

            portal = (output / "index.html").read_text(encoding="utf-8")
            revision_html = (revision / "index.html").read_text(encoding="utf-8")
            self.assertIn("prefetch-triage.html", portal)
            self.assertIn('href="triage.json"', revision_html)
            self.assertEqual(
                links["prefetch_triage_url"],
                "https://example.test/prefetch-triage.html",
            )
            self.assertEqual(
                links["prefetch_triage"]["edition_audit_count"],
                1,
            )


if __name__ == "__main__":
    unittest.main()
