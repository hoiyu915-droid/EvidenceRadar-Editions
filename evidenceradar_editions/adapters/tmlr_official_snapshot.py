from __future__ import annotations

from datetime import date
from html.parser import HTMLParser
import re
from typing import Any
from urllib.parse import parse_qs, urlsplit

from ..http import HttpClient
from ..models import AdapterResult, Article, EditionSpec, SourceCheck, SourceRecord
from ..utils import clean_text, normalize_issn


ENDPOINT = "https://jmlr.org/tmlr/papers/"
JOURNAL = "Transactions on Machine Learning Research"
ISSN = "2835-8856"
MONTHS = {
    name: index
    for index, name in enumerate(
        (
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ),
        start=1,
    )
}
MONTH_RE = re.compile(
    r"\b(" + "|".join(MONTHS) + r")\s+(20\d{2})\b"
)
OPENREVIEW_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class _PapersParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[dict[str, Any]] = []
        self.current: dict[str, Any] | None = None
        self._capture_title = False
        self._capture_authors = False

    @staticmethod
    def _classes(attrs: list[tuple[str, str | None]]) -> set[str]:
        value = next((value for key, value in attrs if key == "class"), None)
        return {part for part in str(value or "").split() if part}

    @staticmethod
    def _href(attrs: list[tuple[str, str | None]]) -> str:
        return str(next((value for key, value in attrs if key == "href"), "") or "")

    @staticmethod
    def _openreview_id(href: str) -> str | None:
        parsed = urlsplit(href)
        if parsed.hostname not in {"openreview.net", "www.openreview.net"}:
            return None
        values = parse_qs(parsed.query).get("id") or []
        value = str(values[0] if values else "")
        return value if OPENREVIEW_ID_RE.fullmatch(value) else None

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag == "li" and "item" in self._classes(attrs) and self.current is None:
            self.current = {
                "title_parts": [],
                "author_parts": [],
                "text_parts": [],
                "openreview_id": None,
            }
            return
        if self.current is None:
            return
        if tag == "a":
            classes = self._classes(attrs)
            if "paper-data-bs-title" in classes:
                self._capture_title = True
            source_id = self._openreview_id(self._href(attrs))
            if source_id:
                self.current["openreview_id"] = source_id
        elif tag == "i":
            self._capture_authors = True

    def handle_endtag(self, tag: str) -> None:
        if self.current is None:
            return
        if tag == "a":
            self._capture_title = False
        elif tag == "i":
            self._capture_authors = False
        elif tag == "li":
            self.items.append(self.current)
            self.current = None
            self._capture_title = False
            self._capture_authors = False

    def handle_data(self, data: str) -> None:
        if self.current is None:
            return
        self.current["text_parts"].append(data)
        if self._capture_title:
            self.current["title_parts"].append(data)
        if self._capture_authors:
            self.current["author_parts"].append(data)


class TmlrOfficialSnapshotAdapter:
    """Parse TMLR's first-party accepted-papers snapshot without inferring days."""

    source = "tmlr_official_snapshot"

    def __init__(self, client: HttpClient) -> None:
        self.client = client

    @staticmethod
    def query(spec: EditionSpec) -> str:
        return (
            f"official TMLR accepted-papers snapshot; publication-month="
            f"{spec.start_date.year:04d}-{spec.start_date.month:02d}"
        )

    @staticmethod
    def _scope_error(spec: EditionSpec) -> str | None:
        if clean_text(spec.journal).casefold() != JOURNAL.casefold():
            return f"adapter is restricted to {JOURNAL!r}"
        if normalize_issn(str(spec.issn or "")) != ISSN:
            return f"adapter requires ISSN {ISSN}"
        if (spec.start_date.year, spec.start_date.month) != (
            spec.end_date.year,
            spec.end_date.month,
        ):
            return "TMLR snapshot request must remain inside one calendar month"
        return None

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
        try:
            payload = self.client.get_bytes(ENDPOINT, limit=8 * 1024 * 1024)
            parser = _PapersParser()
            parser.feed(payload.decode("utf-8"))
            parser.close()

            target = (spec.start_date.year, spec.start_date.month)
            matched: list[dict[str, Any]] = []
            rejected = 0
            for item in parser.items:
                text = clean_text(" ".join(item["text_parts"]))
                label = MONTH_RE.search(text)
                if label is None:
                    continue
                observed = (int(label.group(2)), MONTHS[label.group(1)])
                if observed != target:
                    continue
                title = clean_text(" ".join(item["title_parts"]))
                source_id = str(item.get("openreview_id") or "")
                if not title or not OPENREVIEW_ID_RE.fullmatch(source_id):
                    rejected += 1
                    continue
                matched.append(
                    {
                        "title": title,
                        "authors": [
                            value.strip()
                            for value in clean_text(
                                " ".join(item["author_parts"])
                            ).split(",")
                            if value.strip()
                        ],
                        "source_id": source_id,
                    }
                )

            total_available = len(matched) + rejected
            limited = matched[: spec.max_records]
            truncated = rejected > 0 or len(matched) > len(limited)
            articles = []
            for item in limited:
                source_id = str(item["source_id"])
                forum_url = f"https://openreview.net/forum?id={source_id}"
                articles.append(
                    Article(
                        title=str(item["title"]),
                        journal=JOURNAL,
                        publication_date=date(target[0], target[1], 1),
                        publication_date_precision="MONTH",
                        issns=[ISSN],
                        authors=list(item["authors"]),
                        article_type="Journal Article",
                        urls=[forum_url],
                        source_records=[
                            SourceRecord(self.source, source_id, forum_url)
                        ],
                    )
                )
            if total_available == 0:
                status = "NO_RESULTS"
            elif truncated:
                status = "PARTIAL"
            else:
                status = "SUCCESS"
            detail = (
                "The first-party TMLR page exposes publication month, not day; "
                "no day is inferred. Incremental composition compares this current "
                "month snapshot with the immutable prior snapshot by OpenReview ID."
            )
            if rejected:
                detail += f" Unparseable target-month entries={rejected}."
            return AdapterResult(
                articles,
                SourceCheck(
                    source=self.source,
                    status=status,
                    query=query,
                    returned_count=total_available,
                    accepted_count=len(articles),
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


__all__ = ["TmlrOfficialSnapshotAdapter"]
