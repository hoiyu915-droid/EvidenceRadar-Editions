import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evidenceradar_editions import pages_v12, pages_v13
from evidenceradar_editions.editorial_shortlist_v2 import (
    builtin_editorial_shortlist_policy_v2,
)
from evidenceradar_editions.journal_impact import impact_registry_sha256


def triage_record(index: int, *, route: str = "FETCH_CANDIDATE"):
    canonical_id = f"doi:10.1000/example.{index}"
    return {
        "canonical_id": canonical_id,
        "journal": "Example Journal",
        "journal_slug": "example-journal",
        "period_key": "2026-08",
        "revision": 1,
        "publication_date": "2026-08-13",
        "publication_date_precision": "DAY",
        "title_original": (
            "Systematic review of cardiometabolic rehabilitation"
            if index == 1
            else "Systematic review of multilingual benchmark governance"
            if index == 2
            else "Systematic review of marine ecosystem forecasting"
        ),
        "title_zh_tw": f"測試系統性回顧 {index}",
        "article_type": "journal-article",
        "authors": ["A Author"],
        "identifiers": {
            "doi": canonical_id.removeprefix("doi:"),
            "pmid": str(900000 + index),
            "pmcid": None,
        },
        "source_urls": [f"https://doi.org/{canonical_id.removeprefix('doi:')}"] ,
        "categories": ["clinical_medicine"],
        "publication_role": "primary",
        "matched_paths": ["EVIDENCE_SYNTHESIS"],
        "primary_path": "EVIDENCE_SYNTHESIS",
        "score": 95 if route == "FETCH_CANDIDATE" else 72,
        "raw_score": 95 if route == "FETCH_CANDIDATE" else 72,
        "reason_codes": ["EVIDENCE_SYNTHESIS", "PMID_ROUTE", "DOI_ROUTE"],
        "route": route,
        "processing_mode": "FULL",
        "processing_policy_source": "test",
        "journal_soft_cap_demoted": False,
        "full_text_fetched": False,
        "abstract_reviewed": False,
        "evidence_evaluated": False,
        "edition_url": "journals/example-journal/2026-08/r01/",
        "canonical_json_url": (
            "journals/example-journal/2026-08/r01/edition.json"
        ),
    }


def impact_registry():
    return {
        "schema_version": "1.0",
        "artifact_type": "EvidenceRadar_Editions_JournalImpactRegistry",
        "observed_at": "2026-08-15",
        "semantics": "Publisher-displayed metric used only as a test prior.",
        "metric_preference": ["JIF", "CITESCORE"],
        "normalization": {
            "peer_group": "registry_category_and_metric_kind",
            "percentile_method": "midrank",
            "multi_category_aggregation": "arithmetic_mean",
            "unknown_percentile": 50.0,
        },
        "journals": {
            "example-journal": {
                "name": "Example Journal",
                "publisher": "Example Publisher",
                "categories": ["clinical_medicine"],
                "status": "VERIFIED_PUBLISHER_DISPLAY",
                "metrics": {"JIF": {"value": 12.0, "year": 2025}},
                "source_url": "https://example.test/journal",
                "source_note": "test",
            }
        },
    }


