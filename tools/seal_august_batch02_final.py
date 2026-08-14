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
PROBE = ROOT / "probe-final"
TRANSLATIONS = ROOT / "translation-final"
EDITIONS = ROOT / "editions"
CATALOG = ROOT / "catalog"
START = "2026-08-01"
END = "2026-08-14"

CARRIED = {
    "computers-in-human-behavior": 35,
    "neural-networks": 128,
    "the-lancet": 93,
}
NEW = {
    "nutrition": 38,
    "the-lancet-global-health": 38,
}
ALL_FIVE = {**CARRIED, **NEW}
EXCLUSIONS = {
    "doi:10.1016/s0899-9007(26)00188-7": "NON_ARTICLE_TABLE_OF_CONTENTS",
}


def load_probe_run(slug: str) -> dict:
    directory = PROBE / slug
    candidates = [
        p for p in directory.glob("*.json")
        if not p.name.endswith(".manifest.json") and "translation-" not in p.name
    ]
    if len(candidates) != 1:
        raise RuntimeError(f"{slug}: expected one probe edition JSON, got {candidates}")
    value = json.loads(candidates[0].read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{slug}: edition JSON is not an object")
    return value


def load_translation_map() -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted(TRANSLATIONS.glob("*.ndjson")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            row = json.loads(line)
            cid = str(row.get("canonical_id") or "").strip()
            title = str(row.get("title_zh_tw") or "").strip()
            if not cid or not title:
                raise RuntimeError(f"invalid translation row {path}:{number}")
            if cid in out:
                raise RuntimeError(f"duplicate translation: {cid}")
            out[cid] = title
    return out


def date_ok(article: dict) -> bool:
    precision = str(article.get("publication_date_precision") or "").upper()
    value = str(article.get("publication_date") or "")
    return (
        (precision == "DAY" and START <= value <= END)
        or (precision == "MONTH" and value.startswith("2026-08"))
    )


def recalc_counts(run: dict) -> None:
    articles = [a for a in (run.get("articles") or []) if isinstance(a, dict)]
    by_source: Counter[str] = Counter()
    by_type: Counter[str] = Counter()
    for article in articles:
        by_type[str(article.get("article_type") or "unspecified")] += 1
        seen = {
            str(r.get("source"))
            for r in (article.get("source_records") or [])
            if isinstance(r, dict) and r.get("source")
        }
        for source in seen:
            by_source[source] += 1
    run["counts"] = {
        "articles": len(articles),
        "translated_articles": 0,
        "by_source": dict(sorted(by_source.items())),
        "by_article_type": dict(sorted(by_type.items())),
    }
    statuses = [
        str(c.get("status") or "")
        for c in (run.get("source_checks") or [])
        if isinstance(c, dict) and c.get("source") != "radar_rss"
    ]
    if statuses and all(v == "FAILED" for v in statuses):
        run["run_status"] = "SOURCE_ACCESS_GAP"
    elif any(v in {"FAILED", "PARTIAL"} for v in statuses):
        run["run_status"] = "PARTIAL_SOURCE_COVERAGE"
    elif articles:
        run["run_status"] = "COMPLETE"
    else:
        run["run_status"] = "NO_MATCHING_ARTICLES"


def make_response(run: dict, translations: dict[str, str]) -> dict:
    request = build_translation_request(run)
    ids = {
        str(a.get("canonical_id"))
        for a in (run.get("articles") or [])
        if isinstance(a, dict) and a.get("canonical_id")
    }
    missing = sorted(ids - set(translations))
    if missing:
        raise RuntimeError(f"{run.get('edition_id')}: missing translations: {missing}")
    items = []
    for article in run.get("articles") or []:
        cid = str(article.get("canonical_id"))
        zh = translations[cid]
        items.append({
            "canonical_id": cid,
            "title_zh_tw": zh,
            "summary_zh_tw": (
                f"依題名，本篇聚焦於「{zh}」。目前僅以題名作為繁中導讀依據，"
                "未讀取摘要或全文，因此不推定研究方法、數值結果、效應大小或結論。"
            ),
            "basis": "TITLE_ONLY",
        })
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


def clean_and_translate(slug: str, translations: dict[str, str]) -> dict:
    run = load_probe_run(slug)
    raw = [a for a in (run.get("articles") or []) if isinstance(a, dict)]
    retained = []
    excluded = []
    for article in raw:
        cid = str(article.get("canonical_id") or "")
        if cid in EXCLUSIONS:
            excluded.append({
                "canonical_id": cid,
                "title": article.get("title_original") or article.get("title"),
                "reason": EXCLUSIONS[cid],
            })
            continue
        if not date_ok(article):
            raise RuntimeError(
                f"{slug}: unresolved date gate {cid}: "
                f"{article.get('publication_date')} / {article.get('publication_date_precision')}"
            )
        retained.append(article)
    run["articles"] = retained
    recalc_counts(run)
    run["publication_notes"] = {
        "editorial_projection": {
            "source_match_count": len(raw),
            "published_article_count": len(retained),
            "excluded_count": len(excluded),
            "excluded_records": excluded,
        },
        "date_gate": {
            "window_start": START,
            "window_end": END,
            "accepted_precisions": ["DAY", "MONTH"],
            "year_only_records_publishable": False,
        },
    }
    if len(retained) != NEW[slug]:
        raise RuntimeError(f"{slug}: expected {NEW[slug]} retained, got {len(retained)}")
    response = make_response(run, translations)
    enriched = apply_translation_response(run, response, require_complete=True)
    if int((enriched.get("counts") or {}).get("translated_articles") or 0) != NEW[slug]:
        raise RuntimeError(f"{slug}: translation coverage mismatch")
    return enriched


def verify_translation_ledger(translations: dict[str, str]) -> None:
    retained = set()
    excluded = set()
    for slug in NEW:
        run = load_probe_run(slug)
        for article in run.get("articles") or []:
            if not isinstance(article, dict):
                continue
            cid = str(article.get("canonical_id") or "")
            if cid in EXCLUSIONS:
                excluded.add(cid)
            else:
                retained.add(cid)
    missing = sorted(retained - set(translations))
    extras = sorted(set(translations) - retained)
    if missing or extras:
        raise RuntimeError(
            f"translation ledger mismatch missing={len(missing)} extras={len(extras)}"
        )
    if excluded != set(EXCLUSIONS):
        raise RuntimeError("exclusion ledger does not match probe identities")


def verify_carried() -> None:
    for slug, count in CARRIED.items():
        target = EDITIONS / slug / "2026" / "08" / "r01"
        errors = validate_stored_publication(target, require_zh_tw=True)
        if errors:
            raise RuntimeError(f"{slug}: carried canonical entry invalid:\n" + "\n".join(errors))
        edition = json.loads((target / "edition.json").read_text(encoding="utf-8"))
        observed = int((edition.get("counts") or {}).get("articles") or 0)
        translated = int((edition.get("counts") or {}).get("translated_articles") or 0)
        if observed != count or translated != count:
            raise RuntimeError(f"{slug}: carried count mismatch {observed}/{translated} != {count}")


def seal_new(slug: str, translations: dict[str, str], workspace: Path) -> None:
    run = clean_and_translate(slug, translations)
    bundle = workspace / slug
    write_bundle(run, bundle)
    errors = validate_bundle(bundle, require_zh_tw=True)
    if errors:
        raise RuntimeError(f"{slug}: bundle validation failed:\n" + "\n".join(errors))
    target = store_bundle(bundle, EDITIONS, require_zh_tw=True)
    stored_errors = validate_stored_publication(target, require_zh_tw=True)
    if stored_errors:
        raise RuntimeError(f"{slug}: stored validation failed:\n" + "\n".join(stored_errors))


def verify_pages(workspace: Path) -> None:
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
    observed = {
        str(e.get("journal_slug")): int(e.get("article_count") or 0)
        for e in entries
        if e.get("period_key") == "2026-08"
        and str(e.get("journal_slug")) in ALL_FIVE
        and int(e.get("revision") or 0) == 1
    }
    if observed != ALL_FIVE:
        raise RuntimeError(f"Pages batch counts mismatch: {observed!r}")
    if int(catalog.get("published_journal_count") or 0) != 15:
        raise RuntimeError(
            f"expected 15 published journals, got {catalog.get('published_journal_count')}"
        )
    if int(catalog.get("registered_journal_count") or 0) != 58:
        raise RuntimeError("registered journal count changed unexpectedly")
    indexed = int(search.get("article_count") or 0)
    if indexed < sum(ALL_FIVE.values()):
        raise RuntimeError(f"search index too small: {indexed}")
    for slug in ALL_FIVE:
        if not (site / "journals" / slug / "2026-08" / "r01" / "index.html").is_file():
            raise RuntimeError(f"missing Pages revision for {slug}")
    print(json.dumps({
        "batch_journals": len(ALL_FIVE),
        "batch_articles": sum(ALL_FIVE.values()),
        "published_journals": catalog.get("published_journal_count"),
        "registered_journals": catalog.get("registered_journal_count"),
        "search_articles": indexed,
        "batch_counts": observed,
    }, ensure_ascii=False, indent=2))


def main() -> None:
    translations = load_translation_map()
    verify_translation_ledger(translations)
    verify_carried()
    with tempfile.TemporaryDirectory(prefix="evidenceradar-batch02-final-") as tmp:
        workspace = Path(tmp)
        for slug in NEW:
            seal_new(slug, translations, workspace)
            print(f"sealed {slug}")
        verify_pages(workspace)
    if list(EDITIONS.glob("**/*.html")) or list(EDITIONS.glob("**/*.zip")):
        raise RuntimeError("presentation artifact leaked into canonical editions tree")


if __name__ == "__main__":
    main()
