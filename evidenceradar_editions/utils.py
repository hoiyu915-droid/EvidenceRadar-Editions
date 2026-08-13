from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

_DOI_PREFIX_RE = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.I)
_NON_WORD_RE = re.compile(r"[^a-z0-9]+")

def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    raw = _DOI_PREFIX_RE.sub("", value.strip()).strip().rstrip(".,;)")
    return raw.casefold() or None

def normalize_issn(value: str | None) -> str | None:
    if not value:
        return None
    compact = re.sub(r"[^0-9Xx]", "", value)
    if len(compact) != 8:
        return value.strip().upper()
    return f"{compact[:4]}-{compact[4:].upper()}"

def normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).casefold().strip()
    return " ".join(text.split())

def normalize_title_key(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).casefold()
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return _NON_WORD_RE.sub("", text)

def slugify(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").casefold()
    return text or "edition"

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

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

def date_from_parts(parts: list[int] | tuple[int, ...] | None) -> date | None:
    if not parts:
        return None
    try:
        year = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 else 1
        day = int(parts[2]) if len(parts) > 2 else 1
        return date(year, month, day)
    except (TypeError, ValueError):
        return None

def parse_loose_date(value: str | None) -> date | None:
    if not value:
        return None
    raw = value.strip()
    for candidate in (raw, raw[:10]):
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            pass
    for fmt in ("%Y %b %d", "%Y %B %d", "%Y %b", "%Y %B", "%Y"):
        try:
            parsed = datetime.strptime(raw, fmt)
            return parsed.date().replace(day=parsed.day if "%d" in fmt else 1)
        except ValueError:
            continue
    match = re.search(r"\b(19|20)\d{2}\b", raw)
    if match:
        return date(int(match.group()), 1, 1)
    return None
