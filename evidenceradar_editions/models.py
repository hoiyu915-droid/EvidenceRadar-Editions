from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import re
from typing import Any

from .naming import ALLOWED_PERIOD_KINDS

ALLOWED_SOURCES = (
    "pubmed",
    "europe_pmc",
    "crossref",
    "radar_rss",
    "rsc_chemical_science",
)
ALLOWED_SOURCE_STATUSES = ("SUCCESS", "NO_RESULTS", "PARTIAL", "FAILED", "NOT_ATTEMPTED")


@dataclass(frozen=True)
class EditionSpec:
    journal: str
    start_date: date
    end_date: date
    slug: str
    issn: str | None = None
    sources: tuple[str, ...] = ALLOWED_SOURCES
    max_records: int = 500
    period_kind: str = "auto"
    revision: int = 1
    language: str = "zh-TW"

    def __post_init__(self) -> None:
        if not self.journal.strip():
            raise ValueError("journal must not be empty")
        if self.start_date > self.end_date:
            raise ValueError("start_date must be <= end_date")
        if not self.slug.strip():
            raise ValueError("slug must not be empty")
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?", self.slug):
            raise ValueError(
                "slug must contain only lowercase ASCII letters, digits and internal hyphens (1-80 chars)"
            )
        if not (1 <= self.max_records <= 5000):
            raise ValueError("max_records must be between 1 and 5000")
        if self.period_kind not in ALLOWED_PERIOD_KINDS:
            raise ValueError(f"unsupported period kind: {self.period_kind}")
        if not (1 <= self.revision <= 9999):
            raise ValueError("revision must be between 1 and 9999")
        if self.language != "zh-TW":
            raise ValueError("v0.2 publication language must be zh-TW")
        unknown = [source for source in self.sources if source not in ALLOWED_SOURCES]
        if unknown:
            raise ValueError(f"unsupported sources: {', '.join(unknown)}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "journal": self.journal,
            "issn": self.issn,
            "slug": self.slug,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "sources": list(self.sources),
            "max_records": self.max_records,
            "period_kind_requested": self.period_kind,
            "revision": self.revision,
            "language": self.language,
        }


@dataclass
class SourceRecord:
    source: str
    source_id: str | None = None
    url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "source_id": self.source_id, "url": self.url}


@dataclass
class Article:
    title: str
    journal: str
    publication_date: date
    publication_date_precision: str = "DAY"
    doi: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    issns: list[str] = field(default_factory=list)
    authors: list[str] = field(default_factory=list)
    article_type: str | None = None
    urls: list[str] = field(default_factory=list)
    source_records: list[SourceRecord] = field(default_factory=list)
    title_zh_tw: str | None = None
    summary_zh_tw: str | None = None
    translation_basis: str | None = None
    translation_source_url: str | None = None

    def __post_init__(self) -> None:
        from .utils import ALLOWED_DATE_PRECISIONS

        self.publication_date_precision = self.publication_date_precision.upper()
        if self.publication_date_precision not in ALLOWED_DATE_PRECISIONS:
            raise ValueError(
                f"unsupported publication-date precision: {self.publication_date_precision}"
            )

    @property
    def canonical_id(self) -> str:
        from .utils import normalize_doi, normalize_title_key

        doi = normalize_doi(self.doi)
        if doi:
            return f"doi:{doi}"
        if self.pmid:
            return f"pmid:{self.pmid.strip()}"
        if self.pmcid:
            return f"pmcid:{self.pmcid.strip().upper()}"
        return (
            "fingerprint:"
            + normalize_title_key(self.title)
            + "|"
            + self.publication_date.isoformat()
        )

    def to_dict(self) -> dict[str, Any]:
        translated = bool(self.title_zh_tw and self.summary_zh_tw)
        return {
            "canonical_id": self.canonical_id,
            "title": self.title,
            "title_original": self.title,
            "title_zh_tw": self.title_zh_tw,
            "summary_zh_tw": self.summary_zh_tw,
            "translation_basis": self.translation_basis,
            "translation_source_url": self.translation_source_url,
            "translation_status": "COMPLETE" if translated else "MISSING",
            "journal": self.journal,
            "publication_date": self.publication_date.isoformat(),
            "publication_date_precision": self.publication_date_precision,
            "doi": self.doi,
            "pmid": self.pmid,
            "pmcid": self.pmcid,
            "issns": sorted(set(self.issns)),
            "authors": self.authors,
            "article_type": self.article_type,
            "urls": sorted(set(self.urls)),
            "source_records": [record.to_dict() for record in self.source_records],
        }


@dataclass
class SourceCheck:
    source: str
    status: str
    query: str
    returned_count: int = 0
    accepted_count: int = 0
    total_available: int | None = None
    truncated: bool = False
    detail: str | None = None

    def __post_init__(self) -> None:
        if self.status not in ALLOWED_SOURCE_STATUSES:
            raise ValueError(f"unsupported source status: {self.status}")
        if self.returned_count < 0 or self.accepted_count < 0:
            raise ValueError("source counts must be non-negative")
        if self.total_available is not None and self.total_available < 0:
            raise ValueError("total_available must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "status": self.status,
            "query": self.query,
            "returned_count": self.returned_count,
            "accepted_count": self.accepted_count,
            "total_available": self.total_available,
            "truncated": self.truncated,
            "detail": self.detail,
        }


@dataclass
class AdapterResult:
    articles: list[Article]
    check: SourceCheck
