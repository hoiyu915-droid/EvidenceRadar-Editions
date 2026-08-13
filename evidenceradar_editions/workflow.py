from __future__ import annotations

import os
from pathlib import Path

from .bundle import write_bundle
from .engine import build_run
from .models import EditionSpec
from .utils import parse_iso_date
from .validate import validate_bundle

RADAR_PIN = "6da659df845e4b76072dae016120ca76ed9c27c4"


def main() -> int:
    journal = os.environ["EDITION_JOURNAL"]
    slug = os.environ["EDITION_SLUG"]
    start = parse_iso_date(os.environ["EDITION_START"])
    end = parse_iso_date(os.environ["EDITION_END"])
    issn = os.environ.get("EDITION_ISSN") or None
    max_records = int(os.environ.get("EDITION_MAX_RECORDS", "500"))
    spec = EditionSpec(journal=journal, start_date=start, end_date=end, slug=slug, issn=issn, max_records=max_records)
    output = Path("dist/edition")
    run = build_run(spec, radar_root=Path("_upstream/EvidenceRadar"), radar_commit=RADAR_PIN)
    write_bundle(run, output)
    errors = validate_bundle(output)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"PASS: {run['edition_id']} ({run['counts']['articles']} articles)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
