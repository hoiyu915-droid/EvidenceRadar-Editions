from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
from typing import Any

from .bundle import write_bundle
from .incremental_backfill import build_incremental_month_backfill
from .serialization import json_text
from .store_v3 import store_bundle, validate_stored_publication
from .utils import parse_iso_date, utc_now_iso
from .validate import validate_bundle


def load_batch_request(path: Path) -> dict[str, Any]:
    request = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(request, dict):
        raise ValueError("backfill request must be a JSON object")
    if request.get("artifact_type") != "EvidenceRadar_Editions_BackfillRequest":
        raise ValueError("unsupported backfill request artifact_type")
    if request.get("schema_version") != "1.0":
        raise ValueError("unsupported backfill request schema_version")
    request_id = str(request.get("request_id") or "")
    if not request_id or not all(character.isalnum() or character in "-_" for character in request_id):
        raise ValueError("backfill request_id is missing or unsafe")
    start = parse_iso_date(str(request.get("acquisition_start") or ""))
    end = parse_iso_date(str(request.get("acquisition_end") or ""))
    if start > end:
        raise ValueError("backfill acquisition_start is after acquisition_end")
    if (start.year, start.month) != (end.year, end.month):
        raise ValueError("one backfill batch cannot cross a calendar month")
    revision = int(request.get("revision") or 0)
    if revision < 1:
        raise ValueError("backfill revision must be positive")
    raw_journals = request.get("journals")
    if not isinstance(raw_journals, list) or not raw_journals:
        raise ValueError("backfill request journals must be a non-empty list")
    journals = [str(value) for value in raw_journals]
    if len(journals) != len(set(journals)):
        raise ValueError("backfill request contains duplicate journals")
    for journal in journals:
        if not journal or not all(character.islower() or character.isdigit() or character == "-" for character in journal):
            raise ValueError(f"unsafe journal slug in backfill request: {journal!r}")
    provider = str(request.get("provider") or "").strip().casefold()
    if provider and not all(
        character.islower() or character.isdigit() or character == "-"
        for character in provider
    ):
        raise ValueError(f"unsafe provider in backfill request: {provider!r}")
    raw_limits = request.get("max_records_by_journal") or {}
    if not isinstance(raw_limits, dict):
        raise ValueError("backfill max_records_by_journal must be an object")
    limits: dict[str, int] = {}
    for journal, value in raw_limits.items():
        if journal not in journals:
            raise ValueError(
                f"backfill max_records override is outside the journal batch: {journal}"
            )
        if isinstance(value, bool):
            raise ValueError(f"invalid max_records override for {journal}")
        limit = int(value)
        if limit < 1 or limit > 5000:
            raise ValueError(f"max_records override is out of bounds for {journal}")
        limits[journal] = limit
    raw_overrides = request.get("policy_override_journals") or []
    if not isinstance(raw_overrides, list):
        raise ValueError("backfill policy_override_journals must be a list")
    policy_overrides = [str(value) for value in raw_overrides]
    if len(policy_overrides) != len(set(policy_overrides)):
        raise ValueError("backfill policy_override_journals contains duplicates")
    for journal in policy_overrides:
        if journal not in journals:
            raise ValueError(
                f"backfill policy override is outside the journal batch: {journal}"
            )
        if journal not in limits:
            raise ValueError(
                f"backfill policy override requires an explicit max_records limit: {journal}"
            )
    normalized = dict(request)
    normalized["request_id"] = request_id
    normalized["acquisition_start"] = start.isoformat()
    normalized["acquisition_end"] = end.isoformat()
    normalized["revision"] = revision
    normalized["journals"] = journals
    normalized["provider"] = provider or None
    normalized["max_records_by_journal"] = limits
    normalized["policy_override_journals"] = policy_overrides
    return normalized


def _existing_target(
    *,
    editions_root: Path,
    journal_slug: str,
    end: date,
    revision: int,
) -> Path:
    return (
        Path(editions_root)
        / journal_slug
        / f"{end.year:04d}"
        / f"{end.month:02d}"
        / f"r{revision:02d}"
    )


def _result_from_stored(target: Path) -> dict[str, Any]:
    errors = validate_stored_publication(target, require_zh_tw=False)
    if errors:
        raise ValueError(f"existing backfill target is invalid: {target}\n" + "\n".join(errors))
    edition = json.loads((target / "edition.json").read_text(encoding="utf-8"))
    info = edition.get("incremental_backfill") or {}
    if not info:
        raise ValueError(f"existing target is not an incremental backfill: {target}")
    return {
        "journal_slug": (edition.get("scope") or {}).get("journal_slug"),
        "publication_id": edition.get("publication_id"),
        "target": target.as_posix(),
        "status": "IDEMPOTENT_EXISTING",
        **info,
    }


