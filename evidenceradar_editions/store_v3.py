from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .bundle import BundlePaths, load_bundle_paths
from .render import render_html
from .serialization import json_text
from .utils import sha256_bytes, sha256_file, utc_now_iso
from .validate import validate_bundle

_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?$")
_PERIOD_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z-]*(?:--[0-9A-Za-z-]+)?$")
_ALLOWED_KINDS = {"day", "week", "month", "range"}


@dataclass(frozen=True)
class StoredPublication:
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
        """Public Pages path; intentionally independent of Git storage layout."""

        return f"journals/{self.journal_slug}/{self.period_key}/r{self.revision:02d}/"


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _identity(manifest: dict[str, Any]) -> tuple[str, str, str, int, date, date]:
    slug = str(manifest.get("journal_slug") or "")
    kind = str(manifest.get("period_kind") or "")
    period = str(manifest.get("period_key") or "")
    revision = int(manifest.get("revision") or 0)
    if not _SLUG_RE.fullmatch(slug):
        raise ValueError(f"unsafe journal slug in manifest: {slug!r}")
    if kind not in _ALLOWED_KINDS:
        raise ValueError(f"unsupported period kind in manifest: {kind!r}")
    if not _PERIOD_RE.fullmatch(period):
        raise ValueError(f"unsafe period key in manifest: {period!r}")
    if not (1 <= revision <= 9999):
        raise ValueError(f"unsafe revision in manifest: {revision}")
    try:
        start = date.fromisoformat(str(manifest.get("period_start") or ""))
        end = date.fromisoformat(str(manifest.get("period_end") or ""))
    except ValueError as exc:
        raise ValueError("manifest period dates are invalid") from exc
    if start > end:
        raise ValueError("manifest period start is after end")
    return slug, kind, period, revision, start, end


def store_destination(manifest: dict[str, Any], editions_root: Path) -> Path:
    """Return the v3 sharded canonical storage path.

    Calendar months use the intentionally short long-term shape:
    editions/<journal>/<YYYY>/<MM>/rXX.
    Other supported period kinds are sharded below the same year/month tree
    without competing with monthly edition directories.
    """

    slug, kind, period, revision, start, _ = _identity(manifest)
    root = Path(editions_root)
    if kind == "month":
        return root / slug / f"{start.year:04d}" / f"{start.month:02d}" / f"r{revision:02d}"
    if kind == "day":
        return (
            root
            / slug
            / f"{start.year:04d}"
            / f"{start.month:02d}"
            / "days"
            / f"{start.day:02d}"
            / f"r{revision:02d}"
        )
    if kind == "week":
        iso_year, iso_week, _ = start.isocalendar()
        return root / slug / f"{iso_year:04d}" / "weeks" / f"W{iso_week:02d}" / f"r{revision:02d}"
    return root / slug / f"{start.year:04d}" / "ranges" / period / f"r{revision:02d}"


def _assert_root(root: Path, *, create: bool) -> Path:
    root = _absolute(root)
    if root.is_symlink():
        raise ValueError("editions root must not be a symlink")
    if root.exists():
        if not root.is_dir():
            raise ValueError(f"editions root is not a directory: {root}")
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
            raise ValueError(f"editions directory is unsafe: {current_path}")
        try:
            current_path.resolve(strict=True).relative_to(root_real)
        except ValueError as exc:
            raise ValueError(f"editions directory escapes root: {current_path}") from exc
        for name in [*dirnames, *filenames]:
            candidate = current_path / name
            if candidate.is_symlink():
                raise ValueError(f"editions symlink is forbidden: {candidate}")


