from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from evidenceradar_editions.pipeline import BuildError, BuildOptions, build_edition
from evidenceradar_editions.validate import ValidationError, validate_edition_directory

ROOT = Path(__file__).resolve().parents[1]


def test_fixture_build_is_complete_and_deduplicated(tmp_path: Path) -> None:
    output = tmp_path / "edition"
    summary = build_edition(
        BuildOptions(
            collection_path=ROOT / "config/collections/jama-network-open.yml",
            start=date(2026, 8, 1),
            end=date(2026, 8, 31),
            output_dir=output,
            fixture_dir=ROOT / "tests/fixtures",
            strict_sources=True,
        )
    )
    assert summary["valid"] is True
    assert summary["article_count"] == 2
    assert summary["raw_record_count"] == 6
    edition = json.loads((output / "edition.json").read_text(encoding="utf-8"))
    assert edition["edition_id"] == "jama-network-open--2026-08"
    assert edition["status"] == "COMPLETE"
    assert edition["provenance"]["artifact_dependency"] is False
    assert edition["provenance"]["upstream_radar"]["artifacts_consumed"] is False
    assert {item["canonical_id"] for item in edition["articles"]} == {
        "doi:10.1001/jamanetworkopen.2026.1234",
        "doi:10.1001/jamanetworkopen.2026.5678",
    }
    assert "data-edition-id=\"jama-network-open--2026-08\"" in (
        output / "index.html"
    ).read_text(encoding="utf-8")


def test_build_refuses_to_overwrite_without_replace(tmp_path: Path) -> None:
    output = tmp_path / "edition"
    options = BuildOptions(
        collection_path=ROOT / "config/collections/jama-network-open.yml",
        start=date(2026, 8, 1),
        end=date(2026, 8, 31),
        output_dir=output,
        fixture_dir=ROOT / "tests/fixtures",
    )
    build_edition(options)
    with pytest.raises(BuildError, match="already exists"):
        build_edition(options)
    replacement = build_edition(BuildOptions(**{**options.__dict__, "replace": True}))
    assert replacement["valid"] is True


def test_validator_detects_tampering(tmp_path: Path) -> None:
    output = tmp_path / "edition"
    build_edition(
        BuildOptions(
            collection_path=ROOT / "config/collections/jama-network-open.yml",
            start=date(2026, 8, 1),
            end=date(2026, 8, 31),
            output_dir=output,
            fixture_dir=ROOT / "tests/fixtures",
        )
    )
    (output / "edition.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        validate_edition_directory(output)


def test_build_refuses_current_directory_as_output(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(BuildError, match="current working directory"):
        build_edition(
            BuildOptions(
                collection_path=ROOT / "config/collections/jama-network-open.yml",
                start=date(2026, 8, 1),
                end=date(2026, 8, 31),
                output_dir=Path("."),
                fixture_dir=ROOT / "tests/fixtures",
                replace=True,
            )
        )


def test_validator_detects_source_status_drift(tmp_path: Path) -> None:
    output = tmp_path / "edition"
    build_edition(
        BuildOptions(
            collection_path=ROOT / "config/collections/jama-network-open.yml",
            start=date(2026, 8, 1),
            end=date(2026, 8, 31),
            output_dir=output,
            fixture_dir=ROOT / "tests/fixtures",
        )
    )
    sources_path = output / "sources.json"
    sources = json.loads(sources_path.read_text(encoding="utf-8"))
    sources["receipts"][0]["status"] = "FAILED"
    sources["receipts"][0]["error"] = "synthetic drift"
    sources_path.write_text(json.dumps(sources), encoding="utf-8")
    with pytest.raises(ValidationError, match="edition status"):
        validate_edition_directory(output)


def test_truncated_receipt_makes_edition_partial(tmp_path: Path, monkeypatch) -> None:
    from evidenceradar_editions import pipeline
    from evidenceradar_editions.models import Article, SourceReceipt
    from evidenceradar_editions.sources import SourceResult

    def fake_fetch(source, collection, start, end, **kwargs):
        return SourceResult(
            articles=[
                Article(
                    title="Bounded record",
                    journal=collection.name,
                    publication_date="2026-08-10",
                    issns=list(collection.issns),
                    doi="10.1001/bounded",
                    sources=[source],
                )
            ],
            receipt=SourceReceipt(
                source=source,
                status="SUCCESS",
                query="synthetic bounded query",
                endpoint="https://example.org/source",
                retrieved_at="2026-08-14T00:00:00+00:00",
                returned_count=1,
                request_count=1,
                metadata={"truncated": True},
            ),
        )

    monkeypatch.setattr(pipeline, "fetch_source", fake_fetch)
    output = tmp_path / "partial"
    summary = build_edition(
        BuildOptions(
            collection_path=ROOT / "config/collections/jama-network-open.yml",
            start=date(2026, 8, 1),
            end=date(2026, 8, 31),
            output_dir=output,
            sources=("pubmed",),
        )
    )
    assert summary["status"] == "PARTIAL"
    edition = json.loads((output / "edition.json").read_text(encoding="utf-8"))
    assert any("record bound" in warning for warning in edition["warnings"])
