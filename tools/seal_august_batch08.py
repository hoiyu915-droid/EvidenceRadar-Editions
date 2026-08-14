from __future__ import annotations

import json
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from evidenceradar_editions.bundle import write_bundle
from evidenceradar_editions.pages_v5 import build_pages_site
from evidenceradar_editions.serialization import json_text
from evidenceradar_editions.store_v3 import store_bundle, validate_stored_publication
from evidenceradar_editions.translation import (
    TRANSLATION_RESPONSE_TYPE,
    apply_translation_response,
    build_translation_request,
)
from evidenceradar_editions.utils import contains_cjk, utc_now_iso
from evidenceradar_editions.validate import validate_bundle

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "translation-work" / "batch08"
EDITIONS = ROOT / "editions"
CATALOG = ROOT / "catalog"

EXPECTED_COUNTS = {
    "expert-systems-with-applications": 292,
    "science-advances": 127,
    "scientific-data": 115,
    "nature-communications": 465,
    "scientific-reports": 1888,
}
PROBE_DIRS = {
    "expert-systems-with-applications": ROOT / "probe" / "batch08-selected" / "expert-systems-with-applications",
    "science-advances": ROOT / "probe" / "batch08-selected" / "science-advances",
    "scientific-data": ROOT / "probe" / "batch08-selected" / "scientific-data",
    "nature-communications": ROOT / "probe" / "batch08-replacements" / "nature-communications",
    "scientific-reports": ROOT / "probe" / "batch08-replacements" / "scientific-reports",
}
EXCLUDED_IDS = {"doi:10.1016/s0957-4174(26)02087-7"}
REGISTRY_UPDATES = {
    "science-advances": ("2375-2548", ["crossref"]),
    "scientific-data": ("2052-4463", ["crossref"]),
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def recompute_counts(run: dict) -> None:
    articles = run.get("articles") or []
    by_source: dict[str, set[str]] = defaultdict(set)
    by_type = Counter()
    for article in articles:
        cid = str(article.get("canonical_id") or "")
        by_type[str(article.get("article_type") or "unknown")] += 1
        for record in article.get("source_records") or []:
            source = str(record.get("source") or "")
            if source:
                by_source[source].add(cid)
    run["counts"] = {
        "articles": len(articles),
        "translated_articles": 0,
        "by_source": {k: len(v) for k, v in sorted(by_source.items())},
        "by_article_type": dict(sorted(by_type.items())),
    }
    run["translation"] = {
        "language": "zh-TW",
        "status": "NOT_REQUESTED",
        "translated_articles": 0,
        "total_articles": len(articles),
        "source_edition_sha256": None,
        "request_binding_sha256": None,
        "response_sha256": None,
    }


def load_translation_ledger() -> dict[str, dict]:
    payload = load_json(WORK / "google-full-ledger.json")
    if payload.get("language") != "zh-TW" or int(payload.get("item_count") or 0) != 2887:
        raise ValueError("batch08 full translation ledger identity/count mismatch")
    if "translate.googleapis.com" not in str(payload.get("engine") or ""):
        raise ValueError("batch08 full translation ledger is not the accepted engine")
    rows: dict[str, dict] = {}
    for row in payload.get("items") or []:
        cid = str(row.get("canonical_id") or "").strip()
        title = str(row.get("title_zh_tw") or "").strip()
        if not cid or not title:
            raise ValueError(f"incomplete translation row: {cid!r}")
        if cid in rows:
            raise ValueError(f"duplicate translation id: {cid}")
        if not contains_cjk(title):
            raise ValueError(f"translated title lacks CJK text: {cid}")
        rows[cid] = row
    if len(rows) != 2887:
        raise ValueError(f"translation ledger count mismatch: {len(rows)}")
    flags = load_json(WORK / "google-quality-flags.json")
    flagged = flags.get("items") or []
    if len(flagged) != 1 or str(flagged[0].get("canonical_id")) != "doi:10.1038/s41598-026-64721-3":
        raise ValueError("batch08 quality flag set changed; requires renewed review")
    # This lone flag is a detector false positive caused by the repeated zeroes in HAM10000.
    return rows


def activate_registry() -> None:
    path = CATALOG / "journals.json"
    registry = load_json(path)
    seen = set()
    for journal in registry.get("journals") or []:
        slug = str(journal.get("slug") or "")
        if slug not in REGISTRY_UPDATES:
            continue
        issn, sources = REGISTRY_UPDATES[slug]
        journal["issn"] = issn
        journal["sources"] = list(sources)
        journal["status"] = "active"
        journal.pop("enabled", None)
        seen.add(slug)
    missing = sorted(set(REGISTRY_UPDATES) - seen)
    if missing:
        raise ValueError(f"registry journals missing: {missing}")
    path.write_text(json_text(registry), encoding="utf-8")


def main() -> None:
    ledger = load_translation_ledger()
    expected_ids: set[str] = set()
    sealed_dirs: list[Path] = []

    with tempfile.TemporaryDirectory(prefix="batch08-seal-") as tmp:
        tmp_root = Path(tmp)
        for slug, expected_count in EXPECTED_COUNTS.items():
            run = load_json(PROBE_DIRS[slug] / "edition.json")
            run["articles"] = [
                article for article in (run.get("articles") or [])
                if str(article.get("canonical_id") or "") not in EXCLUDED_IDS
            ]
            if len(run["articles"]) != expected_count:
                raise ValueError(f"{slug}: filtered count {len(run['articles'])} != {expected_count}")
            ids = {str(article.get("canonical_id") or "") for article in run["articles"]}
            if len(ids) != expected_count:
                raise ValueError(f"{slug}: duplicate canonical ids after filtering")
            expected_ids.update(ids)
            recompute_counts(run)

            request = build_translation_request(run)
            response_items = []
            for article in run["articles"]:
                cid = str(article["canonical_id"])
                row = ledger.get(cid)
                if row is None:
                    raise ValueError(f"{slug}: missing translation {cid}")
                title_zh = str(row["title_zh_tw"]).strip()
                response_items.append({
                    "canonical_id": cid,
                    "title_zh_tw": title_zh,
                    "summary_zh_tw": (
                        f"依題名，本篇文獻聚焦於「{title_zh}」。"
                        "目前僅以題名作為繁中導讀依據，未讀取摘要或全文，"
                        "因此不推定研究設計、數值結果、效應大小或結論。"
                    ),
                    "basis": "TITLE_ONLY",
                    "source_url": None,
                })
            response = {
                "schema_version": "1.0",
                "artifact_type": TRANSLATION_RESPONSE_TYPE,
                "edition_id": run["edition_id"],
                "request_id": request["request_id"],
                "language": "zh-TW",
                "source_edition_sha256": request["source_edition_sha256"],
                "request_binding_sha256": request["request_binding_sha256"],
                "generated_at": utc_now_iso(),
                "item_count": len(response_items),
                "items": response_items,
            }
            enriched = apply_translation_response(run, response, require_complete=True)
            out = tmp_root / slug
            out.mkdir(parents=True)
            write_bundle(enriched, out)
            errors = validate_bundle(out, require_zh_tw=True)
            if errors:
                raise ValueError(f"{slug} bundle validation failed:\n" + "\n".join(errors))
            stored = store_bundle(out, EDITIONS, require_zh_tw=True)
            errors = validate_stored_publication(stored, require_zh_tw=True)
            if errors:
                raise ValueError(f"{slug} canonical validation failed:\n" + "\n".join(errors))
            sealed_dirs.append(stored)

        if set(ledger) != expected_ids:
            extra = sorted(set(ledger) - expected_ids)
            missing = sorted(expected_ids - set(ledger))
            raise ValueError(f"translation id set mismatch; extra={extra[:5]} missing={missing[:5]}")

        activate_registry()
        site = tmp_root / "site"
        build_pages_site(
            output_dir=site,
            repository="hoiyu915-droid/EvidenceRadar-Editions",
            editions_root=EDITIONS,
            catalog_root=CATALOG,
            require_zh_tw=True,
        )
        catalog = load_json(site / "index.json")
        search = load_json(site / "search-index.json")
        if int(catalog.get("registered_journal_count") or 0) != 58:
            raise ValueError("Pages registered journal count changed unexpectedly")
        if int(catalog.get("journal_count") or 0) != 50:
            raise ValueError(f"Pages published journal count mismatch: {catalog.get('journal_count')}")
        if int(search.get("article_count") or 0) != 4237:
            raise ValueError(f"Pages article search count mismatch: {search.get('article_count')}")
        for slug, count in EXPECTED_COUNTS.items():
            page = site / "journals" / slug / "2026-08" / "r01" / "index.html"
            if not page.is_file():
                raise ValueError(f"Pages missing revision page: {slug}")
            stored = EDITIONS / slug / "2026" / "08" / "r01" / "edition.json"
            if int((load_json(stored).get("counts") or {}).get("articles") or -1) != count:
                raise ValueError(f"stored count mismatch after Pages build: {slug}")
        print(json.dumps({
            "sealed_journals": len(sealed_dirs),
            "sealed_articles": sum(EXPECTED_COUNTS.values()),
            "registered_journals": catalog.get("registered_journal_count"),
            "published_journals": catalog.get("journal_count"),
            "search_article_count": search.get("article_count"),
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
