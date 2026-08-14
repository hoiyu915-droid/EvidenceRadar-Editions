import copy
import unittest
from pathlib import Path

from evidenceradar_editions.metadata_triage import (
    MetadataTriagePolicyError,
    enrich_article_with_triage,
    load_metadata_triage_policy,
    select_triaged_projection,
    triage_article,
    validate_metadata_triage_policy,
)


def article(title: str, *, article_type: str = "journal-article", index: int = 1):
    return {
        "canonical_id": f"doi:10.1000/{index}",
        "title_original": title,
        "title_zh_tw": title,
        "publication_date": "2026-08-13",
        "publication_date_precision": "DAY",
        "article_type": article_type,
        "authors": ["A Author"],
        "doi": f"10.1000/{index}",
        "pmid": None,
        "pmcid": None,
        "sources": ["crossref"],
        "curation_role": "primary",
    }


class MetadataTriageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = load_metadata_triage_policy(Path("catalog"))

    def test_policy_is_executable_and_rejects_invalid_tier_order(self):
        self.assertEqual(self.policy["policy_id"], "metadata-title-triage-v1")
        invalid = copy.deepcopy(self.policy)
        invalid["tier_order"] = ["HIGH", "ALERT", "MEDIUM", "LOW"]
        with self.assertRaises(MetadataTriagePolicyError):
            validate_metadata_triage_policy(invalid)

    def test_safety_alert_is_not_misread_as_an_editorial(self):
        decision = triage_article(
            article("Editorial Expression of Concern: Example"),
            policy=self.policy,
        )
        self.assertEqual(decision.tier, "ALERT")
        self.assertEqual(decision.attention_class, "SAFETY_ALERT")
        self.assertEqual(decision.fetch_recommendation, "VERIFY_IMMEDIATELY")

    def test_correction_is_terminal_even_when_corrected_title_mentions_review(self):
        decision = triage_article(
            article("Correction: Systematic review and meta-analysis of exercise"),
            policy=self.policy,
        )
        self.assertEqual(decision.tier, "LOW")
        self.assertEqual(decision.attention_class, "CORRECTION")
        self.assertEqual(decision.reason_codes[0], "CORRECTION")
        self.assertNotIn("EVIDENCE_SYNTHESIS", decision.reason_codes)

    def test_high_priority_signals_cover_synthesis_trials_and_resources(self):
        cases = [
            ("A systematic review of resistance training", "EVIDENCE_SYNTHESIS"),
            ("A randomized controlled trial of protein supplementation", "CONTROLLED_TRIAL"),
            ("An open dataset for evaluating language models", "RESOURCE_OR_BENCHMARK"),
            ("External validation of a diagnostic prediction model", "VALIDATION_OR_DIAGNOSTIC"),
        ]
        for index, (title, expected_class) in enumerate(cases, start=1):
            with self.subTest(title=title):
                decision = triage_article(
                    article(title, index=index),
                    policy=self.policy,
                )
                self.assertEqual(decision.tier, "HIGH")
                self.assertEqual(decision.attention_class, expected_class)
                self.assertEqual(decision.fetch_recommendation, "FETCH_PRIORITY")

    def test_default_is_medium_and_explicitly_not_an_evidence_grade(self):
        enriched = enrich_article_with_triage(
            article("Molecular dynamics of a catalytic interface"),
            policy=self.policy,
        )
        triage = enriched["metadata_triage"]
        self.assertEqual(triage["tier"], "MEDIUM")
        self.assertEqual(triage["attention_class"], "PRIMARY_RESEARCH")
        self.assertTrue(
            triage["requires_abstract_or_full_text_for_scientific_judgment"]
        )
        self.assertIn("not evidence-quality", triage["semantics"])

    def test_projection_reviews_all_records_before_applying_limit(self):
        records = [
            article(f"Ordinary primary research record {index}", index=index)
            for index in range(1, 301)
        ]
        priority = article(
            "Systematic review of an important intervention",
            index=999,
        )
        records.append(priority)
        projected = select_triaged_projection(
            records,
            limit=10,
            policy=self.policy,
        )
        ids = {value["canonical_id"] for value in projected}
        self.assertIn(priority["canonical_id"], ids)
        self.assertEqual(
            projected[0]["metadata_triage"]["tier"],
            "HIGH",
        )

    def test_projection_round_robins_classes_and_suppresses_near_duplicates(self):
        records = [
            article(
                "Systematic review of exercise and health outcomes in adults",
                index=1,
            ),
            article(
                "Systematic review of exercise and health outcomes among adults",
                index=2,
            ),
            article(
                "Randomized controlled trial of a nutrition intervention",
                index=3,
            ),
        ]
        projected = select_triaged_projection(
            records,
            limit=2,
            policy=self.policy,
        )
        classes = {
            value["metadata_triage"]["attention_class"]
            for value in projected
        }
        self.assertEqual(
            classes,
            {"EVIDENCE_SYNTHESIS", "CONTROLLED_TRIAL"},
        )


if __name__ == "__main__":
    unittest.main()
