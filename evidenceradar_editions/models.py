from __future__ import annotations

from dataclasses import dataclass, field
import re
from datetime import date
from typing import Any

ALLOWED_SOURCES = ("pubmed", "europe_pmc", "crossref", "radar_rss")

@dataclass(frozen=True)
class EditionSpec:
    journal: str
    start_date: date
    end_date: date
    slug: str
    issn: str | None = None
    sources: tuple[str, ...] = ALLOWED_SOURCES
    max_records: int = 500

    def __post_init__(self) -> None:
        if not self.journal.strip():
            raise ValueError("journal must not be empty")
        if self.start_date > self.end_date:
            raise ValueError("start_date must be <= end_date")
        if not self.slug.strip():
            raise ValueError("slug must not be empty")
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?", self.slug):
            raise ValueError("slug must contain only lowercase ASCII letters, digits and internal hyphens (1-80 chars)")
        if not (1 <= self.max_records <= 5000):
            raise ValueError("max_records must be between 1 and 5000")
        unknown = [s for s in self.sources if s not in ALLOWED_SOURCES]
        if unknown:
            raise ValueError(f"unsupported sources: {', '.join(unknown)}")

    def to_dict(self) -> dict[str, Any]:
        return {"journal": self.journal, "issn": self.issn, "slug": self.slug, "start_date": self.start_date.isoformat(), "end_date": self.end_date.isoformat(), "sources": list(self.sources), "max_records": self.max_records}

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
    doi: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    issns: list[str] = field(default_factory=list)
    authors: list[str] = field(default_factory=list)
    article_type: str | None = None
    urls: list[str] = field(default_factory=list)
    source_records: list[SourceRecord] = field(default_factory=list)

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
        return "fingerprint:" + normalize_title_key(self.title) + "|" + self.publication_date.isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {"canonical_id": self.canonical_id, "title": self.title, "journal": self.journal, "publication_date": self.publication_date.isoformat(), "doi": self.doi, "pmid": self.pmid, "pmcid": self.pmcid, "issns": sorted(set(self.issns)), "authors": self.authors, "article_type": self.article_type, "urls": sorted(set(self.urls)), "source_records": [r.to_dict() for r in self.source_records]}

@dataclass
class SourceCheck:
    source: str
    status: str
    query: str
    returned_count: int = 0
    accepted_count: int = 0
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "status": self.status, "query": self.query, "returned_count": self.returned_count, "accepted_count": self.accepted_count, "detail": self.detail}

@dataclass
class AdapterResult:
    articles: list[Article]
    check: SourceCheck
