from __future__ import annotations

import json
import shutil
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path

from evidenceradar_editions.bundle import write_bundle
from evidenceradar_editions.dedup import counts_by_source
from evidenceradar_editions.engine import build_run
from evidenceradar_editions.models import EditionSpec
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
MAP_ROOT = ROOT / "staging" / "maps"
EDITIONS = ROOT / "editions"
CATALOG = ROOT / "catalog"
START = date(2026, 8, 1)
END = date(2026, 8, 14)
RADAR_PIN = "6da659df845e4b76072dae016120ca76ed9c27c4"
EXPECTED = {
    "artificial-intelligence": 15,
    "ieee-transactions-on-artificial-intelligence": 37,
    "jama-network-open": 88,
    "machine-learning": 2,
    "nature-machine-intelligence": 5,
}

MACHINE_LEARNING_MAP = {
    "journal": "Machine Learning",
    "issn": "0885-6125",
    "sources": ["crossref", "radar_rss"],
    "exclude": [],
    "translations": {
        "Towards Performatively Stable Equilibria in Decision-Dependent Games for Arbitrary Data Distribution Maps": "任意資料分布映射下決策相依博弈中的表現穩定均衡",
        "Learning Weakly Convex Sets in Metric Spaces": "在度量空間中學習弱凸集合",
    },
}


def load_mapping(slug: str) -> dict:
    path = MAP_ROOT / f"{slug}.json"
    if path.is_file():
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"mapping must be an object: {path}")
        return value
    if slug == "machine-learning":
        return MACHINE_LEARNING_MAP
    raise FileNotFoundError(path)


def title_of(article: dict) -> str:
    return str(article.get("title_original") or article.get("title") or "").strip()


def recalc_counts(run: dict) -> None:
    articles = run["articles"]
    by_type = Counter(str(a.get("article_type") or "unspecified") for a in articles)
    run["counts"] = {
        "articles": len(articles),
        "translated_articles": 0,
        "by_source": counts_by_source(articles),
        "by_article_type": dict(sorted(by_type.items())),
    }
    if articles:
        active = [
            str(c.get("status") or "")
            for c in run.get("source_checks") or []
            if c.get("source") != "radar_rss"
        ]
        run["run_status"] = (
            "PARTIAL_SOURCE_COVERAGE"
            if any(v in {"FAILED", "PARTIAL"} for v in active)
            else "COMPLETE"
        )
    else:
        run["run_status"] = "NO_MATCHING_ARTICLES"


