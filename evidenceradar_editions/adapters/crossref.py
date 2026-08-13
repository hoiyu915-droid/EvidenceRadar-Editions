from __future__ import annotations

from typing import Any

from ..http import HttpClient
from ..models import AdapterResult, Article, EditionSpec, SourceCheck, SourceRecord
from ..utils import (
    clean_text,
    date_from_parts_with_precision,
    normalize_doi,
    normalize_issn,
    safe_http_metadata_url,
)

ENDPOINT = "https://api.crossref.org/works"


class CrossrefAdapter:
    source = "crossref"

    def __init__(self, client: HttpClient) -> None:
        self.client = client

    @staticmethod
    def query(spec: EditionSpec) -> str:
        return (
            f"container={spec.journal}; "
            f"publication={spec.start_date.isoformat()}..{spec.end_date.isoformat()}"
        )

    @staticmethod
    def _article(raw: dict[str, Any]) -> Article | None:
        titles = raw.get("title") or []
        journals = raw.get("container-title") or []
        title = clean_text(titles[0] if isinstance(titles, list) and titles else titles)
        journal = clean_text(
            journals[0] if isinstance(journals, list) and journals else journals
        )
        published: tuple[Any, str] | None = None
        for key in ("published-online", "published-print", "published", "issued"):
            block = raw.get(key) or {}
            parts = block.get("date-parts") if isinstance(block, dict) else None
            if isinstance(parts, list) and parts:
                published = date_from_parts_with_precision(parts[0])
            if published:
                break
        if not title or not journal or published is None:
            return None
        publication_date, precision = published
        doi = normalize_doi(str(raw.get("DOI") or ""))
        issns = [
            value
            for value in (
                normalize_issn(str(candidate))
                for candidate in (raw.get("ISSN") or [])
            )
            if value
        ]
        authors: list[str] = []
        for person in raw.get("author") or []:
            if not isinstance(person, dict):
                continue
            name = clean_text(
                " ".join(
                    str(person.get(key) or "").strip()
                    for key in ("given", "family")
                )
            )
            if name:
                authors.append(name)
        url_value = safe_http_metadata_url(str(raw.get("URL") or ""))
        if not url_value and doi:
            url_value = f"https://doi.org/{doi}"
        return Article(
            title=title,
            journal=journal,
            publication_date=publication_date,
            publication_date_precision=precision,
            doi=doi,
            issns=issns,
            authors=authors,
            article_type=clean_text(raw.get("type")) or None,
            urls=[url_value] if url_value else [],
            source_records=[SourceRecord("crossref", doi, url_value)],
        )

    def fetch(self, spec: EditionSpec) -> AdapterResult:
        query = self.query(spec)
        filters = [
            f"from-pub-date:{spec.start_date.isoformat()}",
            f"until-pub-date:{spec.end_date.isoformat()}",
            "type:journal-article",
        ]
        if spec.issn:
            filters.append(f"issn:{spec.issn}")
        base_params: dict[str, Any] = {
            "filter": ",".join(filters),
            "query.container-title": spec.journal,
            "select": (
                "DOI,title,container-title,published-online,published-print,"
                "published,issued,ISSN,author,URL,type"
            ),
        }
        try:
            articles: list[Article] = []
            returned_count = 0
            total_available: int | None = None
            remaining = spec.max_records
            cursor: str | None = "*"
            while remaining > 0 and cursor:
                params = dict(base_params)
                params["rows"] = min(remaining, 1000)
                params["cursor"] = cursor
                data = self.client.get_json(ENDPOINT, params=params)
                message = data.get("message") or {}
                if not isinstance(message, dict):
                    raise ValueError("Crossref message must be an object")
                if total_available is None:
                    try:
                        total_available = int(message.get("total-results"))
                    except (TypeError, ValueError):
                        total_available = None
                items = message.get("items") or []
                if not isinstance(items, list):
                    raise ValueError("Crossref items must be an array")
                if not items:
                    break
                for raw in items:
                    if not isinstance(raw, dict):
                        continue
                    article = self._article(raw)
                    if article is not None:
                        articles.append(article)
                consumed = len(items)
                returned_count += consumed
                remaining -= consumed
                next_cursor = str(message.get("next-cursor") or "")
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
