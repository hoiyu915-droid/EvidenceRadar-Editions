from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

from .archive import archive_destination, publish_bundle
from .bundle import BundlePaths, load_bundle_paths
from .render import render_html
from .serialization import json_text
from .utils import sha256_bytes, sha256_file
from .validate import validate_bundle


class PublicationStoreError(ValueError):
    """Raised when a canonical stored publication is unsafe or inconsistent."""


def _require_regular(path: Path, *, label: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise PublicationStoreError(f"{label} is missing or unsafe: {path}")


def _require_safe_directory_chain(root: Path, directory: Path) -> None:
    root = root.resolve()
    try:
        relative = directory.resolve().relative_to(root)
    except (OSError, ValueError) as exc:
        raise PublicationStoreError(
            f"publication path escapes its store: {directory}"
        ) from exc
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise PublicationStoreError(
                f"publication store path contains a symlink: {current}"
            )


def store_destination(manifest: dict[str, Any], store_root: Path) -> Path:
    return archive_destination(manifest, Path(store_root))


def _same_store_entry(paths: BundlePaths, target: Path) -> bool:
    try:
        stored_manifest = json.loads(
            (target / "manifest.json").read_text(encoding="utf-8")
        )
    except Exception:
        return False
    if stored_manifest != paths.manifest:
        return False
    stored_json = target / "edition.json"
    return (
        stored_json.is_file()
        and not stored_json.is_symlink()
        and sha256_file(stored_json) == sha256_file(paths.json_path)
    )


def store_bundle(
    bundle_dir: Path,
    store_root: Path,
    *,
    require_zh_tw: bool = True,
) -> Path:
    """Persist one validated revision as canonical JSON plus its manifest.

    HTML remains a deterministic projection.  It is regenerated and checked
    against the committed manifest when the store is materialized for Pages or
    a full downloadable archive.
    """

    errors = validate_bundle(bundle_dir, require_zh_tw=require_zh_tw)
    if errors:
        raise PublicationStoreError(
            "edition bundle is not storable:\n" + "\n".join(errors)
        )
    paths = load_bundle_paths(bundle_dir)
    store_root = Path(store_root)
    if store_root.is_symlink():
        raise PublicationStoreError("publication store root must not be a symlink")
    target = store_destination(paths.manifest, store_root)
    if target.exists():
        if target.is_symlink() or not target.is_dir():
            raise PublicationStoreError(f"publication store target is unsafe: {target}")
        if _same_store_entry(paths, target):
            return target
        raise FileExistsError(
            f"publication revision already exists with different bytes: {target}; increment revision"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    _require_safe_directory_chain(store_root, target.parent)
    temporary = target.parent / f".{target.name}.{uuid.uuid4().hex}.tmp"
    try:
        temporary.mkdir(parents=False, exist_ok=False)
        shutil.copyfile(paths.json_path, temporary / "edition.json")
        shutil.copyfile(paths.manifest_path, temporary / "manifest.json")
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return target


def _load_store_entry(
    directory: Path,
    *,
    store_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    if directory.is_symlink() or not directory.is_dir():
        raise PublicationStoreError(f"stored publication directory is unsafe: {directory}")
    _require_safe_directory_chain(store_root, directory)
    entries = {path.name for path in directory.iterdir()}
    if entries != {"edition.json", "manifest.json"}:
        raise PublicationStoreError(
            f"stored publication must contain exactly edition.json and manifest.json: {directory}"
        )
    edition_path = directory / "edition.json"
    manifest_path = directory / "manifest.json"
    _require_regular(edition_path, label="stored edition JSON")
    _require_regular(manifest_path, label="stored manifest")
    try:
        edition = json.loads(edition_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PublicationStoreError(
            f"stored publication JSON parse failed: {directory}: {exc}"
        ) from exc
    if not isinstance(edition, dict) or not isinstance(manifest, dict):
        raise PublicationStoreError(
            f"stored publication files must contain JSON objects: {directory}"
        )
    expected = store_destination(manifest, store_root).resolve()
    if directory.resolve() != expected:
        raise PublicationStoreError(
            f"stored publication path does not match manifest identity: {directory}"
        )
    canonical_json = json_text(edition).encode("utf-8")
    if edition_path.read_bytes() != canonical_json:
        raise PublicationStoreError(
            f"stored edition JSON is not canonical serialization: {directory}"
        )
    files = manifest.get("files") or {}
    json_record = files.get("edition_json") or {}
    html_record = files.get("report_html") or {}
    if json_record.get("sha256") != sha256_bytes(canonical_json):
        raise PublicationStoreError(
            f"stored edition JSON hash does not match manifest: {directory}"
        )
    if json_record.get("bytes") != len(canonical_json):
        raise PublicationStoreError(
            f"stored edition JSON size does not match manifest: {directory}"
        )
    html = render_html(edition)
    html_bytes = html.encode("utf-8")
    if html_record.get("sha256") != sha256_bytes(html_bytes):
        raise PublicationStoreError(
            f"canonical HTML hash does not match stored manifest: {directory}"
        )
    if html_record.get("bytes") != len(html_bytes):
        raise PublicationStoreError(
            f"canonical HTML size does not match stored manifest: {directory}"
        )
    if manifest.get("edition_id") != edition.get("edition_id"):
        raise PublicationStoreError(
            f"stored edition and manifest identity differ: {directory}"
        )
    return manifest, edition, html


def materialize_publication_store(
    store_root: Path,
    archive_root: Path,
    *,
    require_zh_tw: bool = True,
) -> list[Path]:
    """Validate the compact store and materialize full immutable archives."""

    store_root = Path(store_root)
    archive_root = Path(archive_root)
    if store_root.is_symlink():
        raise PublicationStoreError("publication store root must not be a symlink")
    if archive_root.is_symlink():
        raise PublicationStoreError("archive root must not be a symlink")
    archive_root.mkdir(parents=True, exist_ok=True)
    if not store_root.exists():
        return []
    if not store_root.is_dir():
        raise PublicationStoreError(f"publication store root is not a directory: {store_root}")

    targets: list[Path] = []
    manifests = sorted(store_root.glob("journals/*/*/r*/manifest.json"))
    for manifest_path in manifests:
        directory = manifest_path.parent
        manifest, edition, html = _load_store_entry(
            directory, store_root=store_root
        )
        files = manifest.get("files") or {}
        json_name = str((files.get("edition_json") or {}).get("name") or "")
        html_name = str((files.get("report_html") or {}).get("name") or "")
        manifest_name = str(manifest.get("manifest_name") or "")
        for name in (json_name, html_name, manifest_name):
            if not name or Path(name).name != name:
                raise PublicationStoreError(
                    f"stored manifest contains an unsafe artifact name: {name!r}"
                )
        with tempfile.TemporaryDirectory(
            prefix="evidenceradar-edition-", dir=archive_root.parent
        ) as temporary_value:
            temporary = Path(temporary_value)
            (temporary / json_name).write_text(
                json_text(edition), encoding="utf-8"
            )
            (temporary / html_name).write_text(html, encoding="utf-8")
            (temporary / manifest_name).write_text(
                json_text(manifest), encoding="utf-8"
            )
            errors = validate_bundle(
                temporary, require_zh_tw=require_zh_tw
            )
            if errors:
                raise PublicationStoreError(
                    f"stored publication cannot be materialized {directory}:\n"
                    + "\n".join(errors)
                )
            targets.append(
                publish_bundle(
                    temporary,
                    archive_root,
                    require_zh_tw=require_zh_tw,
                )
            )
    return targets
