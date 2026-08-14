import unittest
from pathlib import Path

from evidenceradar_editions.prefetch_triage_precision import extract_paths
from evidenceradar_editions.prefetch_triage_v3 import build_prefetch_triage
from evidenceradar_editions.triage_policy_defaults import load_triage_policy


def article(title: str):
    return {
        "canonical_id": "doi:10.1000/example",
        "title": title,
        "title_original": title,
        "doi": "10.1000/example",
        "pmid": None,
        "pmcid": None,
        "urls": ["https://doi.org/10.1000/example"],
    }


class PrefetchTriagePrecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = load_triage_policy(Path("catalog"))

    def classify(self, title: str):
        return extract_paths(article(title), self.policy)

    def test_biological_replication_is_not_reproducibility(self):
        _, paths, primary = self.classify(
            "Nuclear compartmentalization at the G1/S transition plays a key role in DNA replication control"
        )
        self.assertNotIn("REPLICATION_VALIDATION", paths)
        self.assertEqual(primary, "PRIMARY_METADATA")

        _, paths, primary = self.classify(
            "XFeat Revisited: Reproducibility and Evaluation of a Lightweight Image Matcher"
        )
        self.assertIn("REPLICATION_VALIDATION", paths)
        self.assertEqual(primary, "REPLICATION_VALIDATION")

        _, paths, _ = self.classify(
            "Tailored living mycelium macerate for reproducible flexible actuators"
        )
        self.assertNotIn("REPLICATION_VALIDATION", paths)

    def test_incidental_guideline_language_does_not_override_design(self):
        _, paths, primary = self.classify(
            "Effects of a guidelines-aligned diet on biomarkers: a randomized controlled trial"
        )
        self.assertNotIn("GUIDANCE", paths)
        self.assertEqual(primary, "RANDOMIZED_TRIAL")

        _, paths, primary = self.classify(
            "Compliance with guidelines for antibiotic therapy: a retrospective cohort study"
        )
        self.assertNotIn("GUIDANCE", paths)
        self.assertEqual(primary, "OBSERVATIONAL_DESIGN")

        _, paths, primary = self.classify(
            "Beyond Accuracy: Safety-Centered guidelines for evaluating therapy systems"
        )
        self.assertIn("GUIDANCE", paths)
        self.assertEqual(primary, "GUIDANCE")

        _, paths, primary = self.classify(
            "Beyond majority voting: evaluating AI diagnostic systems against expert consensus"
        )
        self.assertNotIn("GUIDANCE", paths)
        self.assertEqual(primary, "PRIMARY_METADATA")

    def test_correspondence_prefix_blocks_embedded_study_signals(self):
        for title in (
            "Re: Artificial intelligence in hospital malnutrition: A systematic review",
            "Comment on mortality after nutritional intervention",
            "Reply - Letter to the Editor: chemotherapy toxicity prediction",
            "Concerns about a multi-site prospective observational study",
        ):
            role, paths, primary = self.classify(title)
            self.assertEqual(role, "correspondence")
            self.assertEqual(paths, ["EDITORIAL"])
            self.assertEqual(primary, "EDITORIAL")

    def test_nonrandomised_trial_does_not_match_randomized_path(self):
        _, paths, primary = self.classify(
            "Phase II Non-Randomised Trial of Oral Chlorophyllin in Radiation Therapy"
        )
        self.assertNotIn("RANDOMIZED_TRIAL", paths)
        self.assertEqual(primary, "PRIMARY_METADATA")

    def test_dataset_mentions_require_resource_structure(self):
        _, paths, primary = self.classify(
            "Genetic Ancestry and Colorectal Cancer in the All of Us Dataset"
        )
        self.assertNotIn("RESOURCE_BENCHMARK", paths)
        self.assertEqual(primary, "PRIMARY_METADATA")

        _, paths, primary = self.classify(
            "A novel dataset and model for driver attention prediction"
        )
        self.assertIn("RESOURCE_BENCHMARK", paths)
        self.assertEqual(primary, "RESOURCE_BENCHMARK")

    def test_design_terms_require_study_context(self):
        _, paths, primary = self.classify(
            "Patient experiences of barriers to longitudinal care in meningitis"
        )
        self.assertNotIn("PROSPECTIVE_LONGITUDINAL", paths)
        self.assertEqual(primary, "PRIMARY_METADATA")

        _, paths, primary = self.classify(
            "Risk factors in a retrospective cohort study of electronic records"
        )
        self.assertNotIn("PROSPECTIVE_LONGITUDINAL", paths)
        self.assertEqual(primary, "OBSERVATIONAL_DESIGN")

        _, paths, primary = self.classify(
            "Outcomes in a prospective multicentre cohort study"
        )
        self.assertIn("PROSPECTIVE_LONGITUDINAL", paths)
        self.assertEqual(primary, "PROSPECTIVE_LONGITUDINAL")


if __name__ == "__main__":
    unittest.main()
