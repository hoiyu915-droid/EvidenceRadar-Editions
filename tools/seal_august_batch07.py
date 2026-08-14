from __future__ import annotations

import json
import shutil
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
from evidenceradar_editions.utils import utc_now_iso
from evidenceradar_editions.validate import validate_bundle

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "probe" / "batch07-selected"
WORK = ROOT / "translation-work"
EDITIONS = ROOT / "editions"
CATALOG = ROOT / "catalog"

EXPECTED_COUNTS = {
    "acs-central-science": 8,
    "communications-chemistry": 13,
    "communications-physics": 18,
    "knowledge-based-systems": 106,
    "national-science-review": 23,
    "physical-review-x": 29,
    "plos-biology": 16,
    "plos-medicine": 11,
    "pnas-nexus": 17,
    "the-lancet-regional-health-americas": 30,
}
REGISTRY_UPDATES = {
    "acs-central-science": ("2374-7943", ["crossref"]),
    "communications-chemistry": ("2399-3669", ["crossref"]),
    "communications-physics": ("2399-3650", ["crossref"]),
    "national-science-review": ("2053-714X", ["crossref"]),
    "physical-review-x": ("2160-3308", ["crossref"]),
    "plos-biology": ("1545-7885", ["crossref"]),
    "plos-medicine": ("1549-1676", ["crossref"]),
    "pnas-nexus": ("2752-6542", ["crossref"]),
}
# Conservative simplified-only/high-signal sentinels. This is an extra zh-TW gate,
# not a replacement for semantic review.
SIMPLIFIED_SENTINELS = set("这为与从对体发后里学网图术应实线进选运开关门国个书东声边业无长");


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


def load_ledger(manifest: dict) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for path in sorted(WORK.glob("batch07.part*.ndjson")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            cid = str(row.get("canonical_id") or "")
            title = str(row.get("title_zh_tw") or "").strip()
            if not cid or not title:
                raise ValueError(f"incomplete translation row in {path}: {cid!r}")
            if cid in rows:
                raise ValueError(f"duplicate translation id: {cid}")
            bad = sorted({ch for ch in title if ch in SIMPLIFIED_SENTINELS})
            if bad:
                raise ValueError(f"zh-TW simplified-character sentinel failed for {cid}: {''.join(bad)}")
            rows[cid] = row
    if len(rows) != int(manifest["expected_items"]):
        raise ValueError(f"translation ledger count mismatch: {len(rows)} != {manifest['expected_items']}")
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
    manifest = load_json(WORK / "manifest.json")
    if int(manifest.get("expected_items") or 0) != 271:
        raise ValueError("batch07 expected_items must be 271")
    if dict(manifest.get("counts") or {}) != EXPECTED_COUNTS:
        raise ValueError("batch07 per-journal counts do not match sealed contract")
    excluded = set(manifest.get("excluded_ids") or [])
    ledger = load_ledger(manifest)

    expected_ids: set[str] = set()
    sealed_dirs: list[Path] = []
    with tempfile.TemporaryDirectory(prefix="batch07-seal-") as tmp:
        tmp_root = Path(tmp)
        for slug, expected_count in EXPECTED_COUNTS.items():
            run = load_json(PROBE / slug / "edition.json")
            run["articles"] = [
                a for a in (run.get("articles") or [])
                if str(a.get("canonical_id") or "") not in excluded
            ]
            if len(run["articles"]) != expected_count:
                raise ValueError(f"{slug}: filtered count {len(run['articles'])} != {expected_count}")
            recompute_counts(run)
            ids = {str(a.get("canonical_id") or "") for a in run["articles"]}
            expected_ids.update(ids)
            if len(ids) != expected_count:
                raise ValueError(f"{slug}: duplicate canonical ids after filtering")

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
                    "summary_zh_tw": f"本篇文獻題名為「{title_zh}」。",
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
