import copy
import tempfile
import unittest
from pathlib import Path

from evidenceradar_editions.bundle import HTML_NAME, JSON_NAME, MANIFEST_NAME, write_bundle
from evidenceradar_editions.validate import validate_bundle

RUN = {"schema_version":"1.0","artifact_type":"EvidenceRadar_Edition","edition_id":"jama__2026-08","retrieved_at":"2026-08-14T00:00:00Z","data_semantics":"current_source_reconstruction_of_historical_publication_window","scope":{"journal":"JAMA Network Open","issn":"2574-3805","slug":"jama","start_date":"2026-08-01","end_date":"2026-08-31","sources":["pubmed"],"max_records":500},"upstream_radar":{"repository":"hoiyu915-droid/EvidenceRadar","commit":"abc","control_plane":"config/radar_master.json","matched_source_ids":[],"config_sha256":"x","uses_radar_output_artifacts":False},"source_checks":[],"counts":{"articles":0,"by_source":{},"by_article_type":{}},"articles":[]}

class DeliveryTests(unittest.TestCase):
    def test_three_file_bundle_validates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_bundle(copy.deepcopy(RUN), root)
            self.assertTrue((root / JSON_NAME).is_file())
            self.assertTrue((root / HTML_NAME).is_file())
            self.assertTrue((root / MANIFEST_NAME).is_file())
            self.assertEqual(validate_bundle(root), [])

    def test_radar_artifact_dependency_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = copy.deepcopy(RUN)
            run["upstream_radar"]["uses_radar_output_artifacts"] = True
            write_bundle(run, root)
            self.assertTrue(validate_bundle(root))
