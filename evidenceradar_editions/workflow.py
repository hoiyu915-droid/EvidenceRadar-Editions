from __future__ import annotations

import json
import os
from pathlib import Path

from .bundle import write_bundle
from .engine import build_run
from .models import EditionSpec
from .translation import write_translation_request
from .utils import parse_iso_date
from .validate import validate_bundle

RADAR_PIN = "6da659df845e4b76072dae016120ca76ed9c27c4"


def _github_output(values: dict[str, object]) -> None:
    target = os.environ.get("GITHUB_OUTPUT")
    if not target:
        return
    with Path(target).open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            text = str(value).replace("\n", " ")
            handle.write(f"{key}={text}\n")


def main() -> int:
    journal = os.environ["EDITION_JOURNAL"]
    slug = os.environ["EDITION_SLUG"]
    start = parse_iso_date(os.environ["EDITION_START"])
    end = parse_iso_date(os.environ["EDITION_END"])
    issn = os.environ.get("EDITION_ISSN") or None
    max_records = int(os.environ.get("EDITION_MAX_RECORDS", "500"))
    period_kind = os.environ.get("EDITION_PERIOD_KIND", "auto")
    revision = int(os.environ.get("EDITION_REVISION", "1"))
    sources = tuple(
        value.strip()
        for value in os.environ.get(
            "EDITION_SOURCES", "pubmed,europe_pmc,crossref,radar_rss"
        ).split(",")
        if value.strip()
    )
    spec = EditionSpec(
        journal=journal,
        start_date=start,
        end_date=end,
        slug=slug,
        issn=issn,
        sources=sources,
        max_records=max_records,
        period_kind=period_kind,
        revision=revision,
    )
    output = Path(os.environ.get("EDITION_OUTPUT_DIR", "dist/edition"))
    radar_root_value = os.environ.get("EDITION_RADAR_ROOT", "_upstream/EvidenceRadar")
    radar_root = Path(radar_root_value) if radar_root_value else None
    run = build_run(
        spec,
        radar_root=radar_root,
        radar_commit=os.environ.get("EDITION_RADAR_COMMIT", RADAR_PIN),
    )
    manifest = write_bundle(run, output)
    request_name = str(run["artifacts"]["translation_request_json"])
    request = write_translation_request(run, output / request_name)
    errors = validate_bundle(output)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    values = {
        "edition_id": run["edition_id"],
        "artifact_name": run["publication_id"],
        "bundle_dir": output,
        "edition_json": manifest["files"]["edition_json"]["name"],
        "report_html": manifest["files"]["report_html"]["name"],
        "manifest_json": manifest["manifest_name"],
        "translation_request_json": request_name,
        "article_count": run["counts"]["articles"],
        "run_status": run["run_status"],
        "request_binding_sha256": request["request_binding_sha256"],
    }
    _github_output(values)
    print(json.dumps(values, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
