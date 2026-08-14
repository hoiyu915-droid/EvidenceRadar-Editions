import unittest

from evidenceradar_editions.cli import build_parser


class CliPolicyTests(unittest.TestCase):
    def test_policy_flags_are_exposed(self):
        parser = build_parser()
        journals = parser.parse_args(["journals", "--processing-mode", "TRIAGE"])
        self.assertEqual(journals.processing_mode, "TRIAGE")
        run = parser.parse_args(
            [
                "run",
                "--journal-slug",
                "scientific-reports",
                "--start",
                "2026-08-01",
                "--end",
                "2026-08-31",
                "--output-dir",
                "out",
                "--override-processing-policy",
            ]
        )
        self.assertTrue(run.override_processing_policy)


if __name__ == "__main__":
    unittest.main()
