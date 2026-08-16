from __future__ import annotations

import re
from datetime import date, datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit

from ..http import HttpClient
from ..models import AdapterResult, Article, EditionSpec, SourceCheck, SourceRecord
from ..utils import clean_text, normalize_issn, safe_http_metadata_url

BASE_URL = "https://www.cambridge.org"
OA_JOURNAL_LISTING = f"{BASE_URL}/core/publications/open-access/listing"
OA_JOURNAL_LISTING_PARAMS = {
    "aggs[productTypes][filters]": "JOURNAL",
    "sort": "titleSort:asc",
    "statuses": "PUBLISHED",
}
MAX_CATALOG_PAGES = 50
MAX_ARTICLE_PAGES = 500
_PAGE_RE = re.compile(r"\bPage\s+(\d+)\s+of\s+(\d+)\b", re.I)
_JOURNAL_PATH_RE = re.compile(r"^/core/journals/([a-z0-9-]+)/?$", re.I)
_PUBLISHED_RE = re.compile(
    r"Published\s+online\s+by\s+Cambridge\s+University\s+Press:\s*"
    r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})",
    re.I,
)
_PRINT_ISSN_RE = re.compile(r"(\d{4}-[0-9Xx]{4})\s*\(Print\)")
_ONLINE_ISSN_RE = re.compile(r"(\d{4}-[0-9Xx]{4})\s*\(Online\)")
_ANY_ISSN_RE = re.compile(r"\bISSN:\s*(\d{4}-[0-9Xx]{4})")


class _JournalHomeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() == "title":
            self._in_title = True

    def handle_data(self, data: str) -> None:
        text = clean_text(data)
        if not text:
            return
        self.parts.append(text)
        if self._in_title:
            self.title_parts.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "title":
            self._in_title = False

    @property
    def text(self) -> str:
        return " ".join(self.parts)

    @property
    def title(self) -> str:
        return clean_text(" ".join(self.title_parts))


class _JournalListingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.journals: list[dict[str, Any]] = []
        self._capture: tuple[str, str] | None = None
        self._anchor_parts: list[str] = []
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "a":
            return
        href = next((value for key, value in attrs if key.casefold() == "href"), None)
        if not href:
            return
        path = urlsplit(href).path
        match = _JOURNAL_PATH_RE.fullmatch(path)
        if match:
            self._capture = (match.group(1).casefold(), href)
            self._anchor_parts = []

    def handle_data(self, data: str) -> None:
        text = clean_text(data)
        if not text:
            return
        self._text_parts.append(text)
        if self._capture is not None:
            self._anchor_parts.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() != "a" or self._capture is None:
            return
        slug, href = self._capture
        name = clean_text(" ".join(self._anchor_parts))
        if name:
            self.journals.append(
                {
                    "provider": "cambridge",
                    "publisher": "Cambridge University Press",
                    "name": name,
                    "slug": slug,
                    "oa": "fully_oa",
                    "status": "active",
                    "sources": ["cambridge_core"],
                    "url": urljoin(BASE_URL, href),
                }
            )
        self._capture = None
        self._anchor_parts = []

    @property
    def page_count(self) -> int | None:
        match = _PAGE_RE.search(" ".join(self._text_parts))
        return int(match.group(2)) if match else None


