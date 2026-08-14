import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evidenceradar_editions import workflow


class WorkflowPolicyTests(unittest.TestCase):
    def test_triage_workflow_defers_blanket_translation_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "edition"
            run = {
                "edition_id": "scientific-reports__2026-08__r01",
                "publication_id": "scientific-reports__2026-08__r01",
                "artifacts": {"translation_request_json": "request.json"},
                "counts": {"articles": 250},
                "run_status": "PARTIAL_SOURCE_COVERAGE",
                "processing": {
                    "configured_mode": "TRIAGE",
                    "effective_mode": "TRIAGE",
                    "translation_mode": "DEFERRED",
                    "applied_source_record_limit": 500,
                    "pages_record_limit": 250,
                    "policy_override_used": False,
                },
            }
            manifest = {
                "files": {
                    "edition_json": {"name": "edition.json"},
                    "report_html": {"name": "report.html"},
                },
                "manifest_name": "manifest.json",
            }
            environment = {
                "EDITION_JOURNAL_SLUG": "scientific-reports",
                "EDITION_START": "2026-08-01",
                "EDITION_END": "2026-08-14",
                "EDITION_PERIOD_KIND": "month",
                "EDITION_REVISION": "1",
                "EDITION_OUTPUT_DIR": output.as_posix(),
                "EDITION_RADAR_ROOT": "",
            }
            stdout = io.StringIO()
            with patch.dict(os.environ, environment, clear=True), patch.object(
                workflow, "build_run", return_value=run
            ), patch.object(
                workflow, "write_bundle", return_value=manifest
            ), patch.object(
                workflow, "write_translation_request"
            ) as translation_request, patch.object(
                workflow, "validate_bundle", return_value=[]
            ), contextlib.redirect_stdout(stdout):
                self.assertEqual(workflow.main(), 0)
            translation_request.assert_not_called()
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["translation_mode"], "DEFERRED")
            self.assertEqual(payload["translation_request_json"], "")
            self.assertEqual(payload["processing_mode_effective"], "TRIAGE")


if __name__ == "__main__":
    unittest.main()
