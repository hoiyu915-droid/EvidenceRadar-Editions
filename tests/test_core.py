import unittest
from datetime import date

from evidenceradar_editions.dedup import deduplicate_articles, journal_matches
from evidenceradar_editions.models import Article, EditionSpec, SourceRecord
from evidenceradar_editions.utils import normalize_doi, normalize_issn, slugify

class CoreTests(unittest.TestCase):
    def test_spec_and_slug_boundary(self):
        spec = EditionSpec("JAMA Network Open", date(2026, 8, 1), date(2026, 8, 31), "jama-network-open")
        self.assertEqual(spec.slug, "jama-network-open")
        for bad in ("../escape", "Bad", "a/b", "-bad", "bad-"):
            with self.assertRaises(ValueError):
                EditionSpec("J", date(2026, 8, 1), date(2026, 8, 2), bad)

    def test_normalization(self):
        self.assertEqual(normalize_doi("https://doi.org/10.1000/ABC."), "10.1000/abc")
        self.assertEqual(normalize_issn("25743805"), "2574-3805")
        self.assertEqual(slugify("Sports Medicine"), "sports-medicine")

    def test_dedup_merges_provider_identity(self):
        a = Article("Same title", "JAMA Network Open", date(2026, 8, 3), doi="10.1000/X", pmid="1", source_records=[SourceRecord("pubmed", "1")])
        b = Article("Same title", "JAMA Network Open", date(2026, 8, 3), doi="https://doi.org/10.1000/x", pmcid="PMC2", source_records=[SourceRecord("europe_pmc", "PMC2")])
        merged = deduplicate_articles([a, b])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].pmid, "1")
        self.assertEqual(merged[0].pmcid, "PMC2")
        self.assertEqual({r.source for r in merged[0].source_records}, {"pubmed", "europe_pmc"})

    def test_journal_match_by_name_or_issn(self):
        article = Article("T", "JAMA Network Open", date(2026, 8, 3), issns=["2574-3805"])
        self.assertTrue(journal_matches(article, journal="JAMA Network Open", issn=None))
        self.assertTrue(journal_matches(article, journal="Other", issn="25743805"))