class _ArticleListingParser(HTMLParser):
    def __init__(self, journal_slug: str) -> None:
        super().__init__(convert_charrefs=True)
        self.journal_slug = journal_slug.casefold()
        self.records: list[dict[str, Any]] = []
        self.unparsed_records = 0
        self._current_href: str | None = None
        self._title_parts: list[str] = []
        self._context_parts: list[str] = []
        self._capture_title = False
        self._text_parts: list[str] = []

    def _is_article_href(self, href: str) -> bool:
        path = urlsplit(href).path
        prefix = f"/core/journals/{self.journal_slug}/article/"
        return path.casefold().startswith(prefix)

    @staticmethod
    def _parse_date(text: str) -> date | None:
        match = _PUBLISHED_RE.search(text)
        if not match:
            return None
        raw = match.group(1)
        for fmt in ("%d %B %Y", "%d %b %Y"):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                continue
        return None

    def _finalize_current(self) -> None:
        if self._current_href is None:
            return
        title = clean_text(" ".join(self._title_parts))
        context = clean_text(" ".join(self._context_parts))
        published = self._parse_date(context)
        if title and published is not None:
            self.records.append(
                {
                    "title": title,
                    "publication_date": published,
                    "url": urljoin(BASE_URL, self._current_href),
                    "source_id": urlsplit(self._current_href).path,
                }
            )
        else:
            self.unparsed_records += 1
        self._current_href = None
        self._title_parts = []
        self._context_parts = []
        self._capture_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "a":
            return
        href = next((value for key, value in attrs if key.casefold() == "href"), None)
        if href and self._is_article_href(href):
            if self._current_href != href:
                self._finalize_current()
                self._current_href = href
                self._title_parts = []
                self._context_parts = []
            self._capture_title = True

    def handle_data(self, data: str) -> None:
        text = clean_text(data)
        if not text:
            return
        self._text_parts.append(text)
        if self._current_href is None:
            return
        if self._capture_title:
            self._title_parts.append(text)
        else:
            self._context_parts.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "a" and self._capture_title:
            self._capture_title = False

    def finish(self) -> None:
        self._finalize_current()

    @property
    def page_count(self) -> int | None:
        match = _PAGE_RE.search(" ".join(self._text_parts))
        return int(match.group(2)) if match else None


