import json
import unittest
from datetime import date
from pathlib import Path


class LiveEditionGitOpsTests(unittest.TestCase):
    def test_request_is_scoped_and_safe(self):
        root = Path(__file__).resolve().parents[1]
        request = json.loads(
            (root / "catalog" / "live-edition-request.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            request["artifact_type"], "EvidenceRadar_Editions_LiveEditionRequest"
        )
        self.assertTrue(str(request.get("journal_slug") or "").strip())
        self.assertIn(str(request.get("provider") or "").strip().casefold(), {"", "cambridge"})
        start = date.fromisoformat(str(request["start"]))
        end = date.fromisoformat(str(request["end"]))
        self.assertLessEqual(start, end)
        self.assertIn(request["period_kind"], {"auto", "day", "week", "month", "range"})
        self.assertGreaterEqual(int(request["revision"]), 1)
        max_records = str(request.get("max_records") or "").strip()
        if max_records:
            self.assertGreaterEqual(int(max_records), 1)
        self.assertIsInstance(request["allow_planned"], bool)
        self.assertIsInstance(request["override_processing_policy"], bool)
        for key in ("request_id", "provider", "journal_slug", "start", "end", "sources"):
            value = str(request.get(key) or "")
            self.assertNotIn("\n", value)
            self.assertNotIn("\r", value)

    def test_live_workflow_supports_push_trigger_and_guarded_publication(self):
        root = Path(__file__).resolve().parents[1]
        text = (
            root / ".github" / "workflows" / "live-edition.yml"
        ).read_text(encoding="utf-8")
        for token in (
            'catalog/live-edition-request.json',
            'Resolve live Edition request',
            'EDITION_PROVIDER',
            'python -m evidenceradar_editions publish',
            'gh pr create',
            '/pulls/$pr_number/merge',
            'DIRECT_FAST_FORWARD_FALLBACK',
            'git push origin "$HEAD_SHA:refs/heads/main"',
            'actions/workflows/pages.yml/dispatches',
            'gh run watch',
        ):
            self.assertIn(token, text)

    def test_direct_fallback_is_guarded_by_exact_base_sha(self):
        root = Path(__file__).resolve().parents[1]
        text = (
            root / ".github" / "workflows" / "live-edition.yml"
        ).read_text(encoding="utf-8")
        self.assertIn('test "$(git rev-parse origin/main)" = "$BASE_SHA"', text)
        self.assertIn(
            'main moved during live-edition acquisition; refusing stale publication', text
        )
        self.assertIn('Refusing unrelated staged path', text)


if __name__ == "__main__":
    unittest.main()
