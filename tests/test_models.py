from __future__ import annotations

from datetime import date

from evidenceradar_editions.models import Article, Collection, normalize_doi, normalize_issn
from evidenceradar_editions.pipeline import deduplicate_articles, filter_scope


def test_normalizers() -> None:
    assert normalize_doi("https://doi.org/10.1001/ABC.123") == "10.1001/abc.123"
    assert normalize_issn("25743805") == "2574-3805"


def test_collection_matches_issn_and_alias() -> None:
    collection = Collection.from_mapping(
        {
            "id": "jama-network-open",
            "name": "JAMA Network Open",
            "aliases": ["JAMA Netw Open"],
            "issns": ["2574-3805"],
        }
    )
    assert collection.matches(journal="something", issns=["2574-3805"])
    assert collection.matches(journal="JAMA Netw Open", issns=[])
    assert not collection.matches(journal="Another Journal", issns=["1111-2222"])


def test_deduplicate_merges_cross_source_identity() -> None:
    left = Article(
        title="A study",
        journal="JAMA Network Open",
        publication_date="2026-08-01",
        doi="10.1001/example",
        pmid="1",
        sources=["pubmed"],
    )
    right = Article(
        title="A study",
        journal="JAMA Network Open",
        publication_date="2026-08-01",
        doi="https://doi.org/10.1001/example",
        pmcid="PMC1",
        abstract="A longer abstract",
        sources=["europe_pmc"],
        oa_status="YES",
    )
    merged = deduplicate_articles([left, right])
    assert len(merged) == 1
    assert merged[0].pmid == "1"
    assert merged[0].pmcid == "PMC1"
    assert merged[0].sources == ["pubmed", "europe_pmc"]
    assert merged[0].oa_status == "YES"


def test_scope_filter_rejects_wrong_journal_and_date() -> None:
    collection = Collection.from_mapping(
        {"id": "target", "name": "Target Journal", "issns": ["1234-5678"]}
    )
    articles = [
        Article("A", "Target Journal", "2026-08-10", issns=["1234-5678"]),
        Article("B", "Wrong", "2026-08-10", issns=["1111-2222"]),
        Article("C", "Target Journal", "2026-09-01", issns=["1234-5678"]),
    ]
    accepted, counts = filter_scope(
        articles,
        collection=collection,
        start=date(2026, 8, 1),
        end=date(2026, 8, 31),
    )
    assert [item.title for item in accepted] == ["A"]
    assert counts["wrong_collection"] == 1
    assert counts["outside_period"] == 1


def test_month_precision_requires_period_to_contain_whole_month() -> None:
    collection = Collection.from_mapping(
        {"id": "target", "name": "Target Journal", "issns": ["1234-5678"]}
    )
    article = Article(
        "Month-only date",
        "Target Journal",
        "2026-08-01",
        publication_date_precision="MONTH",
        issns=["1234-5678"],
    )
    monthly, monthly_counts = filter_scope(
        [article],
        collection=collection,
        start=date(2026, 8, 1),
        end=date(2026, 8, 31),
    )
    weekly, weekly_counts = filter_scope(
        [article],
        collection=collection,
        start=date(2026, 8, 10),
        end=date(2026, 8, 16),
    )
    assert len(monthly) == 1
    assert monthly_counts["insufficient_date_precision"] == 0
    assert weekly == []
    assert weekly_counts["insufficient_date_precision"] == 1


def test_invalid_day_token_keeps_month_precision() -> None:
    from evidenceradar_editions.sources import _date_value

    value, precision = _date_value("2026", "Aug", "Summer")
    assert value == "2026-08-01"
    assert precision == "MONTH"
