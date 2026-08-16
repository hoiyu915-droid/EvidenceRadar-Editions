from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from evidenceradar_editions.adapters import CambridgeCoreAdapter
from evidenceradar_editions.adapters.cambridge_core import OA_JOURNAL_LISTING
from evidenceradar_editions.http import HttpClient
from evidenceradar_editions.provider_catalog import validate_provider_catalog


def build_snapshot() -> dict[str, object]:
    journals = CambridgeCoreAdapter(HttpClient()).list_journals()
    return validate_provider_catalog(
        {
            "artifact_type": "EvidenceRadar_Editions_ProviderCatalog",
            "schema_version": "1.0",
            "provider": "cambridge",
            "publisher": "Cambridge University Press",
            "scope": "fully_open_access_journals",
            "source_url": OA_JOURNAL_LISTING,
            "observed_at": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "journal_count": len(journals),
            "journals": journals,
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh the Cambridge Core fully-OA provider catalog snapshot."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("catalog/providers/cambridge.json"),
    )
    args = parser.parse_args()
    snapshot = build_snapshot()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "provider": snapshot["provider"],
                "journal_count": snapshot["journal_count"],
                "observed_at": snapshot["observed_at"],
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
