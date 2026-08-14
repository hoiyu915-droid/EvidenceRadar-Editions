from __future__ import annotations

import json
import shutil
import tempfile
from collections import Counter
from pathlib import Path

from evidenceradar_editions.bundle import write_bundle
from evidenceradar_editions.pages import build_pages_site
from evidenceradar_editions.serialization import json_sha256
from evidenceradar_editions.store_v3 import store_bundle, validate_stored_publication
from evidenceradar_editions.translation import (
    TRANSLATION_RESPONSE_TYPE,
    apply_translation_response,
    build_translation_request,
)
from evidenceradar_editions.utils import utc_now_iso
from evidenceradar_editions.validate import validate_bundle

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "probe"
TRANSLATIONS = ROOT / "translation-work"
EDITIONS = ROOT / "editions"
CATALOG = ROOT / "catalog"
START = "2026-08-01"
END = "2026-08-14"

EXPECTED = {
    "clinical-nutrition": 33,
    "computers-in-human-behavior": 35,
    "journal-of-science-and-medicine-in-sport": 24,
    "neural-networks": 128,
    "the-lancet": 93,
}

EXCLUSIONS = {
    "doi:10.1016/s0747-5632(26)00110-x": "NON_ARTICLE_EDITORIAL_BOARD",
    "doi:10.1016/s1440-2440(26)00295-1": "NON_ARTICLE_EDITORIAL_BOARD",
    "doi:10.1016/s0893-6080(26)00581-2": "NON_ARTICLE_EDITORIAL_BOARD",
    "doi:10.1016/j.clnu.2026.106749": "INSUFFICIENT_PUBLICATION_DATE_PRECISION",
    "doi:10.1016/j.jsams.2026.08.201": "TEMPORARY_REMOVAL",
    "doi:10.1016/s0893-6080(26)00584-8": "NON_ARTICLE_MEMBERSHIP_FORM",
    "doi:10.1016/s0893-6080(26)00583-6": "NON_ARTICLE_CURRENT_EVENTS",
}


def title_of(article: dict) -> str:
    return str(article.get("title_original") or article.get("title") or "").strip()


