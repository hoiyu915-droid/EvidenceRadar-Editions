from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import __version__
from .fileio import save_text
from .render import render_html
from .utils import sha256_bytes, utc_now_iso

JSON_NAME = "EvidenceRadar_Edition.json"
HTML_NAME = "EvidenceRadar_Edition.html"
MANIFEST_NAME = "EvidenceRadar_Edition.manifest.json"


def write_bundle(run: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    json_text = json.dumps(run, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    html_text = render_html(run)
    json_bytes = json_text.encode("utf-8")
    html_bytes = html_text.encode("utf-8")
    manifest = {
        "schema_version": "1.0",
        "artifact_type": "EvidenceRadar_Edition_Manifest",
        "edition_id": run["edition_id"],
        "created_at": utc_now_iso(),
        "software_version": __version__,
        "source_reconstruction_semantics": run["data_semantics"],
        "upstream_radar_commit": run["upstream_radar"].get("commit"),
        "article_count": run["counts"]["articles"],
        "files": {
            JSON_NAME: {"sha256": sha256_bytes(json_bytes), "bytes": len(json_bytes)},
            HTML_NAME: {"sha256": sha256_bytes(html_bytes), "bytes": len(html_bytes)},
        },
    }
    save_text(output_dir / JSON_NAME, json_text)
    save_text(output_dir / HTML_NAME, html_text)
    save_text(output_dir / MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return manifest