def _ensure_descendant_directory(root: Path, directory: Path) -> Path:
    root = _assert_root(root, create=True)
    _assert_tree_has_no_symlinks(root)
    root_real = root.resolve(strict=True)
    directory = _absolute(directory)
    try:
        relative = directory.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"edition destination escapes root: {directory}") from exc
    current = root
    for part in relative.parts:
        candidate = current / part
        if candidate.is_symlink():
            raise ValueError(f"edition ancestor is a symlink: {candidate}")
        if candidate.exists():
            if not candidate.is_dir():
                raise ValueError(f"edition ancestor is not a directory: {candidate}")
        else:
            candidate.mkdir()
        try:
            candidate.resolve(strict=True).relative_to(root_real)
        except ValueError as exc:
            raise ValueError(f"edition ancestor escapes root: {candidate}") from exc
        current = candidate
    return current


def _copy_regular(source: Path, destination: Path) -> None:
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"publication source is not a regular file: {source}")
    shutil.copyfile(source, destination)


def _store_files(paths: BundlePaths, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=False)
    _copy_regular(paths.json_path, target / "edition.json")
    _copy_regular(paths.manifest_path, target / "manifest.json")
    metadata = {
        "schema_version": "3.0",
        "artifact_type": "EvidenceRadar_Editions_CanonicalStoreEntry",
        "stored_at": utc_now_iso(),
        "publication_id": paths.manifest.get("publication_id"),
        "journal_slug": paths.manifest.get("journal_slug"),
        "period_key": paths.manifest.get("period_key"),
        "revision": paths.manifest.get("revision"),
        "storage_policy": {
            "canonical_json_in_git": True,
            "manifest_in_git": True,
            "html_in_git": False,
            "html_rendered_by_pages": True,
        },
        "source_bundle": {
            "edition_json": paths.json_path.name,
            "report_html": paths.html_path.name,
            "manifest_json": paths.manifest_path.name,
        },
    }
    (target / "storage.json").write_text(json_text(metadata), encoding="utf-8")


def _same_publication(paths: BundlePaths, target: Path) -> bool:
    try:
        archived = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    except Exception:
        return False
    return archived == paths.manifest and sha256_file(target / "edition.json") == sha256_file(paths.json_path)


def store_bundle(bundle_dir: Path, editions_root: Path, *, require_zh_tw: bool = True) -> Path:
    """Store one validated bundle without duplicating presentation HTML in Git."""

    errors = validate_bundle(bundle_dir, require_zh_tw=require_zh_tw)
    if errors:
        raise ValueError("edition bundle is not publishable:\n" + "\n".join(errors))
    paths = load_bundle_paths(bundle_dir)
    root = _assert_root(Path(editions_root), create=True)
    target = _absolute(store_destination(paths.manifest, root))
    safe_parent = _ensure_descendant_directory(root, target.parent)
    target = safe_parent / target.name
    if target.is_symlink():
        raise ValueError(f"edition target is a symlink: {target}")
    if target.exists():
        if not target.is_dir():
            raise ValueError(f"edition target is unsafe: {target}")
        if _same_publication(paths, target):
            return target
        raise FileExistsError(
            f"edition revision already exists with different bytes: {target}; increment revision"
        )
    temporary = safe_parent / f".{target.name}.{uuid.uuid4().hex}.tmp"
    if temporary.exists() or temporary.is_symlink():
        raise ValueError(f"edition temporary target is unsafe: {temporary}")
    try:
        _store_files(paths, temporary)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            if temporary.is_symlink():
                raise ValueError(f"edition temporary target became a symlink: {temporary}")
            shutil.rmtree(temporary)
    _assert_tree_has_no_symlinks(root)
    return target


