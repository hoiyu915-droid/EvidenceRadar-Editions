from __future__ import annotations

import json
from pathlib import Path

from evidenceradar_editions.sources import (
    parse_crossref_json,
    parse_europe_pmc_json,
    parse_pubmed_xml,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_pubmed_fixture() -> None:
    articles = parse_pubmed_xml((FIXTURES / "pubmed.xml").read_text(encoding="utf-8"))
    assert len(articles) == 1
    article = articles[0]
    assert article.pmid == "12345678"
    assert article.doi == "10.1001/jamanetworkopen.2026.1234"
    assert article.publication_date == "2026-08-12"
    assert article.publication_date_precision == "DAY"
    assert article.study_designs == ["randomized_controlled_trial"]


def test_parse_europe_pmc_fixture() -> None:
    payload = json.loads((FIXTURES / "europe_pmc.json").read_text(encoding="utf-8"))
    articles = parse_europe_pmc_json(payload)
    assert len(articles) == 2
    assert articles[0].pmcid == "PMC1234567"
    assert articles[0].oa_status == "YES"
    assert "systematic_review" in articles[1].study_designs


def test_parse_crossref_fixture() -> None:
    payload = json.loads((FIXTURES / "crossref.json").read_text(encoding="utf-8"))
    articles = parse_crossref_json(payload)
    assert len(articles) == 3
    assert articles[0].publication_date == "2026-08-12"
    assert articles[0].journal == "JAMA Network Open"


def test_crossref_created_timestamp_is_not_publication_date() -> None:
    payload = {
        "message": {
            "items": [
                {
                    "title": ["Created is not published"],
                    "container-title": ["JAMA Network Open"],
                    "ISSN": ["2574-3805"],
                    "DOI": "10.1001/created-only",
                    "created": {"date-time": "2026-08-12T00:00:00Z"},
                }
            ]
        }
    }
    article = parse_crossref_json(payload)[0]
    assert article.publication_date == ""
    assert article.publication_date_precision == "UNKNOWN"


def test_date_parser_does_not_promote_nonnumeric_day_to_day_precision() -> None:
    from evidenceradar_editions.sources import _date_value

    assert _date_value("2026", "Aug", "Summer") == ("2026-08-01", "MONTH")
