from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from . import __version__
from .fileio import save_text
from .naming import build_identity
from .render import render_html
from .serialization import json_text
from .utils import sha256_bytes, utc_now_iso

LEGACY_JSON_NAME = "EvidenceRadar_Edition.json"
LEGACY_HTML_NAME = "EvidenceRadar_Edition.html"
LEGACY_MANIFEST_NAME = "EvidenceRadar_Edition.manifest.json"


@dataclass(frozen=True)
class BundlePaths:
    root: Path
    manifest_path: Path
    json_path: Path
    html_path: Path
    manifest: dict[str, Any]


def _ensure_artifact_names(run: dict[str, Any]) -> dict[str, str]:
    existing = run.get("artifacts") or {}
    required = ("stem", "edition_json", "report_html", "manifest_json")
    if all(existing.get(key) for key in required):
        return {key: str(existing[key]) for key in required}
    scope = run.get("scope") or {}
    identity = build_identity(
        slug=str(scope.get("slug") or "edition"),
        start=date.fromisoformat(str(scope.get("start_date"))),
        end=date.fromisoformat(str(scope.get("end_date"))),
        period_kind_requested=str(scope.get("period_kind_requested") or "auto"),
        revision=int(scope.get("revision") or 1),
    )
    artifacts = {
        "stem": identity.artifact_stem,
        "edition_json": f"{identity.artifact_stem}.json",
        "report_html": f"{identity.artifact_stem}.html",
        "manifest_json": f"{identity.artifact_stem}.manifest.json",
        "translation_request_json": f"{identity.artifact_stem}.translation-request.zh-TW.json",
        "translation_response_json": f"{identity.artifact_stem}.translation-response.zh-TW.json",
    }
    run["artifacts"] = artifacts
    return artifacts


def artifact_names(run: dict[str, Any]) -> dict[str, str]:
    return dict(_ensure_artifact_names(run))


def write_bundle(run: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    names = _ensure_artifact_names(run)
    json_payload = json_text(run)
    html_payload = render_html(run)
    json_bytes = json_payload.encode("utf-8")
    html_bytes = html_payload.encode("utf-8")
    scope = run.get("scope") or {}
    translation = run.get("translation") or {}
    manifest = {
        "schema_version": "2.0",
        "artifact_type": "EvidenceRadar_Edition_Manifest",
        "edition_id": run.get("edition_id"),
        "edition_key": run.get("edition_key"),
        "publication_id": run.get("publication_id") or run.get("edition_id"),
        "journal": scope.get("journal"),
        "journal_slug": scope.get("journal_slug") or scope.get("slug"),
        "period_kind": scope.get("period_kind"),
        "period_key": scope.get("period_key"),
        "period_start": scope.get("start_date"),
        "period_end": scope.get("end_date"),
        "revision": int(scope.get("revision") or 1),
        "created_at": utc_now_iso(),
        "software_version": __version__,
        "source_reconstruction_semantics": run.get("data_semantics"),
        "run_status": run.get("run_status"),
        "upstream_radar_commit": (run.get("upstream_radar") or {}).get("commit"),
        "article_count": (run.get("counts") or {}).get("articles"),
        "translated_article_count": (run.get("counts") or {}).get(
            "translated_articles", 0
        ),
        "publication_language": "zh-TW",
        "translation_status": translation.get("status") or "NOT_REQUESTED",
        "translation_provenance": {
            "source_edition_sha256": translation.get("source_edition_sha256"),
            "request_binding_sha256": translation.get("request_binding_sha256"),
            "response_sha256": translation.get("response_sha256"),
        },
        "files": {
            "edition_json": {
                "name": names["edition_json"],
                "sha256": sha256_bytes(json_bytes),
                "bytes": len(json_bytes),
                "media_type": "application/json",
            },
            "report_html": {
                "name": names["report_html"],
                "sha256": sha256_bytes(html_bytes),
                "bytes": len(html_bytes),
                "media_type": "text/html; charset=utf-8",
            },
        },
        "manifest_name": names["manifest_json"],
    }
    save_text(output_dir / names["edition_json"], json_payload)
    save_text(output_dir / names["report_html"], html_payload)
    save_text(output_dir / names["manifest_json"], json_text(manifest))
    return manifest


def _discover_manifest(root: Path) -> Path:
    candidates = sorted(root.glob("*.manifest.json"))
    if not candidates:
        legacy = root / LEGACY_MANIFEST_NAME
        if legacy.is_file():
            return legacy
        raise FileNotFoundError("edition manifest is missing")
    if len(candidates) != 1:
        raise ValueError(
            f"edition bundle must contain exactly one manifest, found {len(candidates)}"
        )
    return candidates[0]


def load_bundle_paths(root: Path) -> BundlePaths:
    root = Path(root)
    manifest_path = _discover_manifest(root)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("edition manifest must be a JSON object")
    files = manifest.get("files") or {}
    if "edition_json" in files and "report_html" in files:
        json_name = str((files.get("edition_json") or {}).get("name") or "")
        html_name = str((files.get("report_html") or {}).get("name") or "")
    else:
        json_name = LEGACY_JSON_NAME
        html_name = LEGACY_HTML_NAME
    if not json_name or not html_name:
        raise ValueError("edition manifest does not name its data and HTML files")
    for name in (json_name, html_name, manifest_path.name):
        if Path(name).name != name:
            raise ValueError(f"unsafe artifact filename in manifest: {name}")
    return BundlePaths(
        root=root,
        manifest_path=manifest_path,
        json_path=root / json_name,
        html_path=root / html_name,
        manifest=manifest,
    )