def validate_stored_publication(directory: Path, *, require_zh_tw: bool = True) -> list[str]:
    errors: list[str] = []
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        return [f"stored publication directory is missing or unsafe: {directory}"]
    edition_path = directory / "edition.json"
    manifest_path = directory / "manifest.json"
    storage_path = directory / "storage.json"
    for path in (edition_path, manifest_path, storage_path):
        if path.is_symlink() or not path.is_file():
            errors.append(f"missing or unsafe canonical store file: {path.name}")
    if errors:
        return errors
    try:
        edition = json.loads(edition_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        storage = json.loads(storage_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"canonical store JSON parse failed: {exc}"]
    if not isinstance(edition, dict) or not isinstance(manifest, dict) or not isinstance(storage, dict):
        return ["canonical store files must contain JSON objects"]

    files = manifest.get("files") or {}
    edition_record = files.get("edition_json") or {}
    report_record = files.get("report_html") or {}
    if edition_record.get("sha256") != sha256_file(edition_path):
        errors.append("stored edition JSON SHA256 differs from manifest")
    if edition_record.get("bytes") != edition_path.stat().st_size:
        errors.append("stored edition JSON byte size differs from manifest")
    rendered = render_html(edition).encode("utf-8")
    if report_record.get("sha256") != sha256_bytes(rendered):
        errors.append("stored edition no longer reproduces manifest HTML SHA256")
    if report_record.get("bytes") != len(rendered):
        errors.append("stored edition no longer reproduces manifest HTML byte size")

    scope = edition.get("scope") or {}
    for key, expected in (
        ("edition_id", edition.get("edition_id")),
        ("publication_id", edition.get("publication_id")),
        ("journal_slug", scope.get("journal_slug") or scope.get("slug")),
        ("period_key", scope.get("period_key")),
        ("revision", scope.get("revision")),
    ):
        if manifest.get(key) != expected:
            errors.append(f"stored manifest identity mismatch: {key}")
    if storage.get("publication_id") != manifest.get("publication_id"):
        errors.append("storage metadata publication identity mismatch")
    if (storage.get("storage_policy") or {}).get("html_in_git") is not False:
        errors.append("canonical storage policy must keep HTML out of Git")

    article_count = int((edition.get("counts") or {}).get("articles") or 0)
    translated_count = int((edition.get("counts") or {}).get("translated_articles") or 0)
    if manifest.get("article_count") != article_count:
        errors.append("stored manifest article count mismatch")
    if manifest.get("translated_article_count", 0) != translated_count:
        errors.append("stored manifest translated article count mismatch")
    if require_zh_tw and article_count:
        if (edition.get("translation") or {}).get("status") != "COMPLETE":
            errors.append("canonical publication requires COMPLETE zh-TW translation")
        if translated_count != article_count:
            errors.append("canonical publication zh-TW coverage is incomplete")
    return errors


def discover_stored_publications(editions_root: Path, *, require_zh_tw: bool = True) -> list[StoredPublication]:
    root = _assert_root(Path(editions_root), create=False)
    if not root.exists():
        return []
    _assert_tree_has_no_symlinks(root)
    root_real = root.resolve(strict=True)
    publications: list[StoredPublication] = []
    for manifest_path in sorted(root.glob("**/r*/manifest.json")):
        directory = manifest_path.parent
        if manifest_path.is_symlink() or directory.is_symlink():
            raise ValueError(f"stored publication path is unsafe: {directory}")
        try:
            directory.resolve(strict=True).relative_to(root_real)
        except ValueError as exc:
            raise ValueError(f"stored publication escapes root: {directory}") from exc
        errors = validate_stored_publication(directory, require_zh_tw=require_zh_tw)
        if errors:
            raise ValueError(f"invalid stored publication {directory}:\n" + "\n".join(errors))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        edition = json.loads((directory / "edition.json").read_text(encoding="utf-8"))
        expected = _absolute(store_destination(manifest, root))
        if _absolute(directory) != expected:
            raise ValueError(f"stored publication path does not match manifest identity: {directory}")
        publications.append(StoredPublication(directory=directory, manifest=manifest, edition=edition))
    publications.sort(
        key=lambda item: (
            str(item.manifest.get("period_end") or ""),
            str(item.manifest.get("journal") or "").casefold(),
            item.revision,
        ),
        reverse=True,
    )
    return publications
