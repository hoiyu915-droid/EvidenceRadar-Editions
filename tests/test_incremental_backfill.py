from __future__ import annotations

from copy import deepcopy
import json
import tempfile
import unittest
from pathlib import Path

from evidenceradar_editions.bundle import write_bundle
from evidenceradar_editions.incremental_backfill import (
    INCREMENTAL_SEMANTICS,
    compose_incremental_month_revision,
)
from evidenceradar_editions.incremental_batch import load_batch_request
from evidenceradar_editions.utils import sha256_file
from evidenceradar_editions.validate import validate_bundle


class IncrementalBackfillTests(unittest.TestCase):
    def setUp(self):
        self.base_dir = Path("editions/acs-central-science/2026/08/r01")
        self.base = json.loads((self.base_dir / "edition.json").read_text(encoding="utf-8"))
        self.manifest = json.loads((self.base_dir / "manifest.json").read_text(encoding="utf-8"))

    def delta(self) -> dict:
        article = deepcopy(self.base["articles"][0])
        article.update(
            {
                "canonical_id": "doi:10.1021/acscentsci.6c99999",
                "doi": "10.1021/acscentsci.6c99999",
                "publication_date": "2026-08-18",
                "title": "Incrementally acquired article",
                "title_original": "Incrementally acquired article",
                "title_zh_tw": None,
                "summary_zh_tw": None,
                "translation_basis": None,
                "translation_source_url": None,
                "translation_status": "MISSING",
                "urls": ["https://doi.org/10.1021/acscentsci.6c99999"],
                "source_records": [
                    {
                        "source": "crossref",
                        "source_id": "10.1021/acscentsci.6c99999",
                        "url": "https://doi.org/10.1021/acscentsci.6c99999",
                    }
                ],
            }
        )
        return {
            "retrieved_at": "2026-08-19T09:00:00Z",
            "run_status": "COMPLETE",
            "scope": {
                "journal_slug": "acs-central-science",
                "start_date": "2026-08-15",
                "end_date": "2026-08-19",
                "sources": ["crossref"],
                "max_records": 5000,
            },
            "upstream_radar": deepcopy(self.base["upstream_radar"]),
            "source_checks": [
                {
                    "source": "crossref",
                    "status": "SUCCESS",
                    "query": "publication=2026-08-15..2026-08-19",
                    "returned_count": 1,
                    "accepted_count": 1,
                    "total_available": 1,
                    "truncated": False,
                    "detail": None,
                }
            ],
            "processing": {
                "pages_record_limit": 250,
                "configured_mode": "FULL",
                "effective_mode": "FULL",
            },
            "articles": [article],
        }

    def test_composes_new_month_revision_without_mutating_base(self):
        original = deepcopy(self.base)
        run = compose_incremental_month_revision(
            base=self.base,
            base_manifest=self.manifest,
            base_edition_sha256=sha256_file(self.base_dir / "edition.json"),
            delta=self.delta(),
            revision=2,
        )
        self.assertEqual(self.base, original)
        self.assertEqual(run["publication_id"], "acs-central-science__2026-08__r02")
        self.assertEqual(run["scope"]["end_date"], "2026-08-19")
        self.assertEqual(run["counts"]["articles"], len(self.base["articles"]) + 1)
        self.assertEqual(run["translation"]["status"], "PARTIAL")
        self.assertEqual(run["data_semantics"], INCREMENTAL_SEMANTICS)
        self.assertEqual(run["incremental_backfill"]["added_article_count"], 1)

        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "bundle"
            write_bundle(run, bundle)
            self.assertEqual(validate_bundle(bundle, require_zh_tw=False), [])

    def test_rejects_gap_between_base_and_incremental_window(self):
        delta = self.delta()
        delta["scope"]["start_date"] = "2026-08-16"
        with self.assertRaisesRegex(ValueError, "day after the base"):
            compose_incremental_month_revision(
                base=self.base,
                base_manifest=self.manifest,
                base_edition_sha256=sha256_file(self.base_dir / "edition.json"),
                delta=delta,
                revision=2,
            )

    def test_partial_acquisition_error_names_journal_and_source_failure(self):
        delta = self.delta()
        delta["run_status"] = "PARTIAL_SOURCE_COVERAGE"
        delta["source_checks"][0]["status"] = "FAILED"
        delta["source_checks"][0]["detail"] = "HTTP 503"
        with self.assertRaisesRegex(
            ValueError,
            "acs-central-science: PARTIAL_SOURCE_COVERAGE; source_checks: "
            "crossref=FAILED \\(HTTP 503\\)",
        ):
            compose_incremental_month_revision(
                base=self.base,
                base_manifest=self.manifest,
                base_edition_sha256=sha256_file(self.base_dir / "edition.json"),
                delta=delta,
                revision=2,
            )

    def test_batch_request_is_explicit_and_unique(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "request.json"
            path.write_text(
                json.dumps(
                    {
                        "artifact_type": "EvidenceRadar_Editions_BackfillRequest",
                        "schema_version": "1.0",
                        "request_id": "2026-08-batch-01",
                        "acquisition_start": "2026-08-15",
                        "acquisition_end": "2026-08-19",
                        "revision": 2,
                        "journals": ["acs-central-science", "clinical-nutrition"],
                    }
                ),
                encoding="utf-8",
            )
            request = load_batch_request(path)
            self.assertEqual(request["revision"], 2)
            self.assertEqual(request["journals"], ["acs-central-science", "clinical-nutrition"])

    def test_production_request_selects_requested_enabled_active_journal_slice(self):
        request = load_batch_request(Path("catalog/backfill-request.json"))
        registry = json.loads(Path("catalog/journals.json").read_text(encoding="utf-8"))
        eligible = [
            item["slug"]
            for item in registry["journals"]
            if item.get("status") == "active" and item.get("enabled", True) is not False
        ]
        base_revision = request.get("selection_base_revision")
        base_period_end = request.get("selection_base_period_end")
        if base_revision is not None or base_period_end is not None:
            base_eligible = []
            for slug in eligible:
                manifest_path = (
                    Path("editions") / slug / "2026/08/r01/manifest.json"
                )
                if not manifest_path.exists():
                    continue
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if base_revision is not None and manifest["revision"] != base_revision:
                    continue
                if base_period_end is not None and manifest["period_end"] != base_period_end:
                    continue
                base_eligible.append(slug)
            eligible = base_eligible
        offset = request["selection_offset"]
        count = request["selection_count"]
        selected = eligible[offset : offset + count]
        self.assertEqual(request["journals"], selected)
        for slug in selected:
            manifest = json.loads(
                (Path("editions") / slug / "2026/08/r01/manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(manifest["period_end"], "2026-08-14")
            self.assertEqual(manifest["revision"], 1)

    def test_workflow_has_guarded_fast_forward_when_action_prs_are_disabled(self):
        workflow = Path(".github/workflows/incremental-backfill.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("DIRECT_FAST_FORWARD_FALLBACK", workflow)
        self.assertIn('test "$(git rev-parse origin/main)" = "$BASE_SHA"', workflow)
        self.assertIn('git push origin "$HEAD_SHA:refs/heads/main"', workflow)


if __name__ == "__main__":
    unittest.main()
