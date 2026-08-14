import unittest
from pathlib import Path
from types import SimpleNamespace

from evidenceradar_editions.prefetch_triage import extract_paths
from evidenceradar_editions.prefetch_triage_v2 import build_prefetch_triage
from evidenceradar_editions.triage_policy import load_triage_policy


def article(index: int, title: str, *, doi: bool = True):
    return {
        "canonical_id": f"doi:10.1000/example.{index}",
        "title": title,
        "title_original": title,
        "title_zh_tw": f"測試題名 {index}",
        "summary_zh_tw": "依題名整理的繁中導讀。",
        "publication_date": "2026-08-13",
        "publication_date_precision": "DAY",
        "article_type": "journal-article",
        "authors": ["A Author"],
        "doi": f"10.1000/example.{index}" if doi else None,
        "pmid": None,
        "pmcid": None,
        "urls": [f"https://doi.org/10.1000/example.{index}"] if doi else [],
        "source_records": [{"source": "crossref"}],
    }


def publication(slug: str, titles: list[str]):
    return SimpleNamespace(
        journal_slug=slug,
        period_key="2026-08",
        revision=1,
        relative_path=f"journals/{slug}/2026-08/r01/",
        manifest={"publication_id": f"{slug}__2026-08__r01"},
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
            "articles": [article(index, title) for index, title in enumerate(titles)],
        },
    )


class PrefetchTriageTests(unittest.TestCase):
    def test_structural_patterns_avoid_known_false_positives(self):
        policy = load_triage_policy(Path("catalog"))
        _, paths, primary = extract_paths(
            article(
                1,
                "Robust stratification via recurrent autoencoder and consensus clustering",
            ),
            policy,
        )
        self.assertNotIn("GUIDANCE", paths)
        self.assertEqual(primary, "PRIMARY_METADATA")

        _, paths, _ = extract_paths(
            article(2, "Safety-centered evaluation of therapy recommendation systems"),
            policy,
        )
        self.assertNotIn("GUIDANCE", paths)

        _, paths, _ = extract_paths(
            article(3, "Novel oesophageal stimulation protocol in preterm infants"),
            policy,
        )
        self.assertNotIn("PROTOCOL", paths)

    def test_integrity_role_takes_precedence_over_design_words(self):
        pub = publication(
            "example-journal",
            [
                "Corrigendum to randomized controlled trial of intervention X",
                "Retraction Note: A systematic review of intervention Y",
                "Editorial: Special issue introduction",
            ],
        )
        index, editions = build_prefetch_triage(
            [pub],
            catalog_root=Path("catalog"),
            generated_at="2026-08-14T00:00:00Z",
        )
        counts = index["counts"]
        self.assertEqual(counts["integrity_review_count"], 2)
        self.assertEqual(counts["catalog_only_count"], 1)
        records = editions[pub.relative_path]["articles"]
        by_title = {record["title_original"]: record for record in records}
        correction = by_title[
            "Corrigendum to randomized controlled trial of intervention X"
        ]
        self.assertEqual(correction["route"], "INTEGRITY_REVIEW")
        self.assertEqual(correction["primary_path"], "CORRECTION_EVENT")
        self.assertNotIn("RANDOMIZED_TRIAL", correction["matched_paths"])

    def test_4397_record_journal_is_bounded_but_fully_auditable(self):
        titles = [
            f"Randomized controlled trial of intervention {index} in adults"
            for index in range(4397)
        ]
        pub = publication("example-journal", titles)
        index, editions = build_prefetch_triage(
            [pub],
            catalog_root=Path("catalog"),
            generated_at="2026-08-14T00:00:00Z",
        )
        counts = index["counts"]
        self.assertEqual(counts["canonical_article_count"], 4397)
        self.assertEqual(counts["fetch_candidate_count"], 20)
        self.assertEqual(counts["reserve_count"], 4377)
        self.assertEqual(counts["published_reserve_count"], 50)
        self.assertEqual(counts["unpublished_reserve_count"], 4327)
        self.assertEqual(index["item_count"], 70)
        self.assertEqual(len(index["items"]), 70)

        audit = editions[pub.relative_path]
        self.assertEqual(len(audit["articles"]), 4397)
        self.assertEqual(audit["counts"]["published_in_portfolio_index"], 70)
        self.assertTrue(
            all(record["processing_mode"] == "TRIAGE" for record in audit["articles"])
        )
        self.assertTrue(
            all(record["full_text_fetched"] is False for record in audit["articles"])
        )
        self.assertTrue(
            all(record["evidence_evaluated"] is False for record in audit["articles"])
        )

    def test_common_dataset_signal_is_demoted_inside_data_journal(self):
        titles = [f"Dataset of measurement series {index}" for index in range(50)]
        pub = publication("scientific-data", titles)
        index, editions = build_prefetch_triage(
            [pub],
            catalog_root=Path("catalog"),
            generated_at="2026-08-14T00:00:00Z",
        )
        self.assertEqual(index["counts"]["fetch_candidate_count"], 0)
        self.assertEqual(index["counts"]["reserve_count"], 50)
        records = editions[pub.relative_path]["articles"]
        self.assertTrue(
            all(
                record["signal_prevalence"]["saturation_applied"]
                for record in records
            )
        )
        self.assertTrue(
            all("COMMON_SOURCE_PATTERN" in record["reason_codes"] for record in records)
        )


if __name__ == "__main__":
    unittest.main()