class CambridgeCoreAdapter:
    """Cambridge Core first-party adapter for fully open-access journals.

    Catalog discovery is publisher-level and lightweight. Article acquisition is
    journal-scoped: only the journal selected by the caller is traversed.
    """

    source = "cambridge_core"
    provider = "cambridge"

    def __init__(self, client: HttpClient) -> None:
        self.client = client

    @staticmethod
    def query(spec: EditionSpec) -> str:
        return (
            f"cambridge-journal={spec.slug}; "
            f"published-online={spec.start_date.isoformat()}..{spec.end_date.isoformat()}"
        )

    def list_journals(self) -> list[dict[str, Any]]:
        journals: dict[str, dict[str, Any]] = {}
        page = 1
        page_count: int | None = None
        while page <= MAX_CATALOG_PAGES:
            params = dict(OA_JOURNAL_LISTING_PARAMS)
            params["pageNum"] = page
            payload = self.client.get_bytes(OA_JOURNAL_LISTING, params=params)
            parser = _JournalListingParser()
            parser.feed(payload.decode("utf-8", errors="replace"))
            parser.close()
            if page == 1 and not parser.journals:
                raise ValueError("Cambridge OA journal catalog returned no journal records")
            for journal in parser.journals:
                journals.setdefault(str(journal["slug"]), journal)
            if page_count is None:
                page_count = parser.page_count
            if page_count is not None and page >= page_count:
                break
            if not parser.journals:
                break
            page += 1
        if page > MAX_CATALOG_PAGES:
            raise ValueError("Cambridge OA journal catalog exceeded page safety limit")
        return sorted(journals.values(), key=lambda item: str(item["name"]).casefold())

    def resolve_journal(self, slug: str) -> dict[str, Any]:
        wanted = clean_text(slug).casefold()
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?", wanted):
            raise ValueError(f"unsafe Cambridge journal slug: {slug!r}")
        url = f"{BASE_URL}/core/journals/{wanted}"
        payload = self.client.get_bytes(url)
        parser = _JournalHomeParser()
        parser.feed(payload.decode("utf-8", errors="replace"))
        parser.close()
        text = parser.text
        issn_index = text.find("ISSN:")
        if issn_index < 0:
            raise ValueError("Cambridge journal page does not expose ISSN metadata")
        access_context = text[:issn_index].casefold()
        if "contains open access" in access_context or "open access" not in access_context:
            raise KeyError(f"Cambridge journal is not in the fully-OA journal set: {slug}")
        title = parser.title
        name = clean_text(title.split("| Cambridge Core", 1)[0])
        if not name:
            raise ValueError("Cambridge journal page does not expose a canonical title")
        online_match = _ONLINE_ISSN_RE.search(text)
        print_match = _PRINT_ISSN_RE.search(text)
        any_match = _ANY_ISSN_RE.search(text)
        online_issn = normalize_issn(online_match.group(1)) if online_match else None
        print_issn = normalize_issn(print_match.group(1)) if print_match else None
        any_issn = normalize_issn(any_match.group(1)) if any_match else None
        return {
            "provider": "cambridge",
            "publisher": "Cambridge University Press",
            "name": name,
            "slug": wanted,
            "issn": online_issn or print_issn or any_issn,
            "online_issn": online_issn,
            "print_issn": print_issn,
            "oa": "fully_oa",
            "status": "active",
            "sources": ["cambridge_core"],
            "url": url,
        }

    def fetch(self, spec: EditionSpec) -> AdapterResult:
        query = self.query(spec)
        try:
            canonical = self.resolve_journal(spec.slug)
            if clean_text(canonical["name"]).casefold() != clean_text(spec.journal).casefold():
                raise ValueError(
                    "selected Cambridge journal slug resolves to a different journal name"
                )
            canonical_issn = normalize_issn(str(canonical.get("issn") or ""))
            requested_issn = normalize_issn(str(spec.issn or ""))
            if requested_issn and canonical_issn and requested_issn != canonical_issn:
                known = {
                    value
                    for value in (
                        normalize_issn(str(canonical.get("online_issn") or "")),
                        normalize_issn(str(canonical.get("print_issn") or "")),
                    )
                    if value
                }
                if requested_issn not in known:
                    raise ValueError("selected Cambridge journal ISSN does not match provider metadata")

            articles: list[Article] = []
            returned_count = 0
            unparsed = 0
            page = 1
            page_count: int | None = None
            truncated = False
            reached_before_start = False
            while page <= MAX_ARTICLE_PAGES:
                url = f"{BASE_URL}/core/journals/{spec.slug}/open-access"
                payload = self.client.get_bytes(url, params={"pageNum": page})
                parser = _ArticleListingParser(spec.slug)
                parser.feed(payload.decode("utf-8", errors="replace"))
                parser.close()
                parser.finish()
                unparsed += parser.unparsed_records
                if page_count is None:
                    page_count = parser.page_count
                if not parser.records:
                    break

                for raw in parser.records:
                    returned_count += 1
                    published = raw["publication_date"]
                    if published < spec.start_date:
                        reached_before_start = True
                        continue
                    if published > spec.end_date:
                        if returned_count >= spec.max_records:
                            truncated = True
                            break
                        continue
                    url_value = safe_http_metadata_url(str(raw["url"]))
                    articles.append(
                        Article(
                            title=str(raw["title"]),
                            journal=spec.journal,
                            publication_date=published,
                            publication_date_precision="DAY",
                            issns=[requested_issn or canonical_issn]
                            if (requested_issn or canonical_issn)
                            else [],
                            urls=[url_value] if url_value else [],
                            source_records=[
                                SourceRecord(
                                    self.source,
                                    str(raw["source_id"]),
                                    url_value,
                                )
                            ],
                        )
                    )
                    if returned_count >= spec.max_records:
                        if not reached_before_start and (
                            page_count is None or page < page_count
                        ):
                            truncated = True
                        break

                if returned_count >= spec.max_records:
                    break
                if reached_before_start:
                    break
                if page_count is not None and page >= page_count:
                    break
                page += 1

            if page > MAX_ARTICLE_PAGES:
                raise ValueError("Cambridge article listing exceeded page safety limit")
            incomplete = truncated or unparsed > 0
            if returned_count == 0:
                status = "NO_RESULTS"
            elif incomplete:
                status = "PARTIAL"
            else:
                status = "SUCCESS"
            detail_parts = [
                f"fully-OA catalog journal={canonical['slug']}",
                f"source records scanned={returned_count}",
                f"accepted in requested window={len(articles)}",
            ]
            if unparsed:
                detail_parts.append(f"unparsed article records={unparsed}")
            if truncated:
                detail_parts.append("max_records prevented complete requested-window traversal")
            return AdapterResult(
                articles,
                SourceCheck(
                    source=self.source,
                    status=status,
                    query=query,
                    returned_count=returned_count,
                    total_available=None,
                    truncated=incomplete,
                    detail="; ".join(detail_parts),
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


__all__ = ["CambridgeCoreAdapter"]