class PagesEditorialShortlistV2Tests(unittest.TestCase):
    def test_pages_publish_metric_registry_and_impact_bound_shortlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "site"
            catalog = root / "catalog"
            editions = root / "editions"
            catalog.mkdir()
            editions.mkdir()

            policy = builtin_editorial_shortlist_policy_v2()
            policy["fetch_now_target"] = 2
            policy["hold_reserve_target"] = 2
            policy["journal_fetch_caps"] = {
                "FULL": 4,
                "TRIAGE": 4,
                "INDEX_ONLY": 1,
                "SUSPENDED": 0,
            }
            policy["topic_soft_caps_by_mode"] = {
                "FULL": 4,
                "TRIAGE": 4,
                "INDEX_ONLY": 1,
                "SUSPENDED": 0,
            }
            policy["topic_hard_caps_by_mode"] = dict(
                policy["topic_soft_caps_by_mode"]
            )
            (catalog / "editorial-shortlist-policy.json").write_text(
                json.dumps(policy),
                encoding="utf-8",
            )
            registry = impact_registry()
            (catalog / "journal-impact-metrics.json").write_text(
                json.dumps(registry),
                encoding="utf-8",
            )

            revision = (
                output
                / "journals"
                / "example-journal"
                / "2026-08"
                / "r01"
            )

            def fake_base(**kwargs):
                output.mkdir(parents=True)
                revision.mkdir(parents=True)
                (output / "index.html").write_text(
                    '<html><body><main class="shell">portal</main></body></html>',
                    encoding="utf-8",
                )
                (output / "index.json").write_text("{}", encoding="utf-8")
                (output / "links.json").write_text("{}", encoding="utf-8")
                (revision / "index.html").write_text(
                    '<html><body><main><a href="triage.json">triage audit</a>'
                    "</main></body></html>",
                    encoding="utf-8",
                )
                audit = {
                    "schema_version": "1.0",
                    "artifact_type": (
                        "EvidenceRadar_Editions_PrefetchTriageAudit"
                    ),
                    "journal": "Example Journal",
                    "journal_slug": "example-journal",
                    "period_key": "2026-08",
                    "revision": 1,
                    "articles": [
                        triage_record(1, route="FETCH_CANDIDATE"),
                        triage_record(2, route="RESERVE"),
                        triage_record(3, route="RESERVE"),
                    ],
                }
                (revision / "triage.json").write_text(
                    json.dumps(audit),
                    encoding="utf-8",
                )
                return {"base_url": "https://example.test/"}

            with patch.object(
                pages_v12,
                "build_v11_pages_site",
                side_effect=fake_base,
            ):
                links = pages_v13.build_pages_site(
                    output_dir=output,
                    repository="owner/repo",
                    editions_root=editions,
                    catalog_root=catalog,
                )

            for name in (
                "editorial-shortlist.json",
                "editorial-shortlist.html",
                "editorial-shortlist-policy.json",
                "abstract-fetch-plan.json",
                "journal-impact-metrics.json",
            ):
                self.assertTrue((output / name).is_file(), name)
            self.assertTrue((revision / "shortlist.json").is_file())

            shortlist = json.loads(
                (output / "editorial-shortlist.json").read_text(encoding="utf-8")
            )
            plan = json.loads(
                (output / "abstract-fetch-plan.json").read_text(encoding="utf-8")
            )
            index = json.loads((output / "index.json").read_text(encoding="utf-8"))
            published_registry = json.loads(
                (output / "journal-impact-metrics.json").read_text(encoding="utf-8")
            )
            audit = json.loads(
                (revision / "shortlist.json").read_text(encoding="utf-8")
            )

            digest = impact_registry_sha256(published_registry)
            self.assertEqual(shortlist["schema_version"], "2.0")
            self.assertEqual(shortlist["counts"]["canonical_article_count"], 3)
            self.assertEqual(shortlist["counts"]["fetch_now_count"], 2)
            self.assertEqual(shortlist["counts"]["hold_reserve_count"], 1)
            self.assertEqual(plan["item_count"], 2)
            self.assertEqual(plan["impact_registry_sha256"], digest)
            self.assertEqual(shortlist["impact_registry_sha256"], digest)
            self.assertEqual(len(audit["articles"]), 3)
            self.assertEqual(
                index["journal_impact_registry"]["verified_metric_count"],
                1,
            )
            self.assertEqual(
                index["editorial_shortlist"]["impact_registry_sha256"],
                digest,
            )
            self.assertEqual(
                links["journal_impact_registry_url"],
                "https://example.test/journal-impact-metrics.json",
            )
            self.assertEqual(
                links["editorial_shortlist"]["impact_registry_sha256"],
                digest,
            )
            self.assertTrue(
                all(
                    item["abstract_fetch_requested"] is False
                    and item["abstract_acquired"] is False
                    and item["abstract_reviewed"] is False
                    and item["full_text_fetched"] is False
                    and item["evidence_evaluated"] is False
                    for item in audit["articles"]
                )
            )


if __name__ == "__main__":
    unittest.main()
