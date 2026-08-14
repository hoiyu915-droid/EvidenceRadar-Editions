import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evidenceradar_editions import pages_v12


def triage_record(
    index: int,
    *,
    route: str,
    path: str,
    title: str,
    integrity: bool = False,
):
    canonical_id = f"doi:10.1000/example.{index}"
    return {
        "canonical_id": canonical_id,
        "journal": "Example Journal",
        "journal_slug": "example-journal",
        "period_key": "2026-08",
        "revision": 1,
        "publication_date": "2026-08-13",
        "publication_date_precision": "DAY",
        "title_original": title,
        "title_zh_tw": f"測試文章 {index}",
        "article_type": "journal-article",
        "authors": ["A Author"],
        "identifiers": {
            "doi": canonical_id.removeprefix("doi:"),
            "pmid": str(900000 + index),
            "pmcid": None,
        },
        "source_urls": [f"https://doi.org/{canonical_id.removeprefix('doi:')}"],
        "categories": ["clinical_medicine"],
        "publication_role": "concern" if integrity else "primary",
        "matched_paths": [path],
        "primary_path": path,
        "score": 95,
        "raw_score": 95,
        "reason_codes": [path, "PMID_ROUTE", "DOI_ROUTE"],
        "route": "INTEGRITY_REVIEW" if integrity else route,
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


class PagesEditorialShortlistTests(unittest.TestCase):
    def test_pages_publishes_shortlist_plan_and_per_edition_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "site"
            catalog = root / "catalog"
            editions = root / "editions"
            catalog.mkdir()
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
                    '<html><body><main><a href="browse.json">browse JSON</a>'
                    '<a href="triage.json">triage audit</a></main></body></html>',
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
                        triage_record(
                            1,
                            route="FETCH_CANDIDATE",
                            path="EVIDENCE_SYNTHESIS",
                            title=(
                                "Systematic review and meta-analysis of "
                                "intervention X"
                            ),
                        ),
                        triage_record(
                            2,
                            route="INTEGRITY_REVIEW",
                            path="INTEGRITY_EVENT",
                            title="Retraction Note: Example article",
                            integrity=True,
                        ),
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
                links = pages_v12.build_pages_site(
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
            ):
                self.assertTrue((output / name).is_file(), name)
            self.assertTrue((revision / "shortlist.json").is_file())

            shortlist = json.loads(
                (output / "editorial-shortlist.json").read_text(
                    encoding="utf-8"
                )
            )
            plan = json.loads(
                (output / "abstract-fetch-plan.json").read_text(
                    encoding="utf-8"
                )
            )
            audit = json.loads(
                (revision / "shortlist.json").read_text(encoding="utf-8")
            )
            self.assertEqual(shortlist["counts"]["canonical_article_count"], 2)
            self.assertEqual(shortlist["counts"]["fetch_now_count"], 1)
            self.assertEqual(
                shortlist["counts"]["integrity_attention_count"],
                1,
            )
            self.assertEqual(plan["item_count"], 1)
            self.assertEqual(len(audit["articles"]), 2)
            self.assertEqual(
                sum(
                    1
                    for item in audit["articles"]
                    if item["editorial_route"] == "FETCH_NOW"
                ),
                1,
            )
            self.assertTrue(
                all(
                    item["abstract_acquired"] is False
                    and item["abstract_reviewed"] is False
                    and item["evidence_evaluated"] is False
                    for item in audit["articles"]
                )
            )

            portal = (output / "index.html").read_text(encoding="utf-8")
            revision_html = (revision / "index.html").read_text(
                encoding="utf-8"
            )
            self.assertIn("editorial-shortlist.html", portal)
            self.assertIn('href="shortlist.json"', revision_html)
            self.assertEqual(
                links["editorial_shortlist_url"],
                "https://example.test/editorial-shortlist.html",
            )
            self.assertEqual(
                links["abstract_fetch_plan_url"],
                "https://example.test/abstract-fetch-plan.json",
            )
            self.assertEqual(
                links["editorial_shortlist"]["edition_audit_count"],
                1,
            )


if __name__ == "__main__":
    unittest.main()
