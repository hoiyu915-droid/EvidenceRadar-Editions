import copy
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from evidenceradar_editions.archive import publish_bundle
from evidenceradar_editions.bundle import artifact_names, write_bundle
from evidenceradar_editions.engine import RECONSTRUCTION_SEMANTICS
from evidenceradar_editions.naming import build_identity
from evidenceradar_editions.pages import build_pages_site
from evidenceradar_editions.serialization import json_sha256
from evidenceradar_editions.translation import (
    TRANSLATION_RESPONSE_TYPE,
    apply_translation_response,
    build_translation_request,
)
from evidenceradar_editions.validate import validate_bundle


def sample_run(*, revision: int = 1) -> dict:
    identity = build_identity(
        slug="jama-network-open",
        start=date(2026, 8, 13),
        end=date(2026, 8, 13),
        period_kind_requested="day",
        revision=revision,
    )
    stem = identity.artifact_stem
    return {
        "schema_version": "2.0",
        "artifact_type": "EvidenceRadar_Edition",
        "edition_id": identity.publication_id,
        "edition_key": identity.edition_key,
        "publication_id": identity.publication_id,
        "retrieved_at": "2026-08-14T00:00:00Z",
        "run_status": "COMPLETE",
        "data_semantics": RECONSTRUCTION_SEMANTICS,
        "scope": {
            "journal": "JAMA Network Open",
            "issn": "2574-3805",
            "slug": "jama-network-open",
            "journal_slug": "jama-network-open",
            "start_date": "2026-08-13",
            "end_date": "2026-08-13",
            "sources": ["pubmed"],
            "max_records": 500,
            "period_kind_requested": "day",
            "period_kind": "day",
            "period_key": "2026-08-13",
            "period_label_zh_tw": "2026 年 8 月 13 日",
            "revision": revision,
            "language": "zh-TW",
            "edition_key": identity.edition_key,
            "publication_id": identity.publication_id,
            "artifact_stem": stem,
        },
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
            "total_articles": 1,
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
            "commit": "abc",
            "control_plane": "config/radar_master.json",
            "matched_source_ids": [],
            "config_sha256": "x",
            "uses_radar_output_artifacts": False,
        },
        "source_checks": [
            {
                "source": "pubmed",
                "status": "SUCCESS",
                "query": "JAMA Network Open[Journal] AND 2026/08/13:2026/08/13[Date - Publication]",
                "returned_count": 1,
                "accepted_count": 1,
                "total_available": 1,
                "truncated": False,
                "detail": None,
            }
        ],
        "counts": {
            "articles": 1,
            "translated_articles": 0,
            "by_source": {"pubmed": 1},
            "by_article_type": {"Journal Article": 1},
        },
        "articles": [
            {
                "canonical_id": "doi:10.1000/example",
                "title": "Example study",
                "title_original": "Example study",
                "title_zh_tw": None,
                "summary_zh_tw": None,
                "translation_basis": None,
                "translation_source_url": None,
                "translation_status": "MISSING",
                "journal": "JAMA Network Open",
                "publication_date": "2026-08-13",
                "publication_date_precision": "DAY",
                "doi": "10.1000/example",
                "pmid": "123",
                "pmcid": None,
                "issns": ["2574-3805"],
                "authors": ["A Author"],
                "article_type": "Journal Article",
                "urls": ["https://doi.org/10.1000/example"],
                "source_records": [
                    {
                        "source": "pubmed",
                        "source_id": "123",
                        "url": "https://pubmed.ncbi.nlm.nih.gov/123/",
                    }
                ],
            }
        ],
    }


def translation_response(run: dict, *, title: str = "範例研究") -> dict:
    request = build_translation_request(run)
    return {
        "schema_version": "1.0",
        "artifact_type": TRANSLATION_RESPONSE_TYPE,
        "edition_id": run["edition_id"],
        "request_id": request["request_id"],
        "language": "zh-TW",
        "source_edition_sha256": request["source_edition_sha256"],
        "request_binding_sha256": request["request_binding_sha256"],
        "generated_at": "2026-08-14T00:01:00Z",
        "item_count": 1,
        "items": [
            {
                "canonical_id": "doi:10.1000/example",
                "title_zh_tw": title,
                "summary_zh_tw": "這是一段依題名整理的繁中導讀，未宣稱研究設計、數字或結果。",
                "basis": "TITLE_ONLY",
            }
        ],
    }


