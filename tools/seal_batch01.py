from __future__ import annotations

import json
import tempfile
from collections import Counter
from pathlib import Path

from evidenceradar_editions.bundle import write_bundle
from evidenceradar_editions.pages import build_pages_site
from evidenceradar_editions.store_v3 import store_bundle, validate_stored_publication
from evidenceradar_editions.translation import (
    TRANSLATION_RESPONSE_TYPE,
    apply_translation_response,
    build_translation_request,
)
from evidenceradar_editions.utils import utc_now_iso
from evidenceradar_editions.validate import validate_bundle

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "staging"
MAP_ROOT = STAGING / "batch01"
EDITIONS = ROOT / "editions"
CATALOG = ROOT / "catalog"

ACQUISITION_ROOTS = {
    "the-lancet-digital-health": STAGING / "acq" / "main" / "the-lancet-digital-health",
    "the-lancet-healthy-longevity": STAGING / "acq" / "main" / "the-lancet-healthy-longevity",
    "journal-of-science-and-medicine-in-sport": STAGING / "acq" / "main" / "journal-of-science-and-medicine-in-sport",
    "clinical-nutrition": STAGING / "acq" / "main" / "clinical-nutrition",
    "journal-of-exercise-science-and-fitness": STAGING / "acq" / "replacement" / "journal-of-exercise-science-and-fitness",
}

EXPECTED = {
    "the-lancet-digital-health": 7,
    "the-lancet-healthy-longevity": 11,
    "journal-of-science-and-medicine-in-sport": 24,
    "clinical-nutrition": 33,
    "journal-of-exercise-science-and-fitness": 6,
}


def title_of(article: dict) -> str:
    return str(article.get("title_original") or article.get("title") or "").strip()