def load_translation_map() -> dict[str, str]:
    values: dict[str, str] = {}
    for path in sorted(TRANSLATIONS.glob("batch02.part*.ndjson")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            row = json.loads(line)
            canonical_id = str(row.get("canonical_id") or "").strip()
            title = str(row.get("title_zh_tw") or "").strip()
            if not canonical_id or not title:
                raise RuntimeError(f"invalid translation row: {path}:{number}")
            if canonical_id in values:
                raise RuntimeError(f"duplicate translation: {canonical_id}")
            values[canonical_id] = title
    return values


def load_probe_run(slug: str) -> dict:
    directory = PROBE / slug
    candidates = [
        p
        for p in directory.glob("*.json")
        if not p.name.endswith(".manifest.json") and "translation-" not in p.name
    ]
    if len(candidates) != 1:
        raise RuntimeError(f"{slug}: expected one probe edition JSON, got {candidates}")
    run = json.loads(candidates[0].read_text(encoding="utf-8"))
    if not isinstance(run, dict):
        raise RuntimeError(f"{slug}: probe edition is not an object")
    return run


def date_is_publishable(article: dict) -> bool:
    precision = str(article.get("publication_date_precision") or "").upper()
    value = str(article.get("publication_date") or "")
    if precision == "DAY":
        return START <= value <= END
    if precision == "MONTH":
        return value.startswith("2026-08")
    return False


def recalc_counts(run: dict) -> None:
    articles = [a for a in (run.get("articles") or []) if isinstance(a, dict)]
    source_counts: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()
    for article in articles:
        type_counts[str(article.get("article_type") or "unspecified")] += 1
        seen_sources = {
            str(record.get("source"))
            for record in (article.get("source_records") or [])
            if isinstance(record, dict) and record.get("source")
        }
        for source in seen_sources:
            source_counts[source] += 1
    run["counts"] = {
        "articles": len(articles),
        "translated_articles": 0,
        "by_source": dict(sorted(source_counts.items())),
        "by_article_type": dict(sorted(type_counts.items())),
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


def make_response(run: dict, translations: dict[str, str]) -> dict:
    request = build_translation_request(run)
    retained = {
        str(article.get("canonical_id"))
        for article in run.get("articles") or []
        if isinstance(article, dict) and article.get("canonical_id")
    }
    missing = sorted(retained - set(translations))
    if missing:
        raise RuntimeError(
            f"{run.get('edition_id')}: missing {len(missing)} translation(s):\n"
            + "\n".join(missing)
        )
    items = []
    for article in run.get("articles") or []:
        canonical_id = str(article.get("canonical_id"))
        zh = translations[canonical_id]
        items.append(
            {
                "canonical_id": canonical_id,
                "title_zh_tw": zh,
                "summary_zh_tw": (
                    f"依題名，本篇聚焦於「{zh}」。目前僅以題名作為繁中導讀依據，"
                    "未讀取摘要或全文，因此不推定研究方法、數值結果、效應大小或結論。"
                ),
                "basis": "TITLE_ONLY",
            }
        )
    return {
        "schema_version": "1.0",
        "artifact_type": TRANSLATION_RESPONSE_TYPE,
        "edition_id": run.get("edition_id"),
        "request_id": request.get("request_id"),
        "language": "zh-TW",
        "source_edition_sha256": request.get("source_edition_sha256"),
        "request_binding_sha256": request.get("request_binding_sha256"),
        "generated_at": utc_now_iso(),
        "item_count": len(items),
        "items": items,
    }


def clean_run(slug: str, translations: dict[str, str]) -> dict:
    run = load_probe_run(slug)
    raw_articles = [a for a in (run.get("articles") or []) if isinstance(a, dict)]
    excluded_records = []
    retained = []
    for article in raw_articles:
        canonical_id = str(article.get("canonical_id") or "")
        reason = EXCLUSIONS.get(canonical_id)
        if reason:
            excluded_records.append(
                {
                    "canonical_id": canonical_id,
                    "title": title_of(article),
                    "reason": reason,
                }
            )
            continue
        if not date_is_publishable(article):
            raise RuntimeError(
                f"{slug}: unresolved publication date gate for {canonical_id}: "
                f"{article.get('publication_date')} / {article.get('publication_date_precision')}"
            )
        retained.append(article)
    run["articles"] = retained
    recalc_counts(run)
    run["publication_notes"] = {
        "editorial_projection": {
            "source_match_count": len(raw_articles),
            "published_article_count": len(retained),
            "excluded_count": len(excluded_records),
            "excluded_records": excluded_records,
        },
        "date_gate": {
            "window_start": START,
            "window_end": END,
            "accepted_precisions": ["DAY", "MONTH"],
            "year_only_records_publishable": False,
        },
    }
    expected = EXPECTED[slug]
    if len(retained) != expected:
        raise RuntimeError(f"{slug}: expected {expected} retained article(s), got {len(retained)}")
    response = make_response(run, translations)
    enriched = apply_translation_response(run, response, require_complete=True)
    if int((enriched.get("counts") or {}).get("translated_articles") or 0) != expected:
        raise RuntimeError(f"{slug}: translation coverage mismatch")
    return enriched


def seal_one(slug: str, translations: dict[str, str], workspace: Path) -> Path:
    enriched = clean_run(slug, translations)
    bundle = workspace / slug
    write_bundle(enriched, bundle)
    errors = validate_bundle(bundle, require_zh_tw=True)
    if errors:
        raise RuntimeError(f"{slug}: bundle validation failed:\n" + "\n".join(errors))
    target = store_bundle(bundle, EDITIONS, require_zh_tw=True)
    stored_errors = validate_stored_publication(target, require_zh_tw=True)
    if stored_errors:
        raise RuntimeError(f"{slug}: canonical validation failed:\n" + "\n".join(stored_errors))
    if list(target.glob("*.html")):
        raise RuntimeError(f"{slug}: HTML leaked into canonical store")
    return target


def verify_translation_ledger(translations: dict[str, str]) -> None:
    retained_ids = set()
    excluded_ids = set()
    for slug in EXPECTED:
        run = load_probe_run(slug)
        for article in run.get("articles") or []:
            if not isinstance(article, dict):
                continue
            canonical_id = str(article.get("canonical_id") or "")
            if canonical_id in EXCLUSIONS:
                excluded_ids.add(canonical_id)
            else:
                retained_ids.add(canonical_id)
    missing = sorted(retained_ids - set(translations))
    extras = sorted(set(translations) - retained_ids)
    if missing or extras:
        raise RuntimeError(
            f"translation ledger mismatch: missing={len(missing)} extras={len(extras)}\n"
            + ("missing:\n" + "\n".join(missing) + "\n" if missing else "")
            + ("extras:\n" + "\n".join(extras) if extras else "")
        )
    if excluded_ids != set(EXCLUSIONS):
        raise RuntimeError("exclusion ledger does not match probe identities")


def verify_site(workspace: Path) -> None:
    site = workspace / "site"
    build_pages_site(
        editions_root=EDITIONS,
        catalog_root=CATALOG,
        output_dir=site,
        repository="hoiyu915-droid/EvidenceRadar-Editions",
        base_url="https://hoiyu915-droid.github.io/EvidenceRadar-Editions/",
        require_zh_tw=True,
    )
    catalog = json.loads((site / "index.json").read_text(encoding="utf-8"))
    search = json.loads((site / "search-index.json").read_text(encoding="utf-8"))
    entries = catalog.get("editions") or []
    monthly = {
        str(entry.get("journal_slug")): int(entry.get("article_count") or 0)
        for entry in entries
        if entry.get("period_key") == "2026-08"
        and entry.get("journal_slug") in EXPECTED
        and int(entry.get("revision") or 0) == 1
    }
    if monthly != EXPECTED:
        raise RuntimeError(f"Pages batch 02 monthly counts mismatch: {monthly!r}")
    if int(catalog.get("registered_journal_count") or 0) != 58:
        raise RuntimeError("Pages registry count changed unexpectedly")
    if int(catalog.get("published_journal_count") or 0) != 10:
        raise RuntimeError(
            f"expected 10 published journals, got {catalog.get('published_journal_count')}"
        )
    if int(search.get("article_count") or 0) != 468:
        raise RuntimeError(
            f"expected 468 indexed articles after batch 02, got {search.get('article_count')}"
        )
    for slug in EXPECTED:
        path = site / "journals" / slug / "2026-08" / "r01" / "index.html"
        if not path.is_file():
            raise RuntimeError(f"missing Pages revision HTML: {path}")
    print(
        json.dumps(
            {
                "batch_articles": sum(EXPECTED.values()),
                "published_journals": catalog.get("published_journal_count"),
                "registered_journals": catalog.get("registered_journal_count"),
                "search_articles": search.get("article_count"),
                "new_monthly_counts": monthly,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> None:
    translations = load_translation_map()
    verify_translation_ledger(translations)
    with tempfile.TemporaryDirectory(prefix="evidenceradar-batch02-") as tmp:
        workspace = Path(tmp)
        for slug in EXPECTED:
            target = seal_one(slug, translations, workspace)
            print(f"sealed {slug}: {target.relative_to(ROOT)}")
        verify_site(workspace)
    if list(EDITIONS.glob("**/*.html")):
        raise RuntimeError("canonical editions tree contains HTML")


if __name__ == "__main__":
    main()
