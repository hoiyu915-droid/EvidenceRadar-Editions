from __future__ import annotations

from datetime import date
import json
import tempfile
import unittest
from pathlib import Path

from evidenceradar_editions.bundle import write_bundle
from evidenceradar_editions.engine import build_run
from evidenceradar_editions.incremental_backfill import compose_incremental_month_revision
from evidenceradar_editions.models import Article, EditionSpec, SourceRecord
from evidenceradar_editions.utils import sha256_file
from evidenceradar_editions.validate import validate_bundle


HTML = b"""
<html><body><ul>
<li class="item nocertificate">
  <h4><a class="paper-data-bs-title darkblue" href="https://openreview.net/pdf?id=NewOne123"><b>A New Paper</b></a></h4>
  <p><i>Ada Lovelace, Grace Hopper</i>, August 2026<br>
  [<a href="https://openreview.net/forum?id=NewOne123">openreview</a>]</p>
</li>
<li class="item nocertificate">
  <h4><a class="paper-data-bs-title darkblue" href="https://openreview.net/pdf?id=NewTwo_456"><b>Another Paper</b></a></h4>
  <p><i>Alan Turing</i>, August 2026<br>
  [<a href="https://openreview.net/forum?id=NewTwo_456">openreview</a>]</p>
</li>
<li class="item nocertificate">
  <h4><a class="paper-data-bs-title darkblue" href="https://openreview.net/pdf?id=OldJuly"><b>Older Paper</b></a></h4>
  <p><i>Older Author</i>, July 2026<br>
  [<a href="https://openreview.net/forum?id=OldJuly">openreview</a>]</p>
</li>
</ul></body></html>
"""


class _Client:
    def __init__(self, payload: bytes = HTML) -> None:
        self.payload = payload

    def get_bytes(self, url: str, *, limit: int | None = None) -> bytes:
        self.url = url
        self.limit = limit
        return self.payload


class TmlrOfficialSnapshotTests(unittest.TestCase):
    def spec(self) -> EditionSpec:
        return EditionSpec(
            journal="Transactions on Machine Learning Research",
            issn="2835-8856",
            slug="tmlr",
            start_date=date(2026, 8, 15),
            end_date=date(2026, 8, 19),
            sources=("tmlr_official_snapshot",),
            max_records=5000,
            period_kind="range",
            revision=1,
        )

    def test_first_party_month_snapshot_builds_valid_delta(self):
        run = build_run(self.spec(), client=_Client())
        self.assertEqual(run["run_status"], "COMPLETE")
        self.assertEqual(run["counts"]["articles"], 2)
        self.assertEqual(
            {article["canonical_id"] for article in run["articles"]},
            {"openreview:NewOne123", "openreview:NewTwo_456"},
        )
        self.assertEqual(run["source_checks"][0]["status"], "SUCCESS")
        self.assertIn("no day is inferred", run["source_checks"][0]["detail"])
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "bundle"
            write_bundle(run, bundle)
            self.assertEqual(validate_bundle(bundle, require_zh_tw=False), [])

    def test_openreview_source_id_is_stable_article_identity(self):
        article = Article(
            title="Changed title typography",
            journal="Transactions on Machine Learning Research",
            publication_date=date(2026, 8, 1),
            publication_date_precision="MONTH",
            source_records=[
                SourceRecord(
                    "tmlr_official_snapshot",
                    "Stable_Id-1",
                    "https://openreview.net/forum?id=Stable_Id-1",
                )
            ],
        )
        self.assertEqual(article.canonical_id, "openreview:Stable_Id-1")

    def test_snapshot_overlap_deduplicates_against_immutable_base(self):
        overlap = HTML.replace(b"NewOne123", b"JQA0EfQIfj")
        delta = build_run(self.spec(), client=_Client(overlap))
        base_dir = Path("editions/tmlr/2026/08/r01")
        base = json.loads((base_dir / "edition.json").read_text(encoding="utf-8"))
        manifest = json.loads(
            (base_dir / "manifest.json").read_text(encoding="utf-8")
        )
        run = compose_incremental_month_revision(
            base=base,
            base_manifest=manifest,
            base_edition_sha256=sha256_file(base_dir / "edition.json"),
            delta=delta,
            revision=2,
        )
        self.assertEqual(run["counts"]["articles"], 85)
        self.assertEqual(run["incremental_backfill"]["added_article_count"], 1)
        self.assertEqual(
            run["incremental_backfill"]["deduplicated_article_count"], 1
        )


if __name__ == "__main__":
    unittest.main()
