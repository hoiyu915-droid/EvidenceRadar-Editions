import unittest
from datetime import date

from evidenceradar_editions.dedup import deduplicate_articles, journal_matches
from evidenceradar_editions.models import Article, EditionSpec, SourceRecord
from evidenceradar_editions.naming import build_identity, infer_period_kind
from evidenceradar_editions.utils import normalize_doi, normalize_issn, slugify


class CoreTests(unittest.TestCase):
    def test_spec_and_slug_boundary(self):
        spec = EditionSpec(
            "JAMA Network Open",
            date(2026, 8, 1),
            date(2026, 8, 31),
            "jama-network-open",
            period_kind="month",
        )
        self.assertEqual(spec.slug, "jama-network-open")
        for bad in ("../escape", "Bad", "a/b", "-bad", "bad-"):
            with self.assertRaises(ValueError):
                EditionSpec("J", date(2026, 8, 1), date(2026, 8, 2), bad)

    def test_period_identity_and_filename(self):
        identity = build_identity(
            slug="jama-network-open",
            start=date(2026, 8, 1),
            end=date(2026, 8, 31),
            period_kind_requested="month",
            revision=2,
        )
        self.assertEqual(identity.period_key, "2026-08")
        self.assertEqual(identity.publication_id, "jama-network-open__2026-08__r02")
        self.assertIn("EvidenceRadar_Editions__jama-network-open__2026-08__r02", identity.artifact_stem)
        self.assertEqual(
            infer_period_kind(date(2026, 8, 10), date(2026, 8, 16)), "week"
        )

    def test_normalization(self):
        self.assertEqual(normalize_doi("https://doi.org/10.1000/ABC."), "10.1000/abc")
        self.assertEqual(normalize_issn("25743805"), "2574-3805")
        self.assertEqual(slugify("Sports Medicine"), "sports-medicine")

    def test_dedup_merges_provider_identity(self):
        a = Article(
            "Same title",
            "JAMA Network Open",
            date(2026, 8, 3),
            doi="10.1000/X",
            pmid="1",
            source_records=[SourceRecord("pubmed", "1")],
        )
        b = Article(
            "Same title",
            "JAMA Network Open",
            date(2026, 8, 3),
            doi="https://doi.org/10.1000/x",
            pmcid="PMC2",
            source_records=[SourceRecord("europe_pmc", "PMC2")],
        )
        merged = deduplicate_articles([a, b])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].pmid, "1")
        self.assertEqual(merged[0].pmcid, "PMC2")
        self.assertEqual(
            {record.source for record in merged[0].source_records},
            {"pubmed", "europe_pmc"},
        )

    def test_dedup_merges_transitive_identity_chain(self):
        doi_only = Article(
            "One", "JAMA Network Open", date(2026, 8, 3),
            doi="10.1000/x", source_records=[SourceRecord("crossref", "10.1000/x")],
        )
        pmid_only = Article(
            "Two", "JAMA Network Open", date(2026, 8, 3),
            pmid="99", source_records=[SourceRecord("pubmed", "99")],
        )
        bridge = Article(
            "Bridge", "JAMA Network Open", date(2026, 8, 3),
            doi="10.1000/x", pmid="99", source_records=[SourceRecord("europe_pmc", "99")],
        )
        merged = deduplicate_articles([doi_only, pmid_only, bridge])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].doi, "10.1000/x")
        self.assertEqual(merged[0].pmid, "99")

    def test_journal_match_by_name_or_issn(self):
        article = Article(
            "T",
            "JAMA Network Open",
            date(2026, 8, 3),
            issns=["2574-3805"],
        )
        self.assertTrue(
            journal_matches(article, journal="JAMA Network Open", issn=None)
        )
        self.assertTrue(journal_matches(article, journal="Other", issn="25743805"))
