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
JOURNAL = "Chemical Science"
ISSN = "2041-6539"
DOI_PREFIX = "10.1039/"
PUBLISHER = "Royal Society of Chemistry (RSC)"
SURROGATE_SOURCE = "rsc_first_published_surrogate_v1"
SURROGATE_VALIDATION = (
    "Chemical Science only: Crossref DOI created day is used as an explicit "
    "surrogate for RSC First published after 21/21 exact-day matches against "
    "official RSC records; generic Crossref publication-date semantics are unchanged"
)
ISSUE_FURNITURE_TITLES = {
    "front cover",
    "inside front cover",
    "back cover",
    "inside back cover",
    "contents list",
}


class RscChemicalScienceAdapter:
    """Fail-closed Chemical Science adapter for RSC's current metadata shape.

    RSC article/RSS endpoints are not reliably reachable from GitHub-hosted
    runners after the 2026 platform migration. Crossref's normal publication
    fields only carry year precision for current Chemical Science deposits.
    For this journal alone, the Crossref DOI creation day is accepted as a
    *surrogate* after a separately retained 21-record first-party validation.
    """

    source = "rsc_chemical_science"

    def __init__(self, client: HttpClient) -> None:
        self.client = client

    @staticmethod
    def query(spec: EditionSpec) -> str:
        return (
            f"journal={JOURNAL}; issn={ISSN}; "
            f"validated-created-surrogate={spec.start_date.isoformat()}..{spec.end_date.isoformat()}"
        )

    @staticmethod
    def _scope_error(spec: EditionSpec) -> str | None:
        if clean_text(spec.journal).casefold() != JOURNAL.casefold():
            return f"adapter is restricted to {JOURNAL!r}"
        if normalize_issn(str(spec.issn or "")) != ISSN:
            return f"adapter requires ISSN {ISSN}"
        return None

    @staticmethod
    def _title(raw: dict[str, Any]) -> str:
        titles = raw.get("title") or []
        return clean_text(titles[0] if isinstance(titles, list) and titles else titles)

    @classmethod
    def _is_issue_furniture(cls, raw: dict[str, Any]) -> bool:
        return cls._title(raw).casefold() in ISSUE_FURNITURE_TITLES

    @staticmethod
    def _created_day(raw: dict[str, Any]) -> tuple[Any, str] | None:
        block = raw.get("created") or {}
        parts = block.get("date-parts") if isinstance(block, dict) else None
        if not isinstance(parts, list) or not parts:
            return None
        parsed = date_from_parts_with_precision(parts[0])
        if parsed is None or parsed[1] != "DAY":
            return None
        return parsed

    @classmethod
    def _article(cls, raw: dict[str, Any]) -> Article | None:
        title = cls._title(raw)
        journals = raw.get("container-title") or []
        journal = clean_text(
            journals[0] if isinstance(journals, list) and journals else journals
        )
        if not title or journal.casefold() != JOURNAL.casefold():
            return None
        if title.casefold() in ISSUE_FURNITURE_TITLES:
            return None

        doi = normalize_doi(str(raw.get("DOI") or ""))
        if not doi or not doi.casefold().startswith(DOI_PREFIX):
            return None
        issns = [
            value
            for value in (
                normalize_issn(str(candidate))
                for candidate in (raw.get("ISSN") or [])
            )
            if value
        ]
        if ISSN not in issns:
            return None
        if clean_text(raw.get("publisher")) != PUBLISHER:
            return None
        if clean_text(raw.get("prefix")) != DOI_PREFIX.rstrip("/"):
            return None
        if clean_text(raw.get("type")) != "journal-article":
            return None

        created = cls._created_day(raw)
        if created is None:
            return None
        publication_date, precision = created

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
        if not url_value:
            url_value = f"https://doi.org/{doi}"
        article_type = (
            "Correction" if title.casefold().startswith("correction:") else "Journal Article"
        )
        return Article(
            title=title,
            journal=JOURNAL,
            publication_date=publication_date,
            publication_date_precision=precision,
            doi=doi,
            issns=issns,
            authors=authors,
            article_type=article_type,
            urls=[url_value],
            source_records=[
                SourceRecord("crossref", doi, url_value),
                SourceRecord(
                    SURROGATE_SOURCE,
                    f"{doi}|crossref-created:{publication_date.isoformat()}",
                    None,
                ),
            ],
        )

    def fetch(self, spec: EditionSpec) -> AdapterResult:
        query = self.query(spec)
        scope_error = self._scope_error(spec)
        if scope_error:
            return AdapterResult(
                [],
                SourceCheck(
                    source=self.source,
                    status="FAILED",
                    query=query,
                    detail=scope_error,
                ),
            )

        base_params: dict[str, Any] = {
            "filter": ",".join(
                [
                    f"from-created-date:{spec.start_date.isoformat()}",
                    f"until-created-date:{spec.end_date.isoformat()}",
                    f"issn:{ISSN}",
                    "type:journal-article",
                ]
            ),
            "query.container-title": JOURNAL,
            "select": (
                "DOI,title,container-title,created,ISSN,author,URL,type,publisher,prefix"
            ),
        }
        try:
            articles: list[Article] = []
            returned_count = 0
            total_available: int | None = None
            remaining = spec.max_records
            cursor: str | None = "*"
            furniture_excluded = 0
            validation_rejected = 0
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
                        validation_rejected += 1
                        continue
                    if self._is_issue_furniture(raw):
                        furniture_excluded += 1
                        continue
                    article = self._article(raw)
                    if article is None:
                        validation_rejected += 1
                    else:
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
            elif truncated or validation_rejected:
                status = "PARTIAL"
            else:
                status = "SUCCESS"
            detail = (
                f"{SURROGATE_VALIDATION}; "
                f"source records={returned_count}; accepted scholarly records={len(articles)}; "
                f"issue furniture excluded={furniture_excluded}; "
                f"unexpected records rejected={validation_rejected}"
            )
            if truncated:
                detail += (
                    f"; source reported {total_available} records and max_records capped retrieval"
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
