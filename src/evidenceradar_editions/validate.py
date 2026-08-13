from __future__ import annotations

import html
import json
from datetime import date
from pathlib import Path
from typing import Any

from .models import Collection, publication_interval
from .provenance import sha256_file

REQUIRED_FILES = ("index.html", "edition.json", "sources.json", "manifest.json")
EDITION_STATUSES = {"COMPLETE", "PARTIAL", "FAILED"}
SOURCE_STATUSES = {"SUCCESS", "NO_RESULTS", "FAILED"}


class ValidationError(RuntimeError):
    """Raised when an edition directory violates the delivery contract."""


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot read JSON artifact: {path.name}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"JSON artifact must be an object: {path.name}")
    return value


def _nonnegative_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _derived_edition_status(receipts: list[dict[str, Any]]) -> str:
    statuses = {str(receipt.get("status") or "") for receipt in receipts}
    if statuses == {"FAILED"}:
        return "FAILED"
    truncated = any(
        isinstance(receipt.get("metadata"), dict)
        and receipt["metadata"].get("truncated") is True
        for receipt in receipts
    )
    if "FAILED" in statuses or truncated:
        return "PARTIAL"
    return "COMPLETE"


def validate_edition_directory(root: Path) -> dict[str, Any]:
    root = root.resolve()
    errors: list[str] = []
    if not root.is_dir():
        raise ValidationError(f"edition directory does not exist: {root}")
    for name in REQUIRED_FILES:
        if not (root / name).is_file():
            errors.append(f"missing artifact: {name}")
    if errors:
        raise ValidationError("\n".join(errors))

    edition = _load_object(root / "edition.json")
    sources = _load_object(root / "sources.json")
    manifest = _load_object(root / "manifest.json")
    try:
        html_text = (root / "index.html").read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValidationError("cannot read index.html as UTF-8") from exc

    if edition.get("schema_version") != "1.0":
        errors.append("edition.json schema_version must be 1.0")
    if sources.get("schema_version") != "1.0":
        errors.append("sources.json schema_version must be 1.0")
    if manifest.get("schema_version") != "1.0":
        errors.append("manifest.json schema_version must be 1.0")

    edition_id = str(edition.get("edition_id") or "")
    if not edition_id:
        errors.append("edition_id is required")
    escaped_edition_id = html.escape(edition_id, quote=True)
    if f'data-edition-id="{escaped_edition_id}"' not in html_text:
        errors.append("index.html edition marker does not match edition.json")
    if sources.get("edition_id") != edition_id:
        errors.append("sources.json edition_id does not match edition.json")
    if manifest.get("edition_id") != edition_id:
        errors.append("manifest edition_id does not match edition.json")

    edition_status = str(edition.get("status") or "")
    if edition_status not in EDITION_STATUSES:
        errors.append(f"invalid edition status: {edition_status}")
    if manifest.get("status") != edition_status:
        errors.append("manifest status does not match edition.json")
    if sources.get("retrieved_at") != edition.get("retrieved_at"):
        errors.append("sources.json retrieved_at does not match edition.json")
    if manifest.get("created_at") != edition.get("retrieved_at"):
        errors.append("manifest created_at does not match edition retrieval time")

    period = edition.get("period", {})
    if not isinstance(period, dict):
        errors.append("edition period must be an object")
        period = {}
    try:
        period_start = date.fromisoformat(str(period.get("start")))
        period_end = date.fromisoformat(str(period.get("end")))
    except (TypeError, ValueError):
        errors.append("edition period must contain ISO start/end dates")
        period_start = None
        period_end = None
    else:
        if period_end < period_start:
            errors.append("edition period end must be on or after start")
    if period.get("inclusive") is not True:
        errors.append("edition period must state inclusive=true")
    if period.get("basis") != "publication_date":
        errors.append("edition period basis must be publication_date")

    try:
        collection = Collection.from_mapping(edition.get("collection", {}))
    except (TypeError, ValueError) as exc:
        errors.append(f"edition collection is invalid: {exc}")
        collection = None

    receipts_raw = sources.get("receipts", [])
    if not isinstance(receipts_raw, list):
        errors.append("sources.json receipts must be an array")
        receipts_raw = []
    receipts: list[dict[str, Any]] = []
    receipt_names: list[str] = []
    for receipt in receipts_raw:
        if not isinstance(receipt, dict):
            errors.append("source receipt must be an object")
            continue
        receipts.append(receipt)
        source_name = str(receipt.get("source") or "")
        receipt_names.append(source_name)
        if not source_name:
            errors.append("source receipt is missing source")
        source_status = str(receipt.get("status") or "")
        if source_status not in SOURCE_STATUSES:
            errors.append(f"invalid source status: {source_status}")
        if not receipt.get("query") or not receipt.get("endpoint"):
            errors.append(f"source receipt is missing query/endpoint: {source_name}")
        returned_count = _nonnegative_int(receipt.get("returned_count"))
        request_count = _nonnegative_int(receipt.get("request_count"))
        if returned_count is None:
            errors.append(f"source receipt returned_count is invalid: {source_name}")
        if request_count is None:
            errors.append(f"source receipt request_count is invalid: {source_name}")
        if source_status == "SUCCESS" and returned_count == 0:
            errors.append(f"SUCCESS receipt must return at least one record: {source_name}")
        if source_status == "NO_RESULTS" and returned_count not in {0, None}:
            errors.append(f"NO_RESULTS receipt must return zero records: {source_name}")
        if source_status == "FAILED" and not receipt.get("error"):
            errors.append(f"FAILED receipt must record an error: {source_name}")
    if not receipts:
        errors.append("sources.json must contain at least one receipt")
    if len(receipt_names) != len(set(receipt_names)):
        errors.append("source receipt names must be unique")
    receipt_sources = set(receipt_names)
    if receipts and edition_status in EDITION_STATUSES:
        derived = _derived_edition_status(receipts)
        if edition_status != derived:
            errors.append(
                f"edition status {edition_status} does not match source receipts ({derived})"
            )

    articles_raw = edition.get("articles", [])
    if not isinstance(articles_raw, list):
        errors.append("edition.json articles must be an array")
        articles_raw = []
    if edition.get("article_count") != len(articles_raw):
        errors.append("edition.json article_count does not match articles")
    articles: list[dict[str, Any]] = []
    canonical_ids: list[str] = []
    for article in articles_raw:
        if not isinstance(article, dict):
            errors.append("article must be an object")
            continue
        articles.append(article)
        canonical_id = str(article.get("canonical_id") or "")
        canonical_ids.append(canonical_id)
        interval = publication_interval(
            article.get("publication_date"),
            article.get("publication_date_precision"),
        )
        if interval is None:
            errors.append(f"article has invalid publication date: {canonical_id}")
        elif period_start is not None and period_end is not None:
            if interval[0] < period_start or interval[1] > period_end:
                errors.append(f"article date interval falls outside edition period: {canonical_id}")
        if collection is not None and not collection.matches(
            journal=str(article.get("journal") or ""),
            issns=article.get("issns", []),
        ):
            errors.append(f"article does not match collection: {canonical_id}")
        article_sources = article.get("sources", [])
        if not isinstance(article_sources, list) or not article_sources:
            errors.append(f"article must reference at least one source: {canonical_id}")
        else:
            unknown_sources = set(str(value) for value in article_sources).difference(receipt_sources)
            if unknown_sources:
                errors.append(f"article references sources without receipts: {canonical_id}")
    if any(not value or value == "unknown" for value in canonical_ids):
        errors.append("every article must have a stable canonical_id")
    if len(canonical_ids) != len(set(canonical_ids)):
        errors.append("canonical_id values are not unique")
    for canonical_id in canonical_ids:
        escaped = html.escape(canonical_id, quote=True)
        if f'data-canonical-id="{escaped}"' not in html_text:
            errors.append(f"index.html is missing article marker: {canonical_id}")

    raw_record_count = _nonnegative_int(edition.get("raw_record_count"))
    if raw_record_count is None:
        errors.append("edition raw_record_count must be a non-negative integer")
    else:
        receipt_total = sum(
            int(receipt.get("returned_count") or 0)
            for receipt in receipts
            if _nonnegative_int(receipt.get("returned_count")) is not None
        )
        if raw_record_count != receipt_total:
            errors.append("edition raw_record_count does not match source receipts")
    filter_counts = edition.get("scope_filter_counts", {})
    if not isinstance(filter_counts, dict):
        errors.append("scope_filter_counts must be an object")
    else:
        if raw_record_count is not None and filter_counts.get("input") != raw_record_count:
            errors.append("scope_filter_counts.input does not match raw_record_count")
        accepted_before_dedup = _nonnegative_int(filter_counts.get("accepted_before_dedup"))
        if accepted_before_dedup is None:
            errors.append("scope_filter_counts.accepted_before_dedup is invalid")
        elif accepted_before_dedup < len(articles):
            errors.append("accepted_before_dedup cannot be lower than article_count")

    provenance = edition.get("provenance", {})
    upstream = provenance.get("upstream_radar", {}) if isinstance(provenance, dict) else {}
    if not isinstance(upstream, dict) or upstream.get("artifacts_consumed") is not False:
        errors.append("upstream provenance must state artifacts_consumed=false")
    if not isinstance(provenance, dict) or provenance.get("artifact_dependency") is not False:
        errors.append("edition provenance must state artifact_dependency=false")
    config_hash = provenance.get("collection_config_sha256") if isinstance(provenance, dict) else None
    if not isinstance(config_hash, str) or len(config_hash) != 64:
        errors.append("provenance collection_config_sha256 is invalid")
    if manifest.get("collection_config_sha256") != config_hash:
        errors.append("manifest collection config hash does not match edition provenance")
    if manifest.get("upstream_radar") != upstream:
        errors.append("manifest upstream provenance does not match edition.json")
    if manifest.get("source_names") != receipt_names:
        errors.append("manifest source_names do not match source receipts")

    artifact_records = manifest.get("artifacts", [])
    if not isinstance(artifact_records, list):
        errors.append("manifest artifacts must be an array")
        artifact_records = []
    listed_paths: set[str] = set()
    for record in artifact_records:
        if not isinstance(record, dict):
            errors.append("manifest artifact record must be an object")
            continue
        relative = str(record.get("path") or "")
        listed_paths.add(relative)
        path = root / relative
        if relative not in {"index.html", "edition.json", "sources.json"}:
            errors.append(f"manifest contains unexpected artifact: {relative}")
            continue
        if not path.is_file():
            errors.append(f"manifest artifact is missing: {relative}")
            continue
        if record.get("bytes") != path.stat().st_size:
            errors.append(f"manifest byte count mismatch: {relative}")
        if record.get("sha256") != sha256_file(path):
            errors.append(f"manifest SHA-256 mismatch: {relative}")
    if listed_paths != {"index.html", "edition.json", "sources.json"}:
        errors.append("manifest must bind exactly index.html, edition.json, and sources.json")
    if manifest.get("article_count") != len(articles_raw):
        errors.append("manifest article_count does not match edition.json")
    if "file://" in html_text or "localhost" in html_text or "127.0.0.1" in html_text:
        errors.append("index.html contains a local-only URL")

    if errors:
        raise ValidationError("edition validation failed:\n- " + "\n- ".join(errors))
    return {
        "valid": True,
        "edition_id": edition_id,
        "article_count": len(articles),
        "source_count": len(receipts),
        "root": str(root),
    }
