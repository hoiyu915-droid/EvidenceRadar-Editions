from __future__ import annotations

import calendar
import hashlib
import html
import re
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit, urlunsplit

_DOI_PREFIX_RE = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.I)
_NON_WORD_RE = re.compile(r"[^a-z0-9]+")
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
ALLOWED_DATE_PRECISIONS = ("DAY", "MONTH", "YEAR")


def clean_text(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = _TAG_RE.sub(" ", text)
    return _SPACE_RE.sub(" ", text).strip()


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    raw = _DOI_PREFIX_RE.sub("", clean_text(value)).strip().rstrip(".,;)")
    return raw.casefold() or None


def normalize_issn(value: str | None) -> str | None:
    if not value:
        return None
    compact = re.sub(r"[^0-9Xx]", "", value)
    if len(compact) != 8:
        return None
    return f"{compact[:4]}-{compact[4:].upper()}"


def normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKC", clean_text(value)).casefold().strip()
    return " ".join(text.split())


def normalize_title_key(value: str) -> str:
    text = unicodedata.normalize("NFKD", clean_text(value)).casefold()
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return _NON_WORD_RE.sub("", text)


def slugify(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").casefold()
    return text or "edition"


def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def first_nonempty(values: Iterable[str | None]) -> str | None:
    for value in values:
        if value and value.strip():
            return value.strip()
    return None


def parse_iso_date(value: str) -> date:
    return date.fromisoformat(value.strip())


def date_from_parts_with_precision(
    parts: list[int] | tuple[int, ...] | None,
) -> tuple[date, str] | None:
    if not parts:
        return None
    try:
        year = int(parts[0])
        if len(parts) == 1:
            return date(year, 1, 1), "YEAR"
        month = int(parts[1])
        if len(parts) == 2:
            return date(year, month, 1), "MONTH"
        return date(year, month, int(parts[2])), "DAY"
    except (TypeError, ValueError):
        return None


def date_from_parts(parts: list[int] | tuple[int, ...] | None) -> date | None:
    value = date_from_parts_with_precision(parts)
    return value[0] if value else None


def parse_loose_date_with_precision(value: str | None) -> tuple[date, str] | None:
    if not value:
        return None
    raw = clean_text(value)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[T ].*)?", raw):
        try:
            return date.fromisoformat(raw[:10]), "DAY"
        except ValueError:
            return None
    if re.fullmatch(r"\d{4}-\d{2}", raw):
        try:
            return date(int(raw[:4]), int(raw[5:7]), 1), "MONTH"
        except ValueError:
            return None
    if re.fullmatch(r"\d{4}", raw):
        return date(int(raw), 1, 1), "YEAR"
    for fmt, precision in (
        ("%Y %b %d", "DAY"),
        ("%Y %B %d", "DAY"),
        ("%Y %b", "MONTH"),
        ("%Y %B", "MONTH"),
        ("%Y", "YEAR"),
    ):
        try:
            parsed = datetime.strptime(raw, fmt).date()
            return parsed, precision
        except ValueError:
            continue
    match = re.search(r"\b((?:19|20)\d{2})(?:\s+([A-Za-z]{3,9}))?\b", raw)
    if match:
        year = int(match.group(1))
        month_name = match.group(2)
        if month_name:
            for fmt in ("%b", "%B"):
                try:
                    month = datetime.strptime(month_name, fmt).month
                    return date(year, month, 1), "MONTH"
                except ValueError:
                    pass
        return date(year, 1, 1), "YEAR"
    return None


def parse_loose_date(value: str | None) -> date | None:
    parsed = parse_loose_date_with_precision(value)
    return parsed[0] if parsed else None


def publication_interval(value: date, precision: str = "DAY") -> tuple[date, date]:
    normalized = precision.upper()
    if normalized == "DAY":
        return value, value
    if normalized == "MONTH":
        return value.replace(day=1), value.replace(
            day=calendar.monthrange(value.year, value.month)[1]
        )
    if normalized == "YEAR":
        return date(value.year, 1, 1), date(value.year, 12, 31)
    raise ValueError(f"unsupported publication-date precision: {precision}")


def period_overlaps(
    publication_date: date,
    publication_precision: str,
    start: date,
    end: date,
) -> bool:
    observed_start, observed_end = publication_interval(
        publication_date, publication_precision
    )
    return observed_start <= end and observed_end >= start


def safe_http_metadata_url(value: str | None) -> str | None:
    """Return a syntactically safe HTTP(S) metadata URL without fetching it."""

    if not value:
        return None
    try:
        parsed = urlsplit(str(value).strip())
        _ = parsed.port
    except ValueError:
        return None
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    try:
        hostname = parsed.hostname.encode("idna").decode("ascii").casefold()
    except UnicodeError:
        return None
    host = f"[{hostname}]" if ":" in hostname else hostname
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme.casefold(), host, parsed.path or "/", parsed.query, ""))


def contains_cjk(value: str | None) -> bool:
    if not value:
        return False
    return any(
        "\u3400" <= char <= "\u4dbf"
        or "\u4e00" <= char <= "\u9fff"
        or "\uf900" <= char <= "\ufaff"
        for char in value
    )