def make_response(run: dict, translations: dict[str, str]) -> dict:
    request = build_translation_request(run)
    missing: list[str] = []
    items: list[dict] = []
    for article in run["articles"]:
        original = title_of(article)
        zh = translations.get(original)
        if not zh:
            missing.append(original)
            continue
        items.append(
            {
                "canonical_id": article["canonical_id"],
                "title_zh_tw": zh,
                "summary_zh_tw": (
                    f"依題名，本篇聚焦於「{zh}」。目前僅以題名作為繁中導讀依據，"
                    "未讀取摘要或全文，因此不推定研究方法、數值結果、效應大小或結論。"
                ),
                "basis": "TITLE_ONLY",
            }
        )
    if missing:
        raise RuntimeError(
            f"{run['edition_id']}: translation map is missing {len(missing)} title(s):\n"
            + "\n".join(missing)
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


def build_one(slug: str, temp_root: Path) -> Path:
    mapping = load_mapping(slug)
    spec = EditionSpec(
        journal=str(mapping["journal"]),
        issn=str(mapping["issn"]),
        slug=slug,
        start_date=START,
        end_date=END,
        sources=tuple(str(v) for v in mapping["sources"]),
        max_records=500,
        period_kind="month",
        revision=1,
    )
    run = build_run(spec, radar_root=None, radar_commit=RADAR_PIN)
    original_count = len(run["articles"])
    excluded = set(str(v) for v in mapping.get("exclude") or [])
    excluded_records = [
        {
            "canonical_id": a.get("canonical_id"),
            "title": title_of(a),
            "reason": "NON_ARTICLE_FRONT_MATTER",
        }
        for a in run["articles"]
        if title_of(a) in excluded
    ]
    run["articles"] = [a for a in run["articles"] if title_of(a) not in excluded]
    recalc_counts(run)
    run["publication_notes"] = {
        "editorial_projection": {
            "source_match_count": original_count,
            "published_article_count": len(run["articles"]),
            "excluded_count": len(excluded_records),
            "excluded_records": excluded_records,
        }
    }
    expected = EXPECTED[slug]
    if len(run["articles"]) != expected:
        raise RuntimeError(
            f"{slug}: expected {expected} published article(s), got {len(run['articles'])}; "
            f"source matches={original_count}, excluded={len(excluded_records)}"
        )
    response = make_response(run, dict(mapping["translations"]))
    enriched = apply_translation_response(run, response, require_complete=True)
    bundle = temp_root / slug
    write_bundle(enriched, bundle)
    errors = validate_bundle(bundle, require_zh_tw=True)
    if errors:
        raise RuntimeError(f"{slug}: bundle validation failed:\n" + "\n".join(errors))
    target = store_bundle(bundle, EDITIONS, require_zh_tw=True)
    stored_errors = validate_stored_publication(target, require_zh_tw=True)
    if stored_errors:
        raise RuntimeError(f"{slug}: stored publication invalid:\n" + "\n".join(stored_errors))
    if any(target.glob("*.html")):
        raise RuntimeError(f"{slug}: HTML leaked into canonical Git storage")
    print(
        json.dumps(
            {
                "journal": mapping["journal"],
                "slug": slug,
                "source_matches": original_count,
                "excluded": len(excluded_records),
                "published": len(run["articles"]),
                "stored": str(target.relative_to(ROOT)),
            },
            ensure_ascii=False,
        )
    )
    return target


def verify_site(temp_root: Path) -> None:
    site = temp_root / "site"
    build_pages_site(
        editions_root=EDITIONS,
        catalog_root=CATALOG,
        output_dir=site,
        repository="hoiyu915-droid/EvidenceRadar-Editions",
        base_url="https://hoiyu915-droid.github.io/EvidenceRadar-Editions/",
        require_zh_tw=True,
    )
    catalog = json.loads((site / "index.json").read_text(encoding="utf-8"))
    entries = catalog.get("editions") or []
    monthly = {
        str(e.get("journal_slug")): int(e.get("article_count") or 0)
        for e in entries
        if e.get("period_key") == "2026-08"
    }
    if monthly != EXPECTED:
        raise RuntimeError(f"Pages monthly catalog mismatch: {monthly!r}")
    search = json.loads((site / "search-index.json").read_text(encoding="utf-8"))
    if int(search.get("article_count") or 0) < sum(EXPECTED.values()):
        raise RuntimeError("Pages search index lost August MTD articles")
    if int(catalog.get("journal_count") or 0) != 5:
        raise RuntimeError(f"expected 5 published journals, got {catalog.get('journal_count')}")
    print(
        json.dumps(
            {
                "pages_journals": catalog.get("journal_count"),
                "pages_periods": catalog.get("period_count"),
                "pages_revisions": catalog.get("revision_count"),
                "search_articles": search.get("article_count"),
                "august_articles": sum(monthly.values()),
            },
            ensure_ascii=False,
        )
    )


def main() -> None:
    slugs = list(EXPECTED)
    with tempfile.TemporaryDirectory(prefix="august-mtd-publish-") as tmp:
        temp_root = Path(tmp)
        for slug in slugs:
            build_one(slug, temp_root)
        verify_site(temp_root)

    # Staging is intentionally ephemeral and must never reach main.
    staging = ROOT / "staging"
    if staging.exists():
        shutil.rmtree(staging)


if __name__ == "__main__":
    main()
