from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from .bundle import artifact_names, load_bundle_paths
from .models import ALLOWED_SOURCE_STATUSES
from .naming import build_identity
from .render import render_html
from .translation import ALLOWED_BASES
from .utils import (
    ALLOWED_DATE_PRECISIONS,
    contains_cjk,
    normalize_doi,
    period_overlaps,
    safe_http_metadata_url,
    sha256_file,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _translation_complete(article: dict[str, Any]) -> bool:
    return bool(article.get("title_zh_tw") and article.get("summary_zh_tw"))


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _check_inside(root: Path, path: Path) -> bool:
    try:
        path.resolve(strict=True).relative_to(root.resolve(strict=True))
        return True
    except (OSError, ValueError):
        return False


def _validate_source_checks(
    run: dict[str, Any], errors: list[str]
) -> None:
    scope = run.get("scope") or {}
    requested = [str(value) for value in (scope.get("sources") or [])]
    raw_checks = run.get("source_checks") or []
    if not isinstance(raw_checks, list):
        errors.append("source_checks must be a list")
        return
    checks = [value for value in raw_checks if isinstance(value, dict)]
    if len(checks) != len(raw_checks):
        errors.append("source_checks contains a non-object")
    observed = [str(check.get("source") or "") for check in checks]
    if len(observed) != len(set(observed)):
        errors.append("source_checks contains duplicate sources")
    if observed != requested:
        errors.append("source_checks must exactly follow scope.sources order")
    for check in checks:
        source = str(check.get("source") or "")
        status = str(check.get("status") or "")
        if status not in ALLOWED_SOURCE_STATUSES:
            errors.append(f"unsupported source status for {source}: {status}")
        try:
            returned = int(check.get("returned_count") or 0)
            accepted = int(check.get("accepted_count") or 0)
        except (TypeError, ValueError):
            errors.append(f"source counts are not integers: {source}")
            continue
        if returned < 0 or accepted < 0 or accepted > returned:
            errors.append(f"invalid source counts: {source}")
        total = check.get("total_available")
        if total is not None:
            try:
                total_value = int(total)
            except (TypeError, ValueError):
                errors.append(f"source total_available is not an integer: {source}")
            else:
                if total_value < returned:
                    errors.append(f"source total_available is below returned_count: {source}")
        truncated = check.get("truncated") is True
        if status == "PARTIAL" and not truncated:
            errors.append(f"PARTIAL source must set truncated=true: {source}")
        if truncated and status != "PARTIAL":
            errors.append(f"truncated source must use PARTIAL status: {source}")
        if status == "NO_RESULTS" and returned != 0:
            errors.append(f"NO_RESULTS source returned records: {source}")
        if status in {"SUCCESS", "PARTIAL"} and returned == 0:
            errors.append(f"{status} source returned zero records: {source}")
        if not str(check.get("query") or "").strip():
            errors.append(f"source check lacks query: {source}")
    active = [
        str(check.get("status") or "")
        for check in checks
        if str(check.get("source") or "") != "radar_rss"
    ]
    if not active:
        errors.append("at least one active bibliographic source is required")
    elif all(status in {"FAILED", "NOT_ATTEMPTED"} for status in active):
        errors.append("all active bibliographic sources failed or were not attempted")


def _validate_identity(run: dict[str, Any], errors: list[str]) -> None:
    scope = run.get("scope") or {}
    try:
        identity = build_identity(
            slug=str(scope.get("slug") or ""),
            start=date.fromisoformat(str(scope.get("start_date") or "")),
            end=date.fromisoformat(str(scope.get("end_date") or "")),
            period_kind_requested=str(
                scope.get("period_kind_requested") or scope.get("period_kind") or "auto"
            ),
            revision=int(scope.get("revision") or 0),
        )
    except Exception as exc:
        errors.append(f"edition identity is invalid: {exc}")
        return
    expected = identity.to_dict()
    for key in (
        "journal_slug",
        "period_kind",
        "period_key",
        "revision",
        "edition_key",
        "publication_id",
        "artifact_stem",
    ):
        if scope.get(key) != expected[key]:
            errors.append(f"scope identity mismatch: {key}")
    if run.get("edition_id") != identity.publication_id:
        errors.append("edition_id does not match journal/period/revision")
    if run.get("edition_key") != identity.edition_key:
        errors.append("edition_key does not match journal/period")
    if run.get("publication_id") != identity.publication_id:
        errors.append("publication_id mismatch")


def _validate_articles(
    run: dict[str, Any],
    *,
    require_zh_tw: bool,
    errors: list[str],
) -> tuple[list[dict[str, Any]], int]:
    raw_articles = run.get("articles") or []
    if not isinstance(raw_articles, list):
        errors.append("articles must be a list")
        return [], 0
    articles = [value for value in raw_articles if isinstance(value, dict)]
    if len(articles) != len(raw_articles):
        errors.append("articles contains a non-object")
    if (run.get("counts") or {}).get("articles") != len(articles):
        errors.append("article count mismatch")
    ids = [str(article.get("canonical_id") or "") for article in articles]
    if any(not value for value in ids):
        errors.append("article lacks canonical_id")
    if len(ids) != len(set(ids)):
        errors.append("duplicate canonical IDs")
    scope = run.get("scope") or {}
    try:
        start = date.fromisoformat(str(scope.get("start_date") or ""))
        end = date.fromisoformat(str(scope.get("end_date") or ""))
    except ValueError:
        errors.append("scope dates are invalid")
        return articles, 0

    translated_count = 0
    by_source: defaultdict[str, set[str]] = defaultdict(set)
    by_type: Counter[str] = Counter()
    for article in articles:
        canonical_id = str(article.get("canonical_id") or "")
        try:
            published = date.fromisoformat(str(article.get("publication_date") or ""))
        except ValueError:
            errors.append(f"invalid publication date: {canonical_id}")
            continue
        precision = str(article.get("publication_date_precision") or "DAY").upper()
        if precision not in ALLOWED_DATE_PRECISIONS:
            errors.append(f"invalid publication-date precision: {canonical_id}")
        elif not period_overlaps(published, precision, start, end):
            errors.append(f"article outside period: {canonical_id}")
        doi = article.get("doi")
        if doi and normalize_doi(str(doi)) != doi:
            errors.append(f"DOI is not normalized: {doi}")
        source_records = article.get("source_records") or []
        if not isinstance(source_records, list) or not source_records:
            errors.append(f"article lacks source_records: {canonical_id}")
            source_records = []
        for record in source_records:
            if not isinstance(record, dict):
                errors.append(f"malformed source record: {canonical_id}")
                continue
            source = str(record.get("source") or "")
            if not source:
                errors.append(f"source record lacks source: {canonical_id}")
            else:
                by_source[source].add(canonical_id)
            url = record.get("url")
            if url and safe_http_metadata_url(str(url)) != url:
                errors.append(f"unsafe source URL: {canonical_id}")
        article_type = str(article.get("article_type") or "unspecified")
        by_type[article_type] += 1

        if _translation_complete(article):
            translated_count += 1
            if article.get("translation_status") != "COMPLETE":
                errors.append(
                    f"translated article lacks COMPLETE status: {canonical_id}"
                )
            basis = str(article.get("translation_basis") or "").upper()
            if basis not in ALLOWED_BASES:
                errors.append(f"translated article has invalid basis: {canonical_id}")
            source_url = article.get("translation_source_url")
            if basis != "TITLE_ONLY":
                if not source_url:
                    errors.append(
                        f"translation basis {basis} lacks source URL: {canonical_id}"
                    )
                elif safe_http_metadata_url(str(source_url)) != source_url:
                    errors.append(f"unsafe translation source URL: {canonical_id}")
                elif source_url not in set(article.get("urls") or []):
                    errors.append(
                        f"translation source URL is not article-bound: {canonical_id}"
                    )
            if require_zh_tw:
                if not contains_cjk(str(article.get("title_zh_tw") or "")):
                    errors.append(f"translated title lacks CJK text: {canonical_id}")
                if not contains_cjk(str(article.get("summary_zh_tw") or "")):
                    errors.append(f"translated summary lacks CJK text: {canonical_id}")
        elif require_zh_tw:
            errors.append(f"missing zh-TW content: {canonical_id}")

    counts = run.get("counts") or {}
    expected_by_source = {
        key: len(value) for key, value in sorted(by_source.items())
    }
    if counts.get("by_source") != expected_by_source:
        errors.append("counts.by_source mismatch")
    if counts.get("by_article_type") != dict(sorted(by_type.items())):
        errors.append("counts.by_article_type mismatch")
    if counts.get("translated_articles", 0) != translated_count:
        errors.append("translated article count mismatch")
    return articles, translated_count


def _validate_translation(
    run: dict[str, Any],
    *,
    article_count: int,
    translated_count: int,
    require_zh_tw: bool,
    errors: list[str],
) -> str:
    translation = run.get("translation") or {}
    if not isinstance(translation, dict):
        errors.append("translation must be an object")
        return ""
    has_response = bool(translation.get("response_sha256"))
    if article_count == 0:
        expected_status = "NOT_REQUIRED"
    elif translated_count == article_count:
        expected_status = "COMPLETE"
    elif translated_count or has_response:
        expected_status = "PARTIAL"
    else:
        expected_status = "NOT_REQUESTED"
    observed_status = str(translation.get("status") or "NOT_REQUESTED")
    if observed_status != expected_status:
        errors.append(
            f"translation status mismatch: {observed_status} != {expected_status}"
        )
    if translation.get("language") != "zh-TW":
        errors.append("translation language must be zh-TW")
    if translation.get("translated_articles", 0) != translated_count:
        errors.append("translation.translated_articles mismatch")
    if translation.get("total_articles", article_count) != article_count:
        errors.append("translation.total_articles mismatch")
    if observed_status in {"COMPLETE", "PARTIAL"}:
        for key in (
            "source_edition_sha256",
            "request_binding_sha256",
            "response_sha256",
        ):
            if not _is_sha256(translation.get(key)):
                errors.append(f"translation provenance lacks valid {key}")
    if require_zh_tw and article_count and observed_status != "COMPLETE":
        errors.append("publication requires COMPLETE zh-TW translation")
    return observed_status


def _validate_run_status(run: dict[str, Any], errors: list[str]) -> None:
    checks = [
        value
        for value in (run.get("source_checks") or [])
        if isinstance(value, dict) and value.get("source") != "radar_rss"
    ]
    statuses = [str(value.get("status") or "") for value in checks]
    articles = run.get("articles") or []
    if statuses and all(status == "FAILED" for status in statuses):
        expected = "SOURCE_ACCESS_GAP"
    elif any(status in {"FAILED", "PARTIAL"} for status in statuses):
        expected = "PARTIAL_SOURCE_COVERAGE"
    elif articles:
        expected = "COMPLETE"
    else:
        expected = "NO_MATCHING_ARTICLES"
    if run.get("run_status") != expected:
        errors.append(f"run_status mismatch: {run.get('run_status')} != {expected}")


def _validate_manifest_and_render(
    root: Path,
    run: dict[str, Any],
    manifest: dict[str, Any],
    paths: Any,
    *,
    article_count: int,
    translated_count: int,
    translation_status: str,
    errors: list[str],
) -> None:
    files = manifest.get("files") or {}
    if not isinstance(files, dict):
        errors.append("manifest files must be an object")
        files = {}
    role_paths = {"edition_json": paths.json_path, "report_html": paths.html_path}
    for role, path in role_paths.items():
        entry = files.get(role) or {}
        if not isinstance(entry, dict):
            errors.append(f"manifest file record is malformed: {role}")
            continue
        if entry.get("name") != path.name:
            errors.append(f"manifest filename mismatch: {role}")
        if entry.get("sha256") != sha256_file(path):
            errors.append(f"manifest SHA256 mismatch: {role}")
        if entry.get("bytes") != path.stat().st_size:
            errors.append(f"manifest byte-size mismatch: {role}")
    expected_names = artifact_names(run)
    if paths.json_path.name != expected_names["edition_json"]:
        errors.append("edition JSON filename does not match edition identity")
    if paths.html_path.name != expected_names["report_html"]:
        errors.append("report HTML filename does not match edition identity")
    if paths.manifest_path.name != expected_names["manifest_json"]:
        errors.append("manifest filename does not match edition identity")
    if manifest.get("manifest_name") != paths.manifest_path.name:
        errors.append("manifest_name mismatch")
    if manifest.get("edition_id") != run.get("edition_id"):
        errors.append("manifest edition id mismatch")
    if manifest.get("edition_key") != run.get("edition_key"):
        errors.append("manifest edition key mismatch")
    if manifest.get("publication_id") != run.get("publication_id"):
        errors.append("manifest publication id mismatch")
    if manifest.get("article_count") != article_count:
        errors.append("manifest article count mismatch")
    if manifest.get("translated_article_count", 0) != translated_count:
        errors.append("manifest translated article count mismatch")
    if manifest.get("translation_status") != translation_status:
        errors.append("manifest translation status mismatch")
    if manifest.get("publication_language") != "zh-TW":
        errors.append("manifest publication language must be zh-TW")
    if manifest.get("run_status") != run.get("run_status"):
        errors.append("manifest run status mismatch")

    canonical_html = render_html(run)
    if paths.html_path.read_text(encoding="utf-8") != canonical_html:
        errors.append("HTML is not the canonical projection of edition JSON")
    if '<html lang="zh-Hant">' not in canonical_html:
        errors.append("HTML language is not zh-Hant")
    if "<script src=" in canonical_html or "<link rel=\"stylesheet\"" in canonical_html:
        errors.append("edition HTML must be self-contained")
    for control_id in (
        "filter-query",
        "filter-type",
        "filter-source",
        "filter-date",
        "filter-doi",
        "filter-pmid",
        "filter-pmcid",
        "filter-translated",
        "filter-sort",
        "clear-filters",
        "toggle-details",
    ):
        if f'id="{control_id}"' not in canonical_html:
            errors.append(f"interactive filter is missing: {control_id}")


def validate_bundle(root: Path, *, require_zh_tw: bool = False) -> list[str]:
    errors: list[str] = []
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        return [f"bundle root is missing or unsafe: {root}"]
    try:
        paths = load_bundle_paths(root)
    except Exception as exc:
        return [f"bundle discovery failed: {exc}"]
    for path in (paths.json_path, paths.html_path, paths.manifest_path):
        if path.is_symlink() or not path.is_file() or not _check_inside(root, path):
            errors.append(f"missing or unsafe artifact: {path.name}")
    if errors:
        return errors
    try:
        run = json.loads(paths.json_path.read_text(encoding="utf-8"))
        manifest = paths.manifest
    except Exception as exc:
        return [f"bundle parse failed: {exc}"]
    if not isinstance(run, dict):
        return ["edition JSON must be an object"]
    if run.get("schema_version") != "2.0":
        errors.append("edition schema_version must be 2.0")
    if manifest.get("schema_version") != "2.0":
        errors.append("manifest schema_version must be 2.0")
    upstream = run.get("upstream_radar") or {}
    if not isinstance(upstream, dict):
        errors.append("upstream_radar must be an object")
    elif upstream.get("uses_radar_output_artifacts") is not False:
        errors.append("uses_radar_output_artifacts must be false")

    _validate_identity(run, errors)
    _validate_source_checks(run, errors)
    _validate_run_status(run, errors)
    articles, translated_count = _validate_articles(
        run, require_zh_tw=require_zh_tw, errors=errors
    )
    translation_status = _validate_translation(
        run,
        article_count=len(articles),
        translated_count=translated_count,
        require_zh_tw=require_zh_tw,
        errors=errors,
    )
    _validate_manifest_and_render(
        root,
        run,
        manifest,
        paths,
        article_count=len(articles),
        translated_count=translated_count,
        translation_status=translation_status,
        errors=errors,
    )
    return errors