class DeliveryTests(unittest.TestCase):
    def test_self_describing_bundle_and_filters(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = sample_run()
            write_bundle(run, root)
            names = artifact_names(run)
            self.assertTrue((root / names["edition_json"]).is_file())
            self.assertTrue((root / names["report_html"]).is_file())
            self.assertTrue((root / names["manifest_json"]).is_file())
            self.assertEqual(validate_bundle(root), [])
            html = (root / names["report_html"]).read_text(encoding="utf-8")
            self.assertIn('lang="zh-Hant"', html)
            for control in (
                "filter-query", "filter-type", "filter-source", "filter-date",
                "filter-doi", "filter-pmid", "filter-pmcid", "filter-translated",
                "filter-sort", "clear-filters", "toggle-details",
            ):
                self.assertIn(f'id="{control}"', html)
            self.assertIn("尚未提供繁中導讀", html)
            self.assertTrue(validate_bundle(root, require_zh_tw=True))

    def test_hash_bound_translation_and_publication_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            raw_dir = base / "raw"
            translated_dir = base / "translated"
            archive = base / "archive"
            site = base / "site"
            run = sample_run()
            write_bundle(run, raw_dir)
            request = build_translation_request(run)
            self.assertEqual(request["source_edition_sha256"], json_sha256(run))
            enriched = apply_translation_response(run, translation_response(run))
            write_bundle(enriched, translated_dir)
            self.assertEqual(validate_bundle(translated_dir, require_zh_tw=True), [])
            target = publish_bundle(translated_dir, archive)
            self.assertTrue((target / "index.html").is_file())
            self.assertTrue((target / "edition.json").is_file())
            links = build_pages_site(
                archive_root=archive,
                output_dir=site,
                repository="hoiyu915-droid/EvidenceRadar-Editions",
            )
            self.assertTrue((site / "index.html").is_file())
            self.assertTrue((site / "search-index.json").is_file())
            period_page = site / "journals/jama-network-open/2026-08-13/index.html"
            self.assertTrue(period_page.is_file())
            self.assertIn("base_url", links)
            portal = (site / "index.html").read_text(encoding="utf-8")
            self.assertIn("開啟互動 HTML", portal)
            self.assertIn("文章題名或 DOI", portal)
            search = json.loads((site / "search-index.json").read_text())
            self.assertEqual(search["article_count"], 1)
            self.assertEqual(search["articles"][0]["title_zh_tw"], "範例研究")

    def test_archive_revisions_are_immutable_and_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            archive = base / "archive"
            for revision, title in ((1, "第一版範例"), (2, "第二版範例")):
                run = sample_run(revision=revision)
                enriched = apply_translation_response(
                    run, translation_response(run, title=title)
                )
                bundle = base / f"bundle-{revision}"
                write_bundle(enriched, bundle)
                publish_bundle(bundle, archive)
            site = base / "site"
            build_pages_site(
                archive_root=archive,
                output_dir=site,
                repository="hoiyu915-droid/EvidenceRadar-Editions",
            )
            period = (site / "journals/jama-network-open/2026-08-13/index.html").read_text()
            self.assertIn("r02", period)
            self.assertIn("r01", period)
            catalog = json.loads((site / "index.json").read_text())
            self.assertEqual(catalog["period_count"], 1)
            self.assertEqual(catalog["revision_count"], 2)
            self.assertEqual(catalog["latest_editions"][0]["revision"], 2)

    def test_archive_alias_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run = sample_run()
            enriched = apply_translation_response(run, translation_response(run))
            bundle = base / "bundle"
            archive = base / "archive"
            write_bundle(enriched, bundle)
            target = publish_bundle(bundle, archive)
            (target / "edition.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                build_pages_site(
                    archive_root=archive,
                    output_dir=base / "site",
                    repository="hoiyu915-droid/EvidenceRadar-Editions",
                )

    def test_radar_artifact_dependency_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = sample_run()
            run["upstream_radar"]["uses_radar_output_artifacts"] = True
            write_bundle(run, root)
            self.assertTrue(validate_bundle(root))

    def test_translation_response_must_bind_exact_source(self):
        run = sample_run()
        response = translation_response(run)
        response["source_edition_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            apply_translation_response(copy.deepcopy(run), response)

    def test_publication_gate_rejects_non_chinese_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = sample_run()
            response = translation_response(run, title="Example title")
            response["items"][0]["summary_zh_tw"] = "English only summary"
            enriched = apply_translation_response(run, response)
            write_bundle(enriched, root)
            errors = validate_bundle(root, require_zh_tw=True)
            self.assertTrue(any("lacks CJK" in value for value in errors))
