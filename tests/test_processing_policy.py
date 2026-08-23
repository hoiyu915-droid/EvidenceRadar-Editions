import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from evidenceradar_editions.engine_v2 import build_run
from evidenceradar_editions.models import EditionSpec
from evidenceradar_editions.processing_policy import (
    JournalSuspendedError,
    apply_volume_guard,
    load_processing_policy_catalog,
    policy_for_slug,
)


class ProcessingPolicyTests(unittest.TestCase):
    def test_repository_policy_marks_scientific_reports_as_triage(self):
        catalog = load_processing_policy_catalog(Path("catalog"))
        policy = policy_for_slug(
            "scientific-reports",
            catalog_root=Path("catalog"),
            catalog=catalog,
        )
        self.assertEqual(policy.configured_mode, "TRIAGE")
        self.assertEqual(policy.source_record_limit, 500)
        self.assertEqual(policy.pages_record_limit, 250)
        self.assertEqual(policy.translation_mode, "DEFERRED")

    def test_repository_policy_triages_broad_relationship_discovery_journals(self):
        for slug in ("bmc-psychology", "bmc-womens-health"):
            with self.subTest(slug=slug):
                policy = policy_for_slug(slug, catalog_root=Path("catalog"))
                self.assertEqual(policy.configured_mode, "TRIAGE")
                self.assertEqual(policy.source_record_limit, 500)
                self.assertEqual(policy.pages_record_limit, 250)
                self.assertEqual(policy.translation_mode, "DEFERRED")

    def test_full_policy_auto_triages_4397_reported_records(self):
        policy = policy_for_slug("example-journal", catalog_root=Path("catalog"))
        effective = apply_volume_guard(
            policy,
            [{"source": "crossref", "total_available": 4397}],
        )
        self.assertEqual(effective.configured_mode, "FULL")
        self.assertEqual(effective.effective_mode, "TRIAGE")
        self.assertTrue(effective.volume_guard_triggered)
        self.assertEqual(effective.source_reported_total_max, 4397)
        self.assertEqual(effective.pages_record_limit, 250)
        self.assertEqual(effective.translation_mode, "DEFERRED")

    def test_suspended_policy_blocks_before_core_acquisition(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "processing-policies.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "EvidenceRadar_Editions_ProcessingPolicies",
                        "defaults": {"mode": "FULL"},
                        "journals": {
                            "example-journal": {
                                "mode": "SUSPENDED",
                                "note": "test suspension",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            policy = policy_for_slug("example-journal", catalog_root=root)
            spec = EditionSpec(
                journal="Example Journal",
                slug="example-journal",
                start_date=date(2026, 8, 1),
                end_date=date(2026, 8, 31),
                sources=("crossref",),
            )
            with patch("evidenceradar_editions.engine_v2._build_core_run") as core:
                with self.assertRaises(JournalSuspendedError):
                    build_run(
                        spec,
                        processing_policy=policy,
                        catalog_root=root,
                    )
                core.assert_not_called()

    def test_engine_clamps_source_budget_and_records_metadata_boundary(self):
        policy = policy_for_slug("example-journal", catalog_root=Path("catalog"))
        spec = EditionSpec(
            journal="Example Journal",
            slug="example-journal",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 31),
            sources=("crossref",),
            max_records=5000,
        )
        observed = {}

        def fake_core(core_spec, **kwargs):
            observed["max_records"] = core_spec.max_records
            return {
                "scope": core_spec.to_dict(),
                "presentation": {},
                "translation": {},
                "source_checks": [
                    {
                        "source": "crossref",
                        "status": "PARTIAL",
                        "query": "example",
                        "returned_count": 500,
                        "accepted_count": 500,
                        "total_available": 4397,
                        "truncated": True,
                        "detail": "bounded",
                    }
                ],
                "counts": {"articles": 500},
                "articles": [{} for _ in range(500)],
            }

        with patch(
            "evidenceradar_editions.engine_v2._build_core_run",
            side_effect=fake_core,
        ):
            run = build_run(
                spec,
                processing_policy=policy,
                catalog_root=Path("catalog"),
            )

        self.assertEqual(observed["max_records"], 500)
        processing = run["processing"]
        self.assertEqual(processing["effective_mode"], "TRIAGE")
        self.assertEqual(processing["applied_source_record_limit"], 500)
        self.assertEqual(processing["acquisition_level"], "BIBLIOGRAPHIC_METADATA")
        self.assertFalse(processing["full_text_fetched"])
        self.assertFalse(processing["evidence_evaluated"])
        self.assertEqual(processing["pages_projected_article_count"], 250)
        self.assertEqual(processing["pages_omitted_article_count"], 250)


if __name__ == "__main__":
    unittest.main()