def run_batch(
    *,
    request: dict[str, Any],
    editions_root: Path,
    catalog_root: Path,
    radar_root: Path | None,
    radar_commit: str | None,
    work_dir: Path,
    receipt_output: Path,
) -> dict[str, Any]:
    start = parse_iso_date(request["acquisition_start"])
    end = parse_iso_date(request["acquisition_end"])
    revision = int(request["revision"])
    max_records_by_journal = request.get("max_records_by_journal") or {}
    policy_override_journals = set(request.get("policy_override_journals") or [])
    if Path(receipt_output).is_file():
        existing = json.loads(Path(receipt_output).read_text(encoding="utf-8"))
        if (
            existing.get("artifact_type") != "EvidenceRadar_Editions_BackfillReceipt"
            or existing.get("request_id") != request["request_id"]
            or existing.get("acquisition_start") != start.isoformat()
            or existing.get("acquisition_end") != end.isoformat()
            or int(existing.get("revision") or 0) != revision
        ):
            raise ValueError("existing backfill receipt differs from the current request")
        observed = [str(item.get("journal_slug") or "") for item in existing.get("journals") or []]
        if observed != request["journals"]:
            raise ValueError("existing backfill receipt journal order differs from request")
        for item in existing.get("journals") or []:
            _result_from_stored(Path(str(item.get("target") or "")))
        return existing

    results: list[dict[str, Any]] = []
    for journal_slug in request["journals"]:
        target = _existing_target(
            editions_root=editions_root,
            journal_slug=journal_slug,
            end=end,
            revision=revision,
        )
        if target.exists():
            result = _result_from_stored(target)
            if result.get("acquisition_start") != start.isoformat() or result.get("acquisition_end") != end.isoformat():
                raise ValueError(f"existing backfill window differs from request: {target}")
            results.append(result)
            continue

        built = build_incremental_month_backfill(
            journal_slug=journal_slug,
            acquisition_start=start,
            acquisition_end=end,
            revision=revision,
            editions_root=editions_root,
            catalog_root=catalog_root,
            radar_root=radar_root,
            radar_commit=radar_commit,
            max_records=max_records_by_journal.get(journal_slug),
            provider=request.get("provider"),
            allow_policy_override=journal_slug in policy_override_journals,
        )
        bundle_dir = Path(work_dir) / journal_slug
        write_bundle(built.run, bundle_dir)
        errors = validate_bundle(bundle_dir, require_zh_tw=False)
        if errors:
            raise ValueError(f"generated backfill bundle is invalid: {journal_slug}\n" + "\n".join(errors))
        stored = store_bundle(bundle_dir, editions_root, require_zh_tw=False)
        try:
            stored_target = stored.resolve().relative_to(Path.cwd().resolve()).as_posix()
        except ValueError as exc:
            raise ValueError(f"stored backfill target is outside the repository: {stored}") from exc
        info = built.run["incremental_backfill"]
        results.append(
            {
                "journal_slug": journal_slug,
                "publication_id": built.run["publication_id"],
                "target": stored_target,
                "status": "PUBLISHED",
                **info,
            }
        )

    receipt = {
        "artifact_type": "EvidenceRadar_Editions_BackfillReceipt",
        "schema_version": "1.0",
        "request_id": request["request_id"],
        "generated_at": utc_now_iso(),
        "period_key": f"{end.year:04d}-{end.month:02d}",
        "acquisition_start": start.isoformat(),
        "acquisition_end": end.isoformat(),
        "revision": revision,
        "journal_count": len(results),
        "journals": results,
        "semantics": (
            "Only the missing date suffix was acquired live. Each result is a new "
            "full monthly snapshot revision composed with an immutable validated base."
        ),
    }
    Path(receipt_output).parent.mkdir(parents=True, exist_ok=True)
    Path(receipt_output).write_text(json_text(receipt), encoding="utf-8")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evidenceradar_editions.incremental_batch")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--editions-root", type=Path, default=Path("editions"))
    parser.add_argument("--catalog-root", type=Path, default=Path("catalog"))
    parser.add_argument("--radar-root", type=Path)
    parser.add_argument("--radar-commit")
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--receipt-output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        request = load_batch_request(args.request)
        receipt = run_batch(
            request=request,
            editions_root=args.editions_root,
            catalog_root=args.catalog_root,
            radar_root=args.radar_root,
            radar_commit=args.radar_commit,
            work_dir=args.work_dir,
            receipt_output=args.receipt_output,
        )
        print(json.dumps(receipt, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["load_batch_request", "main", "run_batch"]
