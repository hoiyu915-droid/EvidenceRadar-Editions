from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .bundle import BundlePaths, load_bundle_paths
from .serialization import json_text
from .utils import sha256_file, utc_now_iso
from .validate import validate_bundle

_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?$")
_PERIOD_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z-]*(?:--[0-9A-Za-z-]+)?$")


@dataclass(frozen=True)
class Publication:
    directory: Path
    manifest: dict[str, Any]
    edition: dict[str, Any]

    @property
    def journal_slug(self) -> str:
        return str(self.manifest["journal_slug"])

    @property
    def period_key(self) -> str:
        return str(self.manifest["period_key"])

    @property
    def revision(self) -> int:
        return int(self.manifest["revision"])

    @property
    def relative_path(self) -> str:
        return f"journals/{self.journal_slug}/{self.period_key}/r{self.revision:02d}/"


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _identity_from_manifest(manifest: dict[str, Any]) -> tuple[str, str, int]:
    slug = str(manifest.get("journal_slug") or "")
    period = str(manifest.get("period_key") or "")
    revision = int(manifest.get("revision") or 0)
    if not _SLUG_RE.fullmatch(slug):
        raise ValueError(f"unsafe journal slug in manifest: {slug!r}")
    if not _PERIOD_RE.fullmatch(period):
        raise ValueError(f"unsafe period key in manifest: {period!r}")
    if not (1 <= revision <= 9999):
        raise ValueError(f"unsafe revision in manifest: {revision}")
    return slug, period, revision


def archive_destination(manifest: dict[str, Any], archive_root: Path) -> Path:
    slug, period, revision = _identity_from_manifest(manifest)
    return Path(archive_root) / "journals" / slug / period / f"r{revision:02d}"


def _assert_root(root: Path, *, create: bool) -> Path:
    root = _absolute(root)
    if root.is_symlink():
        raise ValueError("archive root must not be a symlink")
    if root.exists():
        if not root.is_dir():
            raise ValueError(f"archive root is not a directory: {root}")
    elif create:
        root.mkdir(parents=True, exist_ok=False)
    return root


def _assert_tree_has_no_symlinks(root: Path) -> None:
    if not root.exists():
        return
    root_real = root.resolve(strict=True)
    for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        if current_path.is_symlink() or not current_path.is_dir():
            raise ValueError(f"archive directory is unsafe: {current_path}")
        try:
            current_path.resolve(strict=True).relative_to(root_real)
        except ValueError as exc:
            raise ValueError(f"archive directory escapes root: {current_path}") from exc
        for name in [*dirnames, *filenames]:
            candidate = current_path / name
            if candidate.is_symlink():
                raise ValueError(f"archive symlink is forbidden: {candidate}")


def _ensure_descendant_directory(root: Path, directory: Path) -> Path:
    root = _assert_root(root, create=True)
    _assert_tree_has_no_symlinks(root)
    root_real = root.resolve(strict=True)
    directory = _absolute(directory)
    try:
        relative = directory.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"archive destination escapes root: {directory}") from exc
    current = root
    for part in relative.parts:
        candidate = current / part
        if candidate.is_symlink():
            raise ValueError(f"archive ancestor is a symlink: {candidate}")
        if candidate.exists():
            if not candidate.is_dir():
                raise ValueError(f"archive ancestor is not a directory: {candidate}")
        else:
            candidate.mkdir()
        try:
            candidate.resolve(strict=True).relative_to(root_real)
        except ValueError as exc:
            raise ValueError(f"archive ancestor escapes root: {candidate}") from exc
        current = candidate
    return current


def _copy_regular(source: Path, destination: Path) -> None:
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"publication source is not a regular file: {source}")
    shutil.copyfile(source, destination)


def _copy_publication_files(paths: BundlePaths, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=False)
    _copy_regular(paths.html_path, target / paths.html_path.name)
    _copy_regular(paths.json_path, target / paths.json_path.name)
    _copy_regular(paths.manifest_path, target / paths.manifest_path.name)
    _copy_regular(paths.html_path, target / "index.html")
    _copy_regular(paths.json_path, target / "edition.json")
    _copy_regular(paths.manifest_path, target / "manifest.json")
    publication = {
        "schema_version": "1.1",
        "artifact_type": "EvidenceRadar_Editions_ArchiveEntry",
        "published_at": utc_now_iso(),
        "edition_id": paths.manifest.get("edition_id"),
        "publication_id": paths.manifest.get("publication_id"),
        "journal_slug": paths.manifest.get("journal_slug"),
        "period_key": paths.manifest.get("period_key"),
        "revision": paths.manifest.get("revision"),
        "files": {
            "index_html": "index.html",
            "edition_json": "edition.json",
            "manifest_json": "manifest.json",
            "download_html": paths.html_path.name,
            "download_json": paths.json_path.name,
            "download_manifest": paths.manifest_path.name,
        },
    }
    (target / "publication.json").write_text(json_text(publication), encoding="utf-8")


