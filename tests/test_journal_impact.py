import copy
import unittest

from evidenceradar_editions.journal_impact import (
    impact_registry_sha256,
    resolve_journal_impact_priors,
    validate_journal_impact_registry,
)


def registry():
    return {
        "schema_version": "1.0",
        "artifact_type": "EvidenceRadar_Editions_JournalImpactRegistry",
        "observed_at": "2026-08-15",
        "semantics": "test",
        "metric_preference": ["JIF", "CITESCORE"],
        "normalization": {
            "peer_group": "registry_category_and_metric_kind",
            "percentile_method": "midrank",
            "multi_category_aggregation": "arithmetic_mean",
            "unknown_percentile": 50.0,
        },
        "journals": {
            "jif-low": {
                "name": "JIF Low",
                "publisher": "P",
                "categories": ["field"],
                "status": "VERIFIED_PUBLISHER_DISPLAY",
                "metrics": {
                    "JIF": {"value": 2.0, "year": 2025},
                    "CITESCORE": {"value": 5.0, "year": 2025},
                },
                "source_url": "https://example.test/jif-low",
                "source_note": "test",
            },
            "jif-high": {
                "name": "JIF High",
                "publisher": "P",
                "categories": ["field"],
                "status": "VERIFIED_PUBLISHER_DISPLAY",
                "metrics": {
                    "JIF": {"value": 10.0, "year": 2025},
                    "CITESCORE": {"value": 20.0, "year": 2025},
                },
                "source_url": "https://example.test/jif-high",
                "source_note": "test",
            },
            "citescore-only": {
                "name": "CiteScore Only",
                "publisher": "P",
                "categories": ["field"],
                "status": "VERIFIED_PUBLISHER_DISPLAY",
                "metrics": {
                    "CITESCORE": {"value": 18.0, "year": 2025},
                },
                "source_url": "https://example.test/citescore",
                "source_note": "test",
            },
            "unknown": {
                "name": "Unknown",
                "publisher": "P",
                "categories": ["field"],
                "status": "NO_PUBLIC_VERIFIED_METRIC",
                "metrics": {},
                "source_url": "https://example.test/unknown",
                "source_note": "neutral",
            },
        },
    }


class JournalImpactTests(unittest.TestCase):
    def test_citescore_fallback_uses_all_citescore_peers(self):
        priors = resolve_journal_impact_priors(registry())
        value = priors["citescore-only"]
        self.assertEqual(value["primary_metric_kind"], "CITESCORE")
        # 18 is above 5 and below 20: (1 + .5) / 3 = 50th percentile.
        self.assertEqual(value["registry_category_percentile"], 50.0)

    def test_missing_metric_is_neutral_not_penalized(self):
        priors = resolve_journal_impact_priors(registry())
        value = priors["unknown"]
        self.assertTrue(value["unknown_metric"])
        self.assertEqual(value["registry_category_percentile"], 50.0)
        self.assertEqual(value["metric_status"], "NO_PUBLIC_VERIFIED_METRIC")

    def test_multi_category_prior_is_arithmetic_mean(self):
        value = registry()
        value["journals"]["multi"] = {
            "name": "Multi",
            "publisher": "P",
            "categories": ["field", "other"],
            "status": "VERIFIED_PUBLISHER_DISPLAY",
            "metrics": {"JIF": {"value": 6.0, "year": 2025}},
            "source_url": "https://example.test/multi",
            "source_note": "test",
        }
        value["journals"]["other-high"] = {
            "name": "Other High",
            "publisher": "P",
            "categories": ["other"],
            "status": "VERIFIED_PUBLISHER_DISPLAY",
            "metrics": {"JIF": {"value": 20.0, "year": 2025}},
            "source_url": "https://example.test/other-high",
            "source_note": "test",
        }
        prior = resolve_journal_impact_priors(value)["multi"]
        expected = sum(prior["category_percentiles"].values()) / 2
        self.assertEqual(prior["registry_category_percentile"], expected)

    def test_registry_digest_is_deterministic_and_tamper_sensitive(self):
        first = validate_journal_impact_registry(registry())
        second = validate_journal_impact_registry(copy.deepcopy(registry()))
        self.assertEqual(impact_registry_sha256(first), impact_registry_sha256(second))
        changed = copy.deepcopy(registry())
        changed["journals"]["jif-high"]["metrics"]["JIF"]["value"] = 9.9
        self.assertNotEqual(
            impact_registry_sha256(first),
            impact_registry_sha256(validate_journal_impact_registry(changed)),
        )


if __name__ == "__main__":
    unittest.main()
