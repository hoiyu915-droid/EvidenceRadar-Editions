from __future__ import annotations

import calendar
import copy
import hashlib
import secrets
import shutil
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .config import load_collection
from .http_client import SafeHttpClient
from .models import (
    Article,
    Collection,
    SourceReceipt,
    clean_text,
    normalize_doi,
    publication_interval,
    stable_unique,
    utc_now_iso,
)
from .provenance import artifact_record, atomic_write_bytes, atomic_write_json
from .renderer import render_edition
from .sources import SUPPORTED_SOURCES, SourceResult, fetch_source
from .upstream import RadarNetworkBridge, RadarReference, declared_reference, inspect_radar_checkout
from .validate import validate_edition_directory


class BuildError(RuntimeError):
    """Raised when an edition cannot be built safely."""


@dataclass(frozen=True)
class BuildOptions:
    collection_path: Path
    start: date
    end: date
    output_dir: Path
    sources: tuple[str, ...] = ()
    fixture_dir: Path | None = None
    radar_root: Path | None = None
    allow_radar_drift: bool = False
    strict_sources: bool = False
    max_records_per_source: int = 5000
    replace: bool = False
    timezone: str = "Asia/Tokyo"


def _merge_article(target: Article, incoming: Article) -> Article:
    merged = copy.deepcopy(target)
    if not merged.title or len(incoming.title) > len(merged.title):
        merged.title = incoming.title
    if not merged.journal:
        merged.journal = incoming.journal
    precision_rank = {"UNKNOWN": 0, "YEAR": 1, "MONTH": 2, "DAY": 3}
    if (
        not merged.publication_date
        or precision_rank.get(incoming.publication_date_precision, 0)
        > precision_rank.get(merged.publication_date_precision, 0)
    ):
        merged.publication_date = incoming.publication_date
        merged.publication_date_precision = incoming.publication_date_precision
    merged.authors = stable_unique([*merged.authors, *incoming.authors])
    merged.issns = stable_unique([*merged.issns, *incoming.issns])
    if not merged.doi:
        merged.doi = normalize_doi(incoming.doi)
    if not merged.pmid:
        merged.pmid = clean_text(incoming.pmid)
    if not merged.pmcid:
        merged.pmcid = clean_text(incoming.pmcid).upper()
    if not merged.abstract or len(incoming.abstract) > len(merged.abstract):
        merged.abstract = incoming.abstract
    merged.article_types = stable_unique([*merged.article_types, *incoming.article_types])
    merged.study_designs = stable_unique([*merged.study_designs, *incoming.study_designs])
    merged.urls = stable_unique([*merged.urls, *incoming.urls])
    merged.sources = stable_unique([*merged.sources, *incoming.sources])
    merged.source_records.extend(copy.deepcopy(incoming.source_records))
    if "YES" in {merged.oa_status, incoming.oa_status}:
        merged.oa_status = "YES"
    elif "NO" in {merged.oa_status, incoming.oa_status}:
        merged.oa_status = "NO"
    if merged.fulltext_status == "NOT_CHECKED" and incoming.fulltext_status != "NOT_CHECKED":
        merged.fulltext_status = incoming.fulltext_status
    return merged


