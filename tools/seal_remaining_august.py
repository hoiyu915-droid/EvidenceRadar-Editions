from __future__ import annotations

import json
import re
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path

from evidenceradar_editions.bundle import write_bundle
from evidenceradar_editions.naming import build_identity
from evidenceradar_editions.pages import build_pages_site
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
EDITIONS = ROOT / "editions"
CATALOG = ROOT / "catalog"
PROBE = ROOT / "probe"
WORK = ROOT / "translation-work" / "remaining"
START = date(2026, 8, 1)
END = date(2026, 8, 14)
TMLR_SLUG = "tmlr"
TMLR_ISSN = "2835-8856"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def fix_utf8(value: object) -> str:
    text = str(value or "")
    if any(marker in text for marker in ("Ã", "â", "Â", "ð")):
        try:
            return text.encode("latin1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return text
    return text


def clean_translation_rows() -> list[dict]:
    ledger = load(WORK / "tmlr.json")
    rows = ledger.get("items") or []
    if len(rows) != 84:
        raise ValueError(f"TMLR translation count must be 84, got {len(rows)}")
    seen = set()
    for row in rows:
        cid = str(row.get("canonical_id") or "")
        if not cid or cid in seen:
            raise ValueError(f"invalid/duplicate TMLR canonical id: {cid!r}")
        seen.add(cid)
        for key in ("title", "title_original"):
            row[key] = fix_utf8(row.get(key))
        row["authors"] = [fix_utf8(value) for value in (row.get("authors") or [])]
        if row["authors"] and row["authors"][0].startswith(row["title_original"] + " "):
            row["authors"][0] = row["authors"][0][len(row["title_original"]):].strip()
        title_zh = fix_utf8(row.get("title_zh_tw")).strip()
        if re.search(r"\bLLMs?\b", row["title_original"], re.I):
            title_zh = title_zh.replace("法學碩士們", "LLMs").replace("法學碩士", "LLM")
        row["title_zh_tw"] = title_zh
        blob = " ".join([row["title_original"], title_zh, *row["authors"]])
        if any(marker in blob for marker in ("Ã", "â", "Â")):
            raise ValueError(f"TMLR mojibake remains: {cid}")
        if re.search(r"\bLLMs?\b", row["title_original"], re.I) and "法學碩士" in title_zh:
            raise ValueError(f"TMLR LLM mistranslation remains: {cid}")
        if not contains_cjk(title_zh):
            raise ValueError(f"TMLR title lacks CJK: {cid}")
    return rows


def tmlr_raw_run(rows: list[dict]) -> dict:
    identity = build_identity(
        slug=TMLR_SLUG,
        start=START,
        end=END,
        period_kind_requested="month",
        revision=1,
    )
    articles = []
    for row in rows:
        url = str(row.get("url") or "")
        oid = str(row.get("openreview_id") or "")
        article = {
            "canonical_id": str(row["canonical_id"]),
            "title": str(row["title_original"]),
            "title_original": str(row["title_original"]),
            "title_zh_tw": None,
            "summary_zh_tw": None,
            "translation_basis": None,
            "translation_source_url": None,
            "translation_status": "MISSING",
            "journal": "Transactions on Machine Learning Research",
            "publication_date": "2026-08-01",
            "publication_date_precision": "MONTH",
            "doi": None,
            "pmid": None,
            "pmcid": None,
            "issns": [TMLR_ISSN],
            "authors": list(row.get("authors") or []),
            "article_type": "Journal Article",
            "urls": [url] if url else [],
            "source_records": [
                {
                    "source": "tmlr_official_snapshot",
                    "source_id": oid or str(row["canonical_id"]),
                    "url": url or None,
                }
            ],
        }
        articles.append(article)
    scope = {
        "journal": "Transactions on Machine Learning Research",
        "issn": TMLR_ISSN,
        "slug": TMLR_SLUG,
        "start_date": START.isoformat(),
        "end_date": END.isoformat(),
        "sources": ["tmlr_official_snapshot"],
        "max_records": 5000,
        "period_kind_requested": "month",
        "revision": 1,
        "language": "zh-TW",
    }
    scope.update(identity.to_dict())
    stem = identity.artifact_stem
    return {
        "schema_version": "2.0",
        "artifact_type": "EvidenceRadar_Edition",
        "edition_id": identity.publication_id,
        "edition_key": identity.edition_key,
        "publication_id": identity.publication_id,
        "retrieved_at": utc_now_iso(),
        "run_status": "COMPLETE",
        "data_semantics": "current_source_reconstruction_of_historical_publication_window",
        "scope": scope,
        "presentation": {
            "default_language": "zh-TW",
            "html_language": "zh-Hant",
            "preserve_original_title": True,
            "interactive_filters": True,
            "translation_required_for_publication": True,
        },
        "translation": {
            "language": "zh-TW",
            "status": "NOT_REQUESTED",
            "translated_articles": 0,
            "total_articles": len(articles),
            "source_edition_sha256": None,
            "request_binding_sha256": None,
            "response_sha256": None,
        },
        "artifacts": {
            "stem": stem,
            "edition_json": f"{stem}.json",
            "report_html": f"{stem}.html",
            "manifest_json": f"{stem}.manifest.json",
            "translation_request_json": f"{stem}.translation-request.zh-TW.json",
            "translation_response_json": f"{stem}.translation-response.zh-TW.json",
        },
        "upstream_radar": {
            "repository": "hoiyu915-droid/EvidenceRadar",
            "commit": None,
            "control_plane": "config/radar_master.json",
            "matched_source_ids": [],
            "config_sha256": None,
            "uses_radar_output_artifacts": False,
        },
        "source_checks": [
            {
                "source": "tmlr_official_snapshot",
                "status": "SUCCESS",
                "query": "official TMLR papers page: entries labelled August 2026; snapshot captured 2026-08-14",
                "returned_count": len(articles),
                "accepted_count": len(articles),
                "total_available": len(articles),
                "truncated": False,
                "detail": "Publication month is first-party; day is intentionally not inferred. Current 2026-08-14 snapshot bounds the MTD reconstruction.",
            }
        ],
        "counts": {
            "articles": len(articles),
            "translated_articles": 0,
            "by_source": {"tmlr_official_snapshot": len(articles)},
            "by_article_type": {"Journal Article": len(articles)},
        },
        "articles": articles,
    }


def translate_run(run: dict, rows: list[dict]) -> dict:
    by_id = {str(row["canonical_id"]): row for row in rows}
    request = build_translation_request(run)
    items = []
    for article in run["articles"]:
        row = by_id[article["canonical_id"]]
        title = str(row["title_zh_tw"]).strip()
        items.append(
            {
                "canonical_id": article["canonical_id"],
                "title_zh_tw": title,
                "summary_zh_tw": f"本篇文獻題名為「{title}」。",
                "basis": "TITLE_ONLY",
                "source_url": None,
            }
        )
    response = {
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
    return apply_translation_response(run, response, require_complete=True)


def update_registry() -> dict:
    path = CATALOG / "journals.json"
    registry = load(path)
    found = False
    for journal in registry.get("journals") or []:
        if journal.get("slug") == TMLR_SLUG:
            journal["issn"] = TMLR_ISSN
            found = True
            break
    if not found:
        raise ValueError("TMLR missing from journal registry")
    path.write_text(json_text(registry), encoding="utf-8")
    return registry


def tacl_coverage_status(final: dict) -> tuple[str, str]:
    candidates = (final.get("tacl") or {}).get("all_candidates") or []
    precise = [
        row for row in candidates
        if row.get("publication_date_precision") in {"DAY", "MONTH"}
        and row.get("publication_date")
    ]
    if precise:
        return (
            "OUTSIDE_WINDOW",
            f"ACL Anthology identified {len(candidates)} 2026-volume candidates; {len(precise)} had DAY/MONTH Crossref publication dates and none overlapped 2026-08-01..14.",
        )
    return (
        "DATE_EVIDENCE_INSUFFICIENT",
        f"ACL Anthology identified {len(candidates)} 2026-volume candidates, but no candidate had DAY/MONTH publication evidence for this MTD window.",
    )


def write_coverage(registry: dict) -> dict:
    final = load(PROBE / "final-first-party.json")
    initial = load(PROBE / "remaining-august-summary.json")
    initial_by_slug = {row["slug"]: row for row in initial.get("remaining") or []}
    tacl_status, tacl_note = tacl_coverage_status(final)
    special = {
        "chemical-science": (
            "DATE_EVIDENCE_INSUFFICIENT",
            "Crossref publication/online-publication filters returned zero; 81 created-date candidates are not publication evidence. RSC first-party landing/RSS access failed from hosted runner, so no August edition was fabricated.",
        ),
        "information-processing-management": (
            "NO_MATCHING_ARTICLES",
            "Exact ISSN Crossref publication-date reconstruction returned zero articles for 2026-08-01..14.",
        ),
        "journal-of-machine-learning-research": (
            "NO_MATCHING_ARTICLES",
            "Official JMLR RSS contained zero pubDate entries in 2026-08-01..14.",
        ),
        "journal-of-sport-and-health-science": (
            "NO_MATCHING_ARTICLES",
            "Crossref, PubMed, and Europe PMC all returned zero matching publication records in the window.",
        ),
        "natural-language-processing-journal": (
            "NO_MATCHING_ARTICLES",
            "Exact ISSN Crossref publication-date reconstruction returned zero articles; created-date records were not treated as publication dates.",
        ),
        "psychology-of-sport-and-exercise": (
            "OUTSIDE_WINDOW",
            "Three PubMed YEAR-only candidates were audited by DOI; Crossref published/issued dates are November 2026, outside this MTD window.",
        ),
        "tacl": (tacl_status, tacl_note),
    }
    rows = []
    status_counts = Counter()
    published = 0
    for journal in registry.get("journals") or []:
        slug = str(journal.get("slug") or "")
        edition_path = EDITIONS / slug / "2026" / "08" / "r01" / "edition.json"
        if edition_path.is_file():
            edition = load(edition_path)
            count = int((edition.get("counts") or {}).get("articles") or 0)
            status, note = "PUBLISHED", "Canonical 2026-08 r01 edition exists."
            published += 1
        else:
            status, note = special.get(slug, ("DATE_EVIDENCE_INSUFFICIENT", "No canonical August edition and no terminal evidence classification was available."))
            count = 0
        status_counts[status] += 1
        source_probe = initial_by_slug.get(slug) or {}
        rows.append(
            {
                "journal": journal.get("name"),
                "slug": slug,
                "registry_status": journal.get("status"),
                "coverage_status": status,
                "article_count": count,
                "note": note,
                "initial_probe_run_status": source_probe.get("run_status"),
                "initial_probe_articles": source_probe.get("articles"),
            }
        )
    if len(rows) != 58:
        raise ValueError(f"coverage registry must contain 58 journals, got {len(rows)}")
    if published != 51:
        raise ValueError(f"expected 51 published journals after TMLR, got {published}")
    payload = {
        "schema_version": "1.0",
        "artifact_type": "EvidenceRadar_Editions_PeriodCoverage",
        "period_key": "2026-08",
        "coverage_start": "2026-08-01",
        "coverage_through": "2026-08-14",
        "semantics": "All registered journals were evaluated for an August 2026 MTD edition. A missing edition is classified explicitly rather than represented by a fabricated empty publication.",
        "registry_count": 58,
        "processed_journal_count": 58,
        "published_journal_count": published,
        "no_edition_count": 58 - published,
        "status_counts": dict(sorted(status_counts.items())),
        "journals": rows,
    }
    target = CATALOG / "coverage" / "2026-08.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json_text(payload), encoding="utf-8")
    return payload


def main() -> None:
    rows = clean_translation_rows()
    run = translate_run(tmlr_raw_run(rows), rows)
    with tempfile.TemporaryDirectory(prefix="tmlr-final-seal-") as tmp:
        bundle = Path(tmp) / "bundle"
        write_bundle(run, bundle)
        errors = validate_bundle(bundle, require_zh_tw=True)
        if errors:
            raise ValueError("TMLR bundle validation failed:\n" + "\n".join(errors))
        stored = store_bundle(bundle, EDITIONS, require_zh_tw=True)
        errors = validate_stored_publication(stored, require_zh_tw=True)
        if errors:
            raise ValueError("TMLR canonical validation failed:\n" + "\n".join(errors))

        registry = update_registry()
        coverage = write_coverage(registry)
        site = Path(tmp) / "site"
        links = build_pages_site(
            output_dir=site,
            repository="hoiyu915-droid/EvidenceRadar-Editions",
            editions_root=EDITIONS,
            catalog_root=CATALOG,
            require_zh_tw=True,
        )
        index = load(site / "index.json")
        search = load(site / "search-index.json")
        public_coverage = load(site / "coverage" / "2026-08.json")
        tmlr_browse = load(site / "journals" / TMLR_SLUG / "2026-08" / "r01" / "browse.json")
        if int(index.get("journal_count") or 0) != 51:
            raise ValueError(f"Pages published journal count mismatch: {index.get('journal_count')}")
        if int(public_coverage.get("processed_journal_count") or 0) != 58:
            raise ValueError("Pages period coverage did not publish 58/58 processed journals")
        if int(tmlr_browse.get("article_count") or 0) != 84:
            raise ValueError("TMLR browse count mismatch")
        if not str(links.get("period_coverage_url") or "").endswith("coverage/2026-08.json"):
            raise ValueError("Pages links lacks period coverage URL")
        print(json.dumps({
            "tmlr_articles": 84,
            "processed_journals": coverage["processed_journal_count"],
            "published_journals": coverage["published_journal_count"],
            "no_edition_count": coverage["no_edition_count"],
            "status_counts": coverage["status_counts"],
            "search_article_count": search.get("article_count"),
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