def load_run(directory: Path) -> dict:
    candidates = [
        path
        for path in directory.glob("EvidenceRadar_Editions__*.json")
        if ".manifest." not in path.name and "translation-" not in path.name
    ]
    if len(candidates) != 1:
        raise RuntimeError(f"{directory}: expected one edition JSON, got {len(candidates)}")
    value = json.loads(candidates[0].read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{candidates[0]} must contain a JSON object")
    return value


def load_map(slug: str) -> dict:
    path = MAP_ROOT / f"{slug}.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("journal_slug") != slug:
        raise RuntimeError(f"invalid translation map: {path}")
    return value


def recalc_counts(run: dict) -> None:
    articles = run.get("articles") or []
    by_source: dict[str, set[str]] = {}
    by_type = Counter()
    for article in articles:
        canonical_id = str(article.get("canonical_id") or "")
        for record in article.get("source_records") or []:
            source = str(record.get("source") or "")
            if source:
                by_source.setdefault(source, set()).add(canonical_id)
        by_type[str(article.get("article_type") or "unspecified")] += 1
    run["counts"] = {
        "articles": len(articles),
        "translated_articles": 0,
        "by_source": {key: len(value) for key, value in sorted(by_source.items())},
        "by_article_type": dict(sorted(by_type.items())),
    }
    statuses = [
        str(check.get("status") or "")
        for check in (run.get("source_checks") or [])
        if isinstance(check, dict) and check.get("source") != "radar_rss"
    ]
    if statuses and all(status == "FAILED" for status in statuses):
        run["run_status"] = "SOURCE_ACCESS_GAP"
    elif any(status in {"FAILED", "PARTIAL"} for status in statuses):
        run["run_status"] = "PARTIAL_SOURCE_COVERAGE"
    elif articles:
        run["run_status"] = "COMPLETE"
    else:
        run["run_status"] = "NO_MATCHING_ARTICLES"


def apply_editorial_projection(run: dict, mapping: dict) -> None:
    exclude_titles = set(str(value) for value in mapping.get("exclude_titles") or [])
    exclude_precisions = {
        str(value).upper() for value in mapping.get("exclude_precisions") or []
    }
    kept: list[dict] = []
    excluded: list[dict] = []
    for article in run.get("articles") or []:
        title = title_of(article)
        precision = str(article.get("publication_date_precision") or "DAY").upper()
        reason = None
        if title in exclude_titles:
            reason = (
                "TEMPORARY_REMOVAL_PLACEHOLDER"
                if title.startswith("TEMPORARY REMOVAL:")
                else "NON_ARTICLE_FRONT_MATTER"
            )
        elif precision in exclude_precisions:
            reason = "INSUFFICIENT_DATE_PRECISION_FOR_MONTH"
        if reason:
            excluded.append(
                {
                    "canonical_id": article.get("canonical_id"),
                    "title": title,
                    "publication_date_precision": precision,
                    "reason": reason,
                }
            )
        else:
            kept.append(article)

    original_count = len(run.get("articles") or [])
    run["articles"] = kept
    recalc_counts(run)
    run["publication_notes"] = {
        "editorial_projection": {
            "source_match_count": original_count,
            "published_article_count": len(kept),
            "excluded_count": len(excluded),
            "excluded_records": excluded,
            "policy": (
                "Exclude temporary-removal/front-matter placeholders and records "
                "whose date precision is insufficient to assign them to the month."
            ),
        }
    }


def build_response(run: dict, mapping: dict) -> dict:
    translations = {
        str(key): str(value)
        for key, value in (mapping.get("translations") or {}).items()
    }
    request = build_translation_request(run)
    items = []
    missing = []
    for article in run.get("articles") or []:
        original = title_of(article)
        translated = translations.get(original)
        if not translated:
            missing.append(original)
            continue
        items.append(
            {
                "canonical_id": article["canonical_id"],
                "title_zh_tw": translated,
                "summary_zh_tw": (
                    f"依題名，本篇聚焦於「{translated}」。目前僅以題名作為繁中導讀依據，"
                    "未讀取摘要或全文，因此不推定研究方法、數值結果、效應大小或結論。"
                ),
                "basis": "TITLE_ONLY",
            }
        )
    if missing:
        raise RuntimeError(
            f"{run.get('edition_id')}: translation map missing {len(missing)} title(s):\n"
            + "\n".join(missing)
        )
    extras = sorted(set(translations) - {title_of(a) for a in run.get("articles") or []})
    if extras:
        raise RuntimeError(
            f"{run.get('edition_id')}: translation map contains {len(extras)} unexpected title(s):\n"
            + "\n".join(extras)
        )
    return {
        "schema_version": "1.0",
        "artifact_type": TRANSLATION_RESPONSE_TYPE,
        "edition_id": run["edition_id"],
        "request_id": request["request_id"],
        "language": "zh-TW",
        "source_edition_sha256": request["source_edition_sha256"],
        "request_binding_sha256": request["request_binding_sha256"],
        "generated_at": utc_now_iso(),
        "item_count": len(items),
        "items": items,
    }


def seal_one(slug: str, work_root: Path) -> Path:
    run = load_run(ACQUISITION_ROOTS[slug])
    mapping = load_map(slug)
    apply_editorial_projection(run, mapping)
    observed = len(run.get("articles") or [])
    if observed != EXPECTED[slug]:
        raise RuntimeError(f"{slug}: expected {EXPECTED[slug]} articles, got {observed}")

    response = build_response(run, mapping)
    enriched = apply_translation_response(run, response, require_complete=True)
    bundle = work_root / slug
    write_bundle(enriched, bundle)
    errors = validate_bundle(bundle, require_zh_tw=True)
    if errors:
        raise RuntimeError(f"{slug}: bundle validation failed:\n" + "\n".join(errors))

    target = store_bundle(bundle, EDITIONS, require_zh_tw=True)
    stored_errors = validate_stored_publication(target, require_zh_tw=True)
    if stored_errors:
        raise RuntimeError(
            f"{slug}: stored publication validation failed:\n" + "\n".join(stored_errors)
        )
    if list(target.glob("*.html")):
        raise RuntimeError(f"{slug}: HTML leaked into canonical storage")
    print(
        json.dumps(
            {
                "slug": slug,
                "articles": observed,
                "stored": str(target.relative_to(ROOT)),
            },
            ensure_ascii=False,
        )
    )
    return target


def verify_pages(work_root: Path) -> None:
    site = work_root / "site"
    links = build_pages_site(
        editions_root=EDITIONS,
        catalog_root=CATALOG,
        output_dir=site,
        repository="hoiyu915-droid/EvidenceRadar-Editions",
        base_url="https://hoiyu915-droid.github.io/EvidenceRadar-Editions/",
        require_zh_tw=True,
    )
    catalog = json.loads((site / "index.json").read_text(encoding="utf-8"))
    search = json.loads((site / "search-index.json").read_text(encoding="utf-8"))
    monthly = {
        str(entry.get("journal_slug")): int(entry.get("article_count") or 0)
        for entry in (catalog.get("latest_editions") or [])
        if entry.get("period_key") == "2026-08"
        and str(entry.get("journal_slug")) in EXPECTED
    }
    if monthly != EXPECTED:
        raise RuntimeError(f"Pages August batch mismatch: {monthly!r}")
    if int(catalog.get("published_journal_count") or 0) != 10:
        raise RuntimeError(
            f"expected 10 published journals, got {catalog.get('published_journal_count')}"
        )
    if int(catalog.get("registered_journal_count") or 0) != 58:
        raise RuntimeError(
            f"expected 58 registered journals, got {catalog.get('registered_journal_count')}"
        )
    if int(search.get("article_count") or 0) != 236:
        raise RuntimeError(
            f"expected 236 indexed articles after batch 01, got {search.get('article_count')}"
        )
    print(
        json.dumps(
            {
                "registered_journals": links.get("registered_journal_count"),
                "published_journals": links.get("published_journal_count"),
                "indexed_articles": search.get("article_count"),
                "batch_articles": sum(EXPECTED.values()),
            },
            ensure_ascii=False,
        )
    )


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="evidenceradar-batch01-") as tmp:
        work_root = Path(tmp)
        for slug in EXPECTED:
            seal_one(slug, work_root)
        verify_pages(work_root)


if __name__ == "__main__":
    main()