def deduplicate_articles(articles: Iterable[Article]) -> list[Article]:
    values = list(articles)
    if not values:
        return []
    parent = list(range(len(values)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    key_owner: dict[str, int] = {}
    for index, article in enumerate(values):
        for key in article.identity_keys():
            if key in key_owner:
                union(index, key_owner[key])
            else:
                key_owner[key] = index

    groups: dict[int, list[int]] = {}
    for index in range(len(values)):
        groups.setdefault(find(index), []).append(index)

    merged_articles: list[Article] = []
    for indices in groups.values():
        ordered = sorted(
            (values[index] for index in indices),
            key=lambda article: (
                0 if article.doi else 1,
                0 if article.pmid else 1,
                0 if article.pmcid else 1,
                -len(article.abstract),
                article.title.casefold(),
            ),
        )
        merged = copy.deepcopy(ordered[0])
        for incoming in ordered[1:]:
            merged = _merge_article(merged, incoming)
        merged_articles.append(merged)
    return sorted(
        merged_articles,
        key=lambda article: (
            article.publication_date or "9999-12-31",
            article.title.casefold(),
            article.canonical_id,
        ),
        reverse=True,
    )


def _type_allowed(article: Article, collection: Collection) -> bool:
    observed = {clean_text(value).casefold() for value in article.article_types}
    included = {clean_text(value).casefold() for value in collection.include_types}
    excluded = {clean_text(value).casefold() for value in collection.exclude_types}
    if included and not observed.intersection(included):
        return False
    return not bool(observed.intersection(excluded))


def filter_scope(
    articles: Iterable[Article],
    *,
    collection: Collection,
    start: date,
    end: date,
) -> tuple[list[Article], dict[str, int]]:
    accepted: list[Article] = []
    counts = {
        "input": 0,
        "missing_date": 0,
        "outside_period": 0,
        "insufficient_date_precision": 0,
        "wrong_collection": 0,
        "excluded_type": 0,
        "accepted_before_dedup": 0,
    }
    for article in articles:
        counts["input"] += 1
        interval = publication_interval(
            article.publication_date,
            article.publication_date_precision,
        )
        if interval is None:
            counts["missing_date"] += 1
            continue
        interval_start, interval_end = interval
        if interval_end < start or interval_start > end:
            counts["outside_period"] += 1
            continue
        if interval_start < start or interval_end > end:
            counts["insufficient_date_precision"] += 1
            continue
        if not collection.matches(journal=article.journal, issns=article.issns):
            counts["wrong_collection"] += 1
            continue
        if not _type_allowed(article, collection):
            counts["excluded_type"] += 1
            continue
        accepted.append(article)
    counts["accepted_before_dedup"] = len(accepted)
    return accepted, counts


def _receipt_failure(source: str, exc: BaseException) -> SourceReceipt:
    return SourceReceipt(
        source=source,
        status="FAILED",
        query="adapter failed before a complete receipt could be produced",
        endpoint="unavailable",
        retrieved_at=utc_now_iso(),
        error=f"{type(exc).__name__}: {exc}",
    )


def _source_status(receipts: list[SourceReceipt]) -> str:
    statuses = {receipt.status for receipt in receipts}
    if statuses == {"FAILED"}:
        return "FAILED"
    if "FAILED" in statuses or any(receipt.metadata.get("truncated") is True for receipt in receipts):
        return "PARTIAL"
    return "COMPLETE"


def _edition_id(collection: Collection, start: date, end: date) -> str:
    if start.year == end.year and start.month == end.month and start.day == 1:
        if end.day == calendar.monthrange(end.year, end.month)[1]:
            return f"{collection.id}--{start:%Y-%m}"
    return f"{collection.id}--{start.isoformat()}--{end.isoformat()}"


def _bridge_for_options(options: BuildOptions) -> tuple[RadarReference, RadarNetworkBridge | None]:
    if options.radar_root is None:
        return declared_reference(), None
    bridge = inspect_radar_checkout(
        options.radar_root,
        allow_drift=options.allow_radar_drift,
    )
    return bridge.reference, bridge


def build_edition(options: BuildOptions) -> dict[str, Any]:
    if options.end < options.start:
        raise BuildError("end date must be on or after start date")
    if options.max_records_per_source < 1 or options.max_records_per_source > 100_000:
        raise BuildError("max_records_per_source must be between 1 and 100000")
    collection, collection_hash = load_collection(options.collection_path.resolve())
    selected_sources = options.sources or collection.default_sources
    unknown_sources = sorted(set(selected_sources).difference(SUPPORTED_SOURCES))
    if unknown_sources:
        raise BuildError(f"unsupported sources: {', '.join(unknown_sources)}")
    if len(selected_sources) != len(set(selected_sources)):
        raise BuildError("source selection contains duplicates")

    upstream_reference, bridge = _bridge_for_options(options)
    client = SafeHttpClient(bridge=bridge)
    receipts: list[SourceReceipt] = []
    raw_articles: list[Article] = []
    for source in selected_sources:
        try:
            result: SourceResult = fetch_source(
                source,
                collection,
                options.start,
                options.end,
                client=client,
                fixture_dir=options.fixture_dir.resolve() if options.fixture_dir else None,
                max_records=options.max_records_per_source,
            )
        except Exception as exc:  # adapter failures must become auditable receipts
            receipt = _receipt_failure(source, exc)
            receipts.append(receipt)
            if options.strict_sources:
                raise BuildError(f"source {source} failed: {exc}") from exc
            continue
        receipts.append(result.receipt)
        raw_articles.extend(result.articles)

    scoped_articles, exclusion_counts = filter_scope(
        raw_articles,
        collection=collection,
        start=options.start,
        end=options.end,
    )
    articles = deduplicate_articles(scoped_articles)
    status = _source_status(receipts)
    warnings: list[str] = []
    if status == "PARTIAL":
        if any(receipt.status == "FAILED" for receipt in receipts):
            warnings.append("One or more configured sources failed; the edition may be incomplete.")
        if any(receipt.metadata.get("truncated") is True for receipt in receipts):
            warnings.append(
                "One or more configured sources exceeded the record bound; the edition is partial."
            )
    elif status == "FAILED":
        warnings.append("All configured source operations failed; no completeness claim is made.")
    parse_drops = sum(
        int(receipt.metadata.get("parse_drop_count") or 0)
        for receipt in receipts
        if isinstance(receipt.metadata.get("parse_drop_count"), int)
    )
    if parse_drops:
        warnings.append(f"Source parsers skipped {parse_drops} returned records lacking usable structure.")
    if exclusion_counts["missing_date"]:
        warnings.append(
            f"Excluded {exclusion_counts['missing_date']} records without a parseable publication date."
        )
    if exclusion_counts["insufficient_date_precision"]:
        warnings.append(
            "Excluded "
            f"{exclusion_counts['insufficient_date_precision']} records whose date precision "
            "was too coarse for the requested period."
        )
    if options.fixture_dir:
        warnings.append("This edition was generated from deterministic test fixtures, not live sources.")

    retrieved_at = utc_now_iso()
    edition_id = _edition_id(collection, options.start, options.end)
    provenance = {
        "producer": {
            "repository": "hoiyu915-droid/EvidenceRadar-Editions",
            "version": "0.1.0",
        },
        "upstream_radar": upstream_reference.as_dict(),
        "collection_config_sha256": collection_hash,
        "artifact_dependency": False,
        "source_inputs": "direct-primary-source-query",
    }
    edition = {
        "schema_version": "1.0",
        "edition_id": edition_id,
        "status": status,
        "retrieved_at": retrieved_at,
        "data_semantics": "current-source reconstruction of historical publication window",
        "collection": collection.as_dict(),
        "period": {
            "start": options.start.isoformat(),
            "end": options.end.isoformat(),
            "inclusive": True,
            "timezone": options.timezone,
            "basis": "publication_date",
        },
        "article_count": len(articles),
        "raw_record_count": len(raw_articles),
        "scope_filter_counts": exclusion_counts,
        "articles": [article.as_dict() for article in articles],
        "warnings": warnings,
        "provenance": provenance,
    }
    sources_document = {
        "schema_version": "1.0",
        "edition_id": edition_id,
        "retrieved_at": retrieved_at,
        "receipts": [receipt.as_dict() for receipt in receipts],
    }
    report = render_edition(edition, sources_document)

    output_dir = options.output_dir.resolve()
    filesystem_root = Path(output_dir.anchor)
    if output_dir == filesystem_root or output_dir == Path.cwd().resolve():
        raise BuildError("refusing to use a filesystem root or current working directory as output")
    if output_dir.is_symlink():
        raise BuildError(f"refusing symlink output directory: {output_dir}")
    if output_dir.exists() and not output_dir.is_dir():
        raise BuildError(f"output path exists and is not a directory: {output_dir}")
    if output_dir.exists() and not options.replace:
        raise BuildError(f"output directory already exists: {output_dir}; use --replace intentionally")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=str(output_dir.parent)))
    try:
        atomic_write_bytes(temporary / "index.html", report.encode("utf-8"))
        atomic_write_json(temporary / "edition.json", edition)
        atomic_write_json(temporary / "sources.json", sources_document)
        manifest = {
            "schema_version": "1.0",
            "edition_id": edition_id,
            "created_at": retrieved_at,
            "status": status,
            "article_count": len(articles),
            "collection_config_sha256": collection_hash,
            "source_names": list(selected_sources),
            "upstream_radar": upstream_reference.as_dict(),
            "artifacts": [
                artifact_record(temporary / name, relative_to=temporary)
                for name in ("index.html", "edition.json", "sources.json")
            ],
        }
        atomic_write_json(temporary / "manifest.json", manifest)
        validation = validate_edition_directory(temporary)
        if output_dir.exists():
            backup = output_dir.with_name(
                f".{output_dir.name}.replaced-{hashlib.sha256(str(output_dir).encode()).hexdigest()[:8]}-"
                f"{secrets.token_hex(4)}"
            )
            output_dir.replace(backup)
            try:
                temporary.replace(output_dir)
            except BaseException:
                backup.replace(output_dir)
                raise
            shutil.rmtree(backup)
        else:
            temporary.replace(output_dir)
        return {
            **validation,
            "root": str(output_dir),
            "status": status,
            "output_dir": str(output_dir),
            "raw_record_count": len(raw_articles),
            "accepted_before_dedup": len(scoped_articles),
        }
    except BaseException:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
