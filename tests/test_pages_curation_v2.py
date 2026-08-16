import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from evidenceradar_editions.pages_curation_v2 import (
    build_browse_index,
    enhance_revision_pages,
    render_browse_page,
)


CAMBRIDGE_URL = (
    "https://www.cambridge.org/core/journals/memory-mind-and-media/article/"
    "ai-at-war-on-screen-record-politics-and-mediated-memory-in-cinematic-futures/"
    "A9682CE5C2E89FE64DD18628E271ACFE"
)


def publication():
    edition = {
        "edition_id": "memory-mind-and-media__2026-08__r01",
        "scope": {
            "journal": "Memory, Mind & Media",
            "period_key": "2026-08",
            "period_label_zh_tw": "2026 年 8 月（MTD 至 8 月 16 日）",
            "revision": 1,
        },
        "artifacts": {
            "report_html": "EvidenceRadar_Editions__memory-mind-and-media__2026-08__r01.html",
        },
        "articles": [
            {
                "canonical_id": "fingerprint:aiatwaronscreen|2026-08-12",
                "title_original": "AI at war on screen: Record politics and mediated memory in cinematic futures",
                "title_zh_tw": None,
                "summary_zh_tw": None,
                "publication_date": "2026-08-12",
                "publication_date_precision": "DAY",
                "article_type": None,
                "authors": [],
                "doi": None,
                "pmid": None,
                "pmcid": None,
                "source_records": [
                    {
                        "source": "cambridge_core",
                        "url": CAMBRIDGE_URL,
                    }
                ],
                "urls": [CAMBRIDGE_URL],
            }
        ],
    }
    return SimpleNamespace(
        edition=edition,
        relative_path="journals/memory-mind-and-media/2026-08/r01/",
    )


class PagesCurationV2Tests(unittest.TestCase):
    def test_browse_projection_preserves_direct_source_link(self):
        browse = build_browse_index(publication())
        self.assertEqual(browse["schema_version"], "1.1")
        self.assertEqual(browse["source_labels"]["cambridge_core"], "Cambridge Core")
        article = browse["articles"][0]
        self.assertEqual(article["primary_url"], CAMBRIDGE_URL)
        self.assertEqual(len(article["external_links"]), 1)
        self.assertEqual(article["external_links"][0]["url"], CAMBRIDGE_URL)
        self.assertEqual(article["external_links"][0]["label"], "Cambridge Core")
        self.assertTrue(article["canonical_id"].startswith("fingerprint:"))

    def test_reader_card_links_title_and_hides_internal_identity(self):
        browse = build_browse_index(publication())
        page = render_browse_page(publication(), browse)
        self.assertIn("原文 ↗", page)
        self.assertIn('value="cambridge_core">Cambridge Core</option>', page)
        self.assertIn('value="unspecified">未分類</option>', page)
        self.assertIn("primary_url", page)
        self.assertNotIn("無標準識別碼", page)
        self.assertNotIn("<span>${esc(a.canonical_id||'')}</span>", page)
        self.assertIn("-webkit-text-size-adjust:100%", page)

    def test_enhancement_writes_source_links_into_browse_json(self):
        item = publication()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            revision = root / item.relative_path
            revision.mkdir(parents=True)
            self.assertEqual(
                enhance_revision_pages(output_dir=root, publications=[item]),
                1,
            )
            browse = json.loads((revision / "browse.json").read_text(encoding="utf-8"))
            self.assertEqual(browse["articles"][0]["primary_url"], CAMBRIDGE_URL)
            page = (revision / "index.html").read_text(encoding="utf-8")
            self.assertIn("原文 ↗", page)
            self.assertNotIn("無標準識別碼", page)


if __name__ == "__main__":
    unittest.main()
