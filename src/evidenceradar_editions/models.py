from __future__ import annotations

import calendar
import hashlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from typing import Any

_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
_DOI_PREFIX_RE = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.I)


def clean_text(value: object) -> str:
    text = _TAG_RE.sub(" ", str(value or ""))
    return _SPACE_RE.sub(" ", text).strip()


def normalize_doi(value: object) -> str:
    doi = _DOI_PREFIX_RE.sub("", clean_text(value)).strip().strip(".")
    return doi.casefold()


def normalize_issn(value: object) -> str:
    text = re.sub(r"[^0-9Xx]", "", str(value or ""))
    if len(text) != 8:
        return ""
    return f"{text[:4]}-{text[4:].upper()}"


def normalize_title(value: object) -> str:
    text = clean_text(value).casefold()
    return re.sub(r"[^\w]+", " ", text, flags=re.UNICODE).strip()


def stable_unique(values: Iterable[object]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = clean_text(value)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


@dataclass(frozen=True)
class Collection:
    id: str
    name: str
    aliases: tuple[str, ...] = ()
    issns: tuple[str, ...] = ()
    publisher: str = ""
    default_sources: tuple[str, ...] = ("pubmed", "europe_pmc", "crossref")
    include_types: tuple[str, ...] = ()
    exclude_types: tuple[str, ...] = ()
    language: str = "en"

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "Collection":
        collection_id = clean_text(data.get("id"))
        name = clean_text(data.get("name"))
        if not _ID_RE.fullmatch(collection_id):
            raise ValueError("collection id must be lowercase kebab-case")
        if not name:
            raise ValueError("collection name is required")
        issns = tuple(filter(None, (normalize_issn(v) for v in data.get("issns", []))))
        aliases = tuple(stable_unique(data.get("aliases", [])))
        sources = tuple(clean_text(v) for v in data.get("default_sources", []) if clean_text(v))
        if not sources:
            sources = ("pubmed", "europe_pmc", "crossref")
        return cls(
            id=collection_id,
            name=name,
            aliases=aliases,
            issns=issns,
            publisher=clean_text(data.get("publisher")),
            default_sources=sources,
            include_types=tuple(stable_unique(data.get("include_types", []))),
            exclude_types=tuple(stable_unique(data.get("exclude_types", []))),
            language=clean_text(data.get("language")) or "en",
        )

    @property
    def venue_names(self) -> tuple[str, ...]:
        return (self.name, *self.aliases)

    def matches(self, *, journal: str, issns: Iterable[str]) -> bool:
        normalized_issns = {normalize_issn(v) for v in issns if normalize_issn(v)}
        if self.issns and normalized_issns.intersection(self.issns):
            return True
        venue = normalize_title(journal)
        return bool(venue and venue in {normalize_title(v) for v in self.venue_names})

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in ("aliases", "issns", "default_sources", "include_types", "exclude_types"):
            payload[key] = list(payload[key])
        return payload


@dataclass
class SourceReceipt:
    source: str
    status: str
    query: str
    endpoint: str
    retrieved_at: str
    returned_count: int = 0
    request_count: int = 0
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Article:
    title: str
    journal: str
    publication_date: str
    publication_date_precision: str = "DAY"
    authors: list[str] = field(default_factory=list)
    issns: list[str] = field(default_factory=list)
    doi: str = ""
    pmid: str = ""
    pmcid: str = ""
    abstract: str = ""
    article_types: list[str] = field(default_factory=list)
    study_designs: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    oa_status: str = "UNKNOWN"
    fulltext_status: str = "NOT_CHECKED"
    sources: list[str] = field(default_factory=list)
    source_records: list[dict[str, Any]] = field(default_factory=list)

    def identity_keys(self) -> list[str]:
        keys: list[str] = []
        if normalize_doi(self.doi):
            keys.append(f"doi:{normalize_doi(self.doi)}")
        if clean_text(self.pmid):
            keys.append(f"pmid:{clean_text(self.pmid)}")
        if clean_text(self.pmcid):
            keys.append(f"pmcid:{clean_text(self.pmcid).upper()}")
        title = normalize_title(self.title)
        if title:
            keys.append(
                "title:"
                + hashlib.sha256(
                    f"{title}|{normalize_title(self.journal)}|{self.publication_date}".encode()
                ).hexdigest()[:24]
            )
        return keys

    @property
    def canonical_id(self) -> str:
        return self.identity_keys()[0] if self.identity_keys() else "unknown"

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["canonical_id"] = self.canonical_id
        return payload


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def parse_date(value: object) -> date | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def publication_interval(value: object, precision: object = "DAY") -> tuple[date, date] | None:
    parsed = parse_date(value)
    if parsed is None:
        return None
    normalized = clean_text(precision).upper() or "UNKNOWN"
    if normalized == "DAY":
        return parsed, parsed
    if normalized == "MONTH":
        start = parsed.replace(day=1)
        end = parsed.replace(day=calendar.monthrange(parsed.year, parsed.month)[1])
        return start, end
    if normalized == "YEAR":
        return date(parsed.year, 1, 1), date(parsed.year, 12, 31)
    return None


_STUDY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("randomized_controlled_trial", re.compile(r"\brandomi[sz]ed\b.*\btrial\b", re.I)),
    ("systematic_review", re.compile(r"\bsystematic review\b", re.I)),
    ("meta_analysis", re.compile(r"\bmeta[- ]analys(?:is|es)\b", re.I)),
    ("scoping_review", re.compile(r"\bscoping review\b", re.I)),
    ("cohort_study", re.compile(r"\bcohort stud(?:y|ies)\b", re.I)),
    ("case_control_study", re.compile(r"\bcase[- ]control\b", re.I)),
    ("cross_sectional_study", re.compile(r"\bcross[- ]sectional\b", re.I)),
    ("protocol", re.compile(r"\bprotocol\b", re.I)),
)


def classify_study_designs(title: str, article_types: Iterable[str]) -> list[str]:
    haystack = " ".join([title, *article_types])
    return [label for label, pattern in _STUDY_PATTERNS if pattern.search(haystack)]