def _same_publication(paths: BundlePaths, target: Path) -> bool:
    try:
        archived = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    except Exception:
        return False
    if archived != paths.manifest:
        return False
    return (
        sha256_file(target / "edition.json") == sha256_file(paths.json_path)
        and sha256_file(target / "index.html") == sha256_file(paths.html_path)
    )


def publish_bundle(bundle_dir: Path, archive_root: Path, *, require_zh_tw: bool = True) -> Path:
    errors = validate_bundle(bundle_dir, require_zh_tw=require_zh_tw)
    if errors:
        raise ValueError("edition bundle is not publishable:\n" + "\n".join(errors))
    paths = load_bundle_paths(bundle_dir)
    root = _assert_root(Path(archive_root), create=True)
    target = _absolute(archive_destination(paths.manifest, root))
    safe_parent = _ensure_descendant_directory(root, target.parent)
    target = safe_parent / target.name
    if target.is_symlink():
        raise ValueError(f"archive target is a symlink: {target}")
    if target.exists():
        if not target.is_dir():
            raise ValueError(f"archive target is unsafe: {target}")
        if _same_publication(paths, target):
            return target
        raise FileExistsError(
            f"archive revision already exists with different bytes: {target}; increment revision"
        )
    temporary = safe_parent / f".{target.name}.{uuid.uuid4().hex}.tmp"
    if temporary.exists() or temporary.is_symlink():
        raise ValueError(f"archive temporary target is unsafe: {temporary}")
    try:
        _copy_publication_files(paths, temporary)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            if temporary.is_symlink():
                raise ValueError(f"archive temporary target became a symlink: {temporary}")
            shutil.rmtree(temporary)
    _assert_tree_has_no_symlinks(root)
    return target


def _validate_aliases(directory: Path, paths: BundlePaths) -> list[str]:
    errors: list[str] = []
    aliases = {"index.html": paths.html_path, "edition.json": paths.json_path, "manifest.json": paths.manifest_path}
    for name, canonical in aliases.items():
        alias = directory / name
        if alias.is_symlink() or not alias.is_file():
            errors.append(f"missing or unsafe archive alias: {name}")
            continue
        if sha256_file(alias) != sha256_file(canonical):
            errors.append(f"archive alias bytes differ from canonical file: {name}")
    publication_path = directory / "publication.json"
    if publication_path.is_symlink() or not publication_path.is_file():
        errors.append("missing or unsafe publication.json")
    else:
        try:
            publication = json.loads(publication_path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"publication.json parse failed: {exc}")
        else:
            if publication.get("publication_id") != paths.manifest.get("publication_id"):
                errors.append("publication.json identity mismatch")
    return errors


def discover_publications(archive_root: Path, *, require_zh_tw: bool = True) -> list[Publication]:
    root = _assert_root(Path(archive_root), create=False)
    if not root.exists():
        return []
    _assert_tree_has_no_symlinks(root)
    root_real = root.resolve(strict=True)
    publications: list[Publication] = []
    for manifest_path in sorted(root.glob("journals/*/*/r*/manifest.json")):
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise ValueError(f"archive manifest is unsafe: {manifest_path}")
        directory = manifest_path.parent
        try:
            directory.resolve(strict=True).relative_to(root_real)
        except ValueError as exc:
            raise ValueError(f"archived edition escapes root: {directory}") from exc
        errors = validate_bundle(directory, require_zh_tw=require_zh_tw)
        try:
            paths = load_bundle_paths(directory)
        except Exception as exc:
            errors.append(f"archive bundle discovery failed: {exc}")
            paths = None
        if paths is not None:
            errors.extend(_validate_aliases(directory, paths))
        if errors:
            raise ValueError(f"invalid archived edition {directory}:\n" + "\n".join(errors))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        edition = json.loads((directory / "edition.json").read_text(encoding="utf-8"))
        publication = Publication(directory=directory, manifest=manifest, edition=edition)
        expected = _absolute(archive_destination(manifest, root))
        if _absolute(directory) != expected:
            raise ValueError(f"archive path does not match manifest identity: {directory}")
        publications.append(publication)
    publications.sort(
        key=lambda item: (
            str(item.manifest.get("period_end") or ""),
            str(item.manifest.get("journal") or "").casefold(),
            item.revision,
        ),
        reverse=True,
    )
    return publications
