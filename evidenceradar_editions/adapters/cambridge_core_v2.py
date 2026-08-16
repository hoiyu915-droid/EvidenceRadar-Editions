from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit

from ..models import AdapterResult, EditionSpec
from ..utils import clean_text
from .cambridge_core import (
    BASE_URL,
    MAX_CATALOG_PAGES,
    OA_JOURNAL_LISTING,
    OA_JOURNAL_LISTING_PARAMS,
    _JOURNAL_PATH_RE,
    _PAGE_RE,
    CambridgeCoreAdapter as _LegacyCambridgeCoreAdapter,
)

_RESULTS_HEADING_RE = re.compile(r"\b(\d+)\s+results?\b", re.I)
_UNPARSED_ARTICLE_RECORDS_RE = re.compile(r"\bunparsed article records=(\d+)\b")
_SOURCE_RECORDS_SCANNED_RE = re.compile(r"\bsource records scanned=\d+\b")


class _ScopedJournalListingParser(HTMLParser):
    """Parse only Cambridge's primary result-title journal links.

    Cambridge open-access result cards use ``class="part-link"`` on the
    primary journal-title anchor. The same cards can also contain related
    journal/supplement links whose URLs look like journal roots but which are
    not results; those links do not carry ``part-link``. Catalog identity is
    therefore bound to the first-party result-title marker, then reconciled
    against Cambridge's declared result count before being returned.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.journals: list[dict[str, Any]] = []
        self._capture: tuple[str, str] | None = None
        self._anchor_parts: list[str] = []
        self._text_parts: list[str] = []
        self._heading_tag: str | None = None
        self._heading_parts: list[str] = []
        self._in_results = False
        self.declared_result_count: int | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.casefold()
        if normalized in {"h1", "h2", "h3"}:
            self._heading_tag = normalized
            self._heading_parts = []
            return
        if normalized != "a" or not self._in_results:
            return
        values = {key.casefold(): value for key, value in attrs}
        href = str(values.get("href") or "").strip()
        classes = {
            token.casefold()
            for token in str(values.get("class") or "").split()
            if token.strip()
        }
        if "part-link" not in classes or not href.startswith("/core/journals/"):
            return
        match = _JOURNAL_PATH_RE.fullmatch(urlsplit(href).path)
        if match:
            self._capture = (match.group(1).casefold(), href)
            self._anchor_parts = []

    def handle_data(self, data: str) -> None:
        text = clean_text(data)
        if not text:
            return
        self._text_parts.append(text)
        if self._heading_tag is not None:
            self._heading_parts.append(text)
        if self._capture is not None:
            self._anchor_parts.append(text)

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.casefold()
        if self._heading_tag == normalized:
            heading = clean_text(" ".join(self._heading_parts))
            result_match = _RESULTS_HEADING_RE.search(heading)
            if result_match and "open access" in heading.casefold():
                self._in_results = True
                self.declared_result_count = int(result_match.group(1))
            self._heading_tag = None
            self._heading_parts = []
            return
        if normalized != "a" or self._capture is None:
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


class CambridgeCoreAdapter(_LegacyCambridgeCoreAdapter):
    """Cambridge adapter with fail-closed publisher-catalog reconciliation."""

    def list_journals(self) -> list[dict[str, Any]]:
        journals: dict[str, dict[str, Any]] = {}
        page = 1
        page_count: int | None = None
        declared_result_count: int | None = None

        while page <= MAX_CATALOG_PAGES:
            params = dict(OA_JOURNAL_LISTING_PARAMS)
            params["pageNum"] = page
            payload = self.client.get_bytes(OA_JOURNAL_LISTING, params=params)
            parser = _ScopedJournalListingParser()
            parser.feed(payload.decode("utf-8", errors="replace"))
            parser.close()
            if page == 1 and not parser.journals:
                raise ValueError(
                    "Cambridge OA journal catalog returned no primary result-title links"
                )
            if parser.declared_result_count is None:
                raise ValueError(
                    "Cambridge OA journal catalog does not expose a declared result count"
                )
            if declared_result_count is None:
                declared_result_count = parser.declared_result_count
            elif parser.declared_result_count != declared_result_count:
                raise ValueError(
                    "Cambridge OA journal result count changed during pagination"
                )

            for journal in parser.journals:
                journals.setdefault(str(journal["slug"]), journal)

            if page_count is None:
                page_count = parser.page_count
            elif parser.page_count is not None and parser.page_count != page_count:
                raise ValueError(
                    "Cambridge OA journal page count changed during pagination"
                )
            if page_count is not None and page >= page_count:
                break
            if not parser.journals:
                raise ValueError(
                    f"Cambridge OA journal catalog page {page} contains no primary result-title links"
                )
            page += 1

        if page > MAX_CATALOG_PAGES:
            raise ValueError("Cambridge OA journal catalog exceeded page safety limit")
        if declared_result_count is None:
            raise ValueError("Cambridge OA journal catalog lacks a result count")
        if len(journals) != declared_result_count:
            raise ValueError(
                "Cambridge OA journal catalog reconciliation mismatch: "
                f"declared={declared_result_count}; primary_results={len(journals)}"
            )
        return sorted(journals.values(), key=lambda item: str(item["name"]).casefold())

    def fetch(self, spec: EditionSpec) -> AdapterResult:
        """Preserve observed-but-unparsed article cards as PARTIAL coverage.

        The legacy parser reports article cards whose title/date context could
        not be parsed in ``detail``. Those cards are still source records that
        were observed, so they must count toward ``returned_count`` and must
        prevent a false ``NO_RESULTS`` claim. The validator uses
        ``truncated=true`` as the generic incomplete-source marker for PARTIAL.
        """

        result = super().fetch(spec)
        check = result.check
        detail = str(check.detail or "")
        match = _UNPARSED_ARTICLE_RECORDS_RE.search(detail)
        if match is None:
            return result

        unparsed = int(match.group(1))
        if unparsed <= 0:
            return result

        check.returned_count += unparsed
        check.status = "PARTIAL"
        check.truncated = True
        scanned = f"source records scanned={check.returned_count}"
        if _SOURCE_RECORDS_SCANNED_RE.search(detail):
            detail = _SOURCE_RECORDS_SCANNED_RE.sub(scanned, detail, count=1)
        else:
            detail = f"{detail}; {scanned}" if detail else scanned
        check.detail = detail
        return result


__all__ = ["CambridgeCoreAdapter"]