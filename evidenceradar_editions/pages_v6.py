from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .pages_v5 import build_pages_site as build_v5_pages_site
from .serialization import json_text


def build_pages_site(
    *,
    output_dir: Path,
    repository: str,
    editions_root: Path | None = None,
    archive_root: Path | None = None,
    catalog_root: Path | None = None,
    base_url: str | None = None,
    require_zh_tw: bool = True,
) -> dict[str, Any]:
    links = build_v5_pages_site(
        output_dir=output_dir,
        repository=repository,
        editions_root=editions_root,
        archive_root=archive_root,
        catalog_root=catalog_root,
        base_url=base_url,
        require_zh_tw=require_zh_tw,
    )
    if catalog_root is None:
        return links

    source = Path(catalog_root) / "coverage"
    ledgers = sorted(source.glob("*.json")) if source.is_dir() else []
    if not ledgers:
        return links

    output = Path(output_dir)
    public_dir = output / "coverage"
    public_dir.mkdir(parents=True, exist_ok=True)
    for path in ledgers:
        shutil.copyfile(path, public_dir / path.name)

    latest = ledgers[-1]
    coverage = json.loads(latest.read_text(encoding="utf-8"))
    summary = {
        "period_key": coverage.get("period_key"),
        "coverage_through": coverage.get("coverage_through"),
        "registry_count": coverage.get("registry_count"),
        "processed_journal_count": coverage.get("processed_journal_count"),
        "published_journal_count": coverage.get("published_journal_count"),
        "no_edition_count": coverage.get("no_edition_count"),
        "status_counts": coverage.get("status_counts") or {},
        "file": f"coverage/{latest.name}",
    }

    catalog_path = output / "index.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["period_coverage_summary"] = summary
    catalog_path.write_text(json_text(catalog), encoding="utf-8")

    public_base = str(links.get("base_url") or "")
    links["period_coverage_url"] = public_base + f"coverage/{latest.name}"
    links["processed_journal_count"] = coverage.get("processed_journal_count")
    links_path = output / "links.json"
    links_path.write_text(json_text(links), encoding="utf-8")
    return links
