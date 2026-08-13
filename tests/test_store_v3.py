import tempfile
import unittest
from datetime import date
from pathlib import Path

from evidenceradar_editions.bundle import write_bundle
from evidenceradar_editions.naming import build_identity
from evidenceradar_editions.pages import build_pages_site
from evidenceradar_editions.store_v3 import (
    discover_stored_publications,
    store_bundle,
    validate_stored_publication,
)
from evidenceradar_editions.translation import apply_translation_response
from test_delivery import sample_run, translation_response


def month_run() -> dict:
    run = sample_run()
    identity = build_identity(
        slug="jama-network-open",
        start=date(2026, 8, 1),
        end=date(2026, 8, 14),
        period_kind_requested="month",
        revision=1,
    )
    run["edition_id"] = identity.publication_id
    run["edition_key"] = identity.edition_key
    run["publication_id"] = identity.publication_id
    run["scope"].update(
        {
            "start_date": "2026-08-01",
            "end_date": "2026-08-14",
            "period_kind_requested": "month",
            **identity.to_dict(),
        }
    )
    stem = identity.artifact_stem
    run["artifacts"] = {
        "stem": stem,
        "edition_json": f"{stem}.json",
        "report_html": f"{stem}.html",
        "manifest_json": f"{stem}.manifest.json",
        "translation_request_json": f"{stem}.translation-request.zh-TW.json",
        "translation_response_json": f"{stem}.translation-response.zh-TW.json",
    }
    return run


class CanonicalStoreV3Tests(unittest.TestCase):
    def test_month_store_is_sharded_and_html_free(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run = month_run()
            enriched = apply_translation_response(run, translation_response(run))
            bundle = base / "bundle"
            editions = base / "editions"
            write_bundle(enriched, bundle)
            target = store_bundle(bundle, editions)

            self.assertEqual(
                target.relative_to(editions).as_posix(),
                "jama-network-open/2026/08/r01",
            )
            self.assertTrue((target / "edition.json").is_file())
            self.assertTrue((target / "manifest.json").is_file())
            self.assertTrue((target / "storage.json").is_file())
            self.assertFalse((target / "index.html").exists())
            self.assertEqual(list(target.glob("*.html")), [])
            self.assertEqual(validate_stored_publication(target), [])

    def test_day_store_is_sharded_below_month_without_polluting_month_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run = sample_run()
            enriched = apply_translation_response(run, translation_response(run))
            bundle = base / "bundle"
            editions = base / "editions"
            write_bundle(enriched, bundle)
            target = store_bundle(bundle, editions)
            self.assertEqual(
                target.relative_to(editions).as_posix(),
                "jama-network-open/2026/08/days/13/r01",
            )

    def test_pages_rebuilds_html_from_canonical_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run = month_run()
            enriched = apply_translation_response(run, translation_response(run))
            bundle = base / "bundle"
            editions = base / "editions"
            site = base / "site"
            write_bundle(enriched, bundle)
            store_bundle(bundle, editions)

            build_pages_site(
                editions_root=editions,
                output_dir=site,
                repository="hoiyu915-droid/EvidenceRadar-Editions",
            )
            report = site / "journals/jama-network-open/2026-08/r01/index.html"
            self.assertTrue(report.is_file())
            self.assertIn("範例研究", report.read_text(encoding="utf-8"))
            self.assertTrue((site / "journals/jama-network-open/2026-08/r01/edition.json").is_file())
            self.assertTrue((site / "index.json").is_file())

    def test_store_is_idempotent_but_revision_bytes_are_immutable(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run = month_run()
            enriched = apply_translation_response(run, translation_response(run))
            bundle = base / "bundle"
            editions = base / "editions"
            write_bundle(enriched, bundle)
            first = store_bundle(bundle, editions)
            second = store_bundle(bundle, editions)
            self.assertEqual(first, second)

            (first / "edition.json").write_text("{}\n", encoding="utf-8")
            self.assertTrue(validate_stored_publication(first))
            with self.assertRaises(ValueError):
                discover_stored_publications(editions)


if __name__ == "__main__":
    unittest.main()
