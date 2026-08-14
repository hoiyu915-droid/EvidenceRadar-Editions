from __future__ import annotations

import json
import shutil
import tempfile
from collections import Counter, defaultdict
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

SLUGS = [
    "clinical-biomechanics",
    "clinical-nutrition-espen",
    "clinical-nutrition-open-science",
    "eclinicalmedicine",
    "journal-of-biomedical-informatics",
]
EXPECTED = {
    "clinical-biomechanics": 27,
    "clinical-nutrition-espen": 83,
    "clinical-nutrition-open-science": 25,
    "eclinicalmedicine": 53,
    "journal-of-biomedical-informatics": 21,
}
TOTAL_EXPECTED = sum(EXPECTED.values())


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return value


def load_translations() -> dict[str, str]:
    result: dict[str, str] = {}
    manifest = load_json(Path("translation-work/manifest.json"))
    if int(manifest.get("expected_items") or -1) != TOTAL_EXPECTED:
        raise RuntimeError("translation-work manifest count mismatch")
    for path in sorted(Path("translation-work").glob("batch04.part*.ndjson")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            item = json.loads(line)
            cid = str(item.get("canonical_id") or "").strip()
            title = str(item.get("title_zh_tw") or "").strip()
            if not cid or not title:
                raise RuntimeError(f"invalid translation row: {path}:{lineno}")
            if cid in result:
                raise RuntimeError(f"duplicate translation: {cid}")
            result[cid] = title
    return result


def excluded_ids() -> set[str]:
    result: set[str] = set()
    for source in (Path("probe/flags.json"), Path("probe/manual-exclusions.json")):
        value = load_json(source)
        for item in value.get("items") or []:
            if isinstance(item, dict) and item.get("canonical_id"):
                result.add(str(item["canonical_id"]))
    return result


def probe_run(slug: str) -> dict:
    root = Path("probe") / slug
    candidates = [
        path
        for path in root.glob("*.json")
        if not path.name.endswith(".manifest.json") and "translation-" not in path.name
    ]
    if len(candidates) != 1:
        raise RuntimeError(f"{slug}: expected exactly one probe edition JSON, got {candidates}")
    return load_json(candidates[0])


def prepare_run(slug: str, excluded: set[str]) -> dict:
    run = probe_run(slug)
    articles = [
        article
        for article in (run.get("articles") or [])
        if str(article.get("canonical_id") or "") not in excluded
    ]
    if len(articles) != EXPECTED[slug]:
        raise RuntimeError(
            f"{slug}: expected {EXPECTED[slug]} retained articles, got {len(articles)}"
        )
    by_source: defaultdict[str, set[str]] = defaultdict(set)
    by_type: Counter[str] = Counter()
    for article in articles:
        cid = str(article.get("canonical_id") or "")
        for record in article.get("source_records") or []:
            source = str((record or {}).get("source") or "")
            if source:
                by_source[source].add(cid)
        by_type[str(article.get("article_type") or "unspecified")] += 1
        for key in (
            "title_zh_tw",
            "summary_zh_tw",
            "translation_basis",
            "translation_source_url",
            "translation_status",
        ):
            article.pop(key, None)
    run["articles"] = articles
    run["counts"] = {
        "articles": len(articles),
        "translated_articles": 0,
        "by_source": {key: len(value) for key, value in sorted(by_source.items())},
        "by_article_type": dict(sorted(by_type.items())),
    }
    run["translation"] = {
        "language": "zh-TW",
        "status": "NOT_REQUESTED" if articles else "NOT_REQUIRED",
        "translated_articles": 0,
        "total_articles": len(articles),
        "source_edition_sha256": None,
        "request_binding_sha256": None,
        "response_sha256": None,
    }
    return run


def apply_titles(run: dict, translations: dict[str, str]) -> dict:
    request = build_translation_request(run)
    items = []
    for article in run.get("articles") or []:
        cid = str(article.get("canonical_id") or "")
        title = translations[cid]
        items.append(
            {
                "canonical_id": cid,
                "title_zh_tw": title,
                "summary_zh_tw": (
                    f"依題名，本篇聚焦於「{title}」。目前僅以題名作為繁中導讀依據，"
                    "未讀取摘要或全文，因此不推定研究方法、數值結果、效應大小或結論。"
                ),
                "basis": "TITLE_ONLY",
                "source_url": None,
            }
        )
    response = {
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
    return apply_translation_response(run, response, require_complete=True)


def main() -> None:
    excluded = excluded_ids()
    translations = load_translations()
    runs = {slug: prepare_run(slug, excluded) for slug in SLUGS}
    wanted = {
        str(article.get("canonical_id"))
        for run in runs.values()
        for article in (run.get("articles") or [])
    }
    if set(translations) != wanted:
        missing = sorted(wanted - set(translations))
        extra = sorted(set(translations) - wanted)
        raise RuntimeError(
            f"translation ledger mismatch: wanted={len(wanted)} got={len(translations)} "
            f"missing={missing} extra={extra}"
        )
    if len(wanted) != TOTAL_EXPECTED:
        raise RuntimeError(f"expected {TOTAL_EXPECTED} retained articles, got {len(wanted)}")

    workspace = Path(tempfile.mkdtemp(prefix="batch04-"))
    try:
        for slug in SLUGS:
            enriched = apply_titles(runs[slug], translations)
            bundle_dir = workspace / "bundles" / slug
            bundle_dir.mkdir(parents=True, exist_ok=True)
            write_bundle(enriched, bundle_dir)
            errors = validate_bundle(bundle_dir, require_zh_tw=True)
            if errors:
                raise RuntimeError(f"{slug}: bundle validation failed:\n" + "\n".join(errors))
            target = store_bundle(bundle_dir, Path("editions"), require_zh_tw=True)
            stored_errors = validate_stored_publication(target, require_zh_tw=True)
            if stored_errors:
                raise RuntimeError(f"{slug}: stored validation failed:\n" + "\n".join(stored_errors))
            print(f"sealed {slug}: {target}")

        site = workspace / "site"
        build_pages_site(
            editions_root=Path("editions"),
            catalog_root=Path("catalog"),
            output_dir=site,
            repository="hoiyu915-droid/EvidenceRadar-Editions",
            base_url="https://example.invalid/EvidenceRadar-Editions/",
            require_zh_tw=True,
        )
        for slug, count in EXPECTED.items():
            page = site / "journals" / slug / "2026-08" / "r01" / "index.html"
            if not page.is_file():
                raise RuntimeError(f"Pages smoke missing: {page}")
            manifest = load_json(Path("editions") / slug / "2026" / "08" / "r01" / "manifest.json")
            if int(manifest.get("article_count") or -1) != count:
                raise RuntimeError(f"{slug}: manifest article count mismatch")
        search = load_json(site / "search-index.json")
        if int(search.get("article_count") or 0) < 845:
            raise RuntimeError("Pages search index did not grow to the expected minimum")
        print(json.dumps({
            "batch_articles": TOTAL_EXPECTED,
            "new_monthly_counts": EXPECTED,
            "search_articles": search.get("article_count"),
        }, ensure_ascii=False, indent=2))
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    main()
