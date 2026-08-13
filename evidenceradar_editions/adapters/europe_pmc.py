from __future__ import annotations

from typing import Any

from ..http import HttpClient
from ..models import AdapterResult, Article, EditionSpec, SourceCheck, SourceRecord
from ..utils import (
    clean_text,
    normalize_doi,
    normalize_issn,
    parse_loose_date_with_precision,
)

ENDPOINT = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


class EuropePmcAdapter:
    source = "europe_pmc"

    def __init__(self, client: HttpClient) -> None:
        self.client = client

    @staticmethod
    def query(spec: EditionSpec) -> str:
        journal_name = spec.journal.replace('"', r'\"')
        return (
            f'JOURNAL:"{journal_name}" AND '
            f"FIRST_PDATE:[{spec.start_date.isoformat()} TO {spec.end_date.isoformat()}]"
        )

    @staticmethod
    def _article(raw: dict[str, Any]) -> Article | None:
        title = clean_text(raw.get("title"))
        journal = clean_text(raw.get("journalTitle"))
        parsed = parse_loose_date_with_precision(
            str(
                raw.get("firstPublicationDate")
                or raw.get("electronicPublicationDate")
                or raw.get("dateOfPublication")
                or ""
            )
        )
        if not title or not journal or parsed is None:
            return None
        published, precision = parsed
        pmid = clean_text(raw.get("pmid") or raw.get("id")) or None
        pmcid = clean_text(raw.get("pmcid")).upper() or None
        doi = normalize_doi(str(raw.get("doi") or ""))
        issns: list[str] = []
        normalized_issn = normalize_issn(str(raw.get("journalIssn") or ""))
        if normalized_issn:
            issns.append(normalized_issn)
        author_string = clean_text(raw.get("authorString"))
        authors = (
            [part.strip() for part in author_string.split(",") if part.strip()]
            if author_string
            else []
        )
        urls: list[str] = []
        if doi:
            urls.append(f"https://doi.org/{doi}")
        if pmcid:
            urls.append(f"https://europepmc.org/article/PMC/{pmcid}")
        elif pmid:
            urls.append(f"https://europepmc.org/article/MED/{pmid}")
        return Article(
            title=title,
            journal=journal,
            publication_date=published,
            publication_date_precision=precision,
            doi=doi,
            pmid=pmid,
            pmcid=pmcid,
            issns=issns,
            authors=authors,
            article_type=clean_text(raw.get("pubType")) or None,
            urls=urls,
            source_records=[
                SourceRecord(
                    "europe_pmc", pmcid or pmid or doi, urls[-1] if urls else None
                )
            ],
        )

    def fetch(self, spec: EditionSpec) -> AdapterResult:
        query = self.query(spec)
        try:
            articles: list[Article] = []
            returned_count = 0
            total_available: int | None = None
            cursor: str | None = "*"
            remaining = spec.max_records
            while remaining > 0 and cursor:
                data = self.client.get_json(
                    ENDPOINT,
                    params={
                        "query": query,
                        "format": "json",
                        "resultType": "lite",
                        "pageSize": min(remaining, 1000),
                        "cursorMark": cursor,
                    },
                )
                if total_available is None:
                    try:
                        total_available = int(data.get("hitCount"))
                    except (TypeError, ValueError):
                        total_available = None
                raw_results = ((data.get("resultList") or {}).get("result") or [])
                if not isinstance(raw_results, list):
                    raise ValueError("Europe PMC results must be an array")
                if not raw_results:
                    break
                for raw in raw_results:
                    if not isinstance(raw, dict):
                        continue
                    article = self._article(raw)
                    if article is not None:
                        articles.append(article)
                consumed = len(raw_results)
                returned_count += consumed
                remaining -= consumed
                next_cursor = str(data.get("nextCursorMark") or "")
                if not next_cursor or next_cursor == cursor:
                    break
                cursor = next_cursor
            truncated = bool(
                total_available is not None and total_available > returned_count
            )
            if returned_count == 0:
                status = "NO_RESULTS"
            elif truncated:
                status = "PARTIAL"
            else:
                status = "SUCCESS"
            detail = (
                f"source reported {total_available} records; capped at {returned_count}"
                if truncated
                else None
            )
            return AdapterResult(
                articles,
                SourceCheck(
                    source=self.source,
                    status=status,
                    query=query,
                    returned_count=returned_count,
                    total_available=total_available,
                    truncated=truncated,
                    detail=detail,
                ),
            )
        except Exception as exc:
            return AdapterResult(
                [],
                SourceCheck(
                    source=self.source,
                    status="FAILED",
                    query=query,
                    detail=f"{type(exc).__name__}: {exc}",
                ),
            )
