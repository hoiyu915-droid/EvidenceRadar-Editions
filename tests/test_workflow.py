import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evidenceradar_editions import workflow


class WorkflowTests(unittest.TestCase):
    def test_main_emits_json_serializable_output_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "edition"
            run = {
                "edition_id": "jama-network-open__2026-08-13__r01",
                "publication_id": "jama-network-open__2026-08-13__r01",
                "artifacts": {"translation_request_json": "request.json"},
                "counts": {"articles": 1},
                "run_status": "COMPLETE",
            }
            manifest = {
                "files": {
                    "edition_json": {"name": "edition.json"},
                    "report_html": {"name": "report.html"},
                },
                "manifest_name": "manifest.json",
            }
            request = {"request_binding_sha256": "a" * 64}
            environment = {
                "EDITION_JOURNAL": "JAMA Network Open",
                "EDITION_ISSN": "2574-3805",
                "EDITION_SLUG": "jama-network-open",
                "EDITION_START": "2026-08-13",
                "EDITION_END": "2026-08-13",
                "EDITION_PERIOD_KIND": "day",
                "EDITION_REVISION": "1",
                "EDITION_MAX_RECORDS": "10",
                "EDITION_SOURCES": "pubmed",
                "EDITION_OUTPUT_DIR": output.as_posix(),
                "EDITION_RADAR_ROOT": "",
            }
            stdout = io.StringIO()
            with patch.dict(os.environ, environment, clear=True), patch.object(workflow, "build_run", return_value=run), patch.object(workflow, "write_bundle", return_value=manifest), patch.object(workflow, "write_translation_request", return_value=request), patch.object(workflow, "validate_bundle", return_value=[]), contextlib.redirect_stdout(stdout):
                self.assertEqual(workflow.main(), 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["bundle_dir"], output.as_posix())
            self.assertIsInstance(payload["bundle_dir"], str)


if __name__ == "__main__":
    unittest.main()
