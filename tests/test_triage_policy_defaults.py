import tempfile
import unittest
from pathlib import Path

from evidenceradar_editions.triage_policy_defaults import load_triage_policy


class TriagePolicyDefaultsTests(unittest.TestCase):
    def test_missing_optional_catalog_policy_uses_validated_builtin_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            policy = load_triage_policy(Path(tmp))
        self.assertEqual(
            policy["artifact_type"],
            "EvidenceRadar_Editions_PrefetchTriagePolicy",
        )
        self.assertEqual(policy["thresholds"]["fetch_candidate"], 80)
        self.assertEqual(policy["journal_soft_caps"]["TRIAGE"], 20)
        self.assertEqual(policy["reserve_index_soft_caps"]["TRIAGE"], 50)
        self.assertEqual(policy["paths"]["EVIDENCE_SYNTHESIS"]["score"], 88)


if __name__ == "__main__":
    unittest.main()
