import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evidenceradar_editions import workflow
from evidenceradar_editions import workflow_v2


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

    def test_live_workflow_resolves_cambridge_provider_journal(self):
        environment = {
            "EDITION_PROVIDER": "cambridge",
            "EDITION_JOURNAL_SLUG": "cambridge-forum-on-ai-culture-and-society",
            "EDITION_START": "2026-08-01",
            "EDITION_END": "2026-08-16",
            "EDITION_PERIOD_KIND": "month",
            "EDITION_REVISION": "1",
            "EDITION_CATALOG_ROOT": "catalog",
        }
        provider_record = {
            "name": "Cambridge Forum on AI: Culture and Society",
            "slug": "cambridge-forum-on-ai-culture-and-society",
            "issn": "",
            "sources": ["cambridge_core"],
            "url": "https://www.cambridge.org/core/journals/cambridge-forum-on-ai-culture-and-society",
        }
        with patch.dict(os.environ, environment, clear=True), patch.object(
            workflow_v2, "CambridgeCoreAdapter"
        ) as adapter_class, patch.object(workflow_v2, "HttpClient"):
            adapter_class.return_value.resolve_journal.return_value = provider_record
            spec, _policy, override, provider_context = workflow_v2._resolve_spec_and_policy()

        adapter_class.return_value.resolve_journal.assert_called_once_with(
            "cambridge-forum-on-ai-culture-and-society"
        )
        self.assertEqual(spec.journal, "Cambridge Forum on AI: Culture and Society")
        self.assertEqual(spec.slug, "cambridge-forum-on-ai-culture-and-society")
        self.assertEqual(spec.sources, ("cambridge_core",))
        self.assertEqual(spec.start_date.isoformat(), "2026-08-01")
        self.assertEqual(spec.end_date.isoformat(), "2026-08-16")
        self.assertFalse(override)
        self.assertEqual(provider_context["provider"], "cambridge")
        self.assertEqual(provider_context["provider_journal_url"], provider_record["url"])


if __name__ == "__main__":
    unittest.main()
