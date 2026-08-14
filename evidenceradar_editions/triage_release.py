from __future__ import annotations

import argparse
import json
from pathlib import Path

from .serialization import json_text
from .triage_delivery import build_triage_delivery


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evidenceradar_editions.triage_release"
    )
    parser.add_argument("--editions-root", type=Path, default=Path("editions"))
    parser.add_argument("--catalog-root", type=Path, default=Path("catalog"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--base-url")
    parser.add_argument("--allow-untranslated", action="store_true")
    return parser


def build_release(
    *,
    output_dir: Path,
    repository: str,
    editions_root: Path,
    catalog_root: Path,
    base_url: str | None = None,
    require_zh_tw: bool = True,
) -> dict[str, object]:
    links = build_triage_delivery(
        output_dir=output_dir,
        repository=repository,
        editions_root=editions_root,
        catalog_root=catalog_root,
        base_url=base_url,
        require_zh_tw=require_zh_tw,
    )
    summary = dict(links.get("metadata_triage_summary") or {})
    links["search_projection"] = {
        "semantics": "latest_revision_per_journal_period_metadata_triage_projected",
        "canonical_article_count": summary.get("canonical_article_count", 0),
        "projected_article_count": summary.get(
            "default_projected_article_count", 0
        ),
        "omitted_article_count": summary.get(
            "default_omitted_article_count", 0
        ),
        "processing_mode_counts": summary.get("processing_mode_counts") or {},
        "metadata_triage_policy_id": summary.get("policy_id"),
        "search_index_file": "search-index.json",
    }
    (Path(output_dir) / "links.json").write_text(
        json_text(links), encoding="utf-8"
    )
    return links


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        links = build_release(
            output_dir=args.output_dir,
            repository=args.repository,
            editions_root=args.editions_root,
            catalog_root=args.catalog_root,
            base_url=args.base_url,
            require_zh_tw=not args.allow_untranslated,
        )
        print(json.dumps(links, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
