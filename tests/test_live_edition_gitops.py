import json
import unittest
from pathlib import Path


class LiveEditionGitOpsTests(unittest.TestCase):
    def test_request_is_scoped_and_safe(self):
        root = Path(__file__).resolve().parents[1]
        request = json.loads((root / "catalog" / "live-edition-request.json").read_text(encoding="utf-8"))
        self.assertEqual(request["artifact_type"], "EvidenceRadar_Editions_LiveEditionRequest")
        self.assertEqual(request["journal_slug"], "jama-network-open")
        self.assertEqual(request["start"], "2026-08-14")
        self.assertEqual(request["end"], "2026-08-14")
        self.assertEqual(request["period_kind"], "day")
        self.assertEqual(request["revision"], 1)
        self.assertFalse(request["allow_planned"])
        self.assertFalse(request["override_processing_policy"])

    def test_live_workflow_supports_push_trigger_and_guarded_publication(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / ".github" / "workflows" / "live-edition.yml").read_text(encoding="utf-8")
        for token in (
            'catalog/live-edition-request.json',
            'Resolve live Edition request',
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
        text = (root / ".github" / "workflows" / "live-edition.yml").read_text(encoding="utf-8")
        self.assertIn('test "$(git rev-parse origin/main)" = "$BASE_SHA"', text)
        self.assertIn('main moved during live-edition acquisition; refusing stale publication', text)
        self.assertIn('Refusing unrelated staged path', text)


if __name__ == "__main__":
    unittest.main()
