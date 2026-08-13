import unittest
from datetime import date
from evidenceradar_editions.adapters import CrossrefAdapter, EuropePmcAdapter, PubMedAdapter
from evidenceradar_editions.models import EditionSpec

class QueryTests(unittest.TestCase):
    def test_period_queries(self):
        spec = EditionSpec("JAMA Network Open", date(2026, 8, 1), date(2026, 8, 31), "jama-network-open", issn="2574-3805")
        self.assertIn("2026/08/01", PubMedAdapter.query(spec))
        self.assertIn("FIRST_PDATE", EuropePmcAdapter.query(spec))
        self.assertIn("2026-08-31", CrossrefAdapter.query(spec))
