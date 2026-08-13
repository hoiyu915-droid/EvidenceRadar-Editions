from __future__ import annotations

import importlib.util
import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

DEFAULT_RADAR_CONFIG = Path(__file__).resolve().parent / "data" / "upstream-radar.json"


class UpstreamError(RuntimeError):
    """Raised when a pinned EvidenceRadar source checkout is incompatible."""


@dataclass(frozen=True)
class RadarReference:
    repository: str
    expected_commit: str
    observed_commit: str = ""
    verified: bool = False
    mode: str = "declared-only"
    artifacts_consumed: bool = False
    files_used: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "repository": self.repository,
            "expected_commit": self.expected_commit,
            "observed_commit": self.observed_commit or None,
            "verified": self.verified,
            "mode": self.mode,
            "artifacts_consumed": self.artifacts_consumed,
            "files_used": list(self.files_used),
        }


@dataclass(frozen=True)
class RadarNetworkBridge:
    reference: RadarReference
    validate_public_http_url: Callable[..., str] | None = None
    bounded_response_text: Callable[..., str] | None = None
    bounded_response_bytes: Callable[..., bytes | None] | None = None


def load_upstream_config(path: Path = DEFAULT_RADAR_CONFIG) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UpstreamError(f"cannot read upstream Radar config: {path}") from exc
    if not isinstance(payload, dict):
        raise UpstreamError("upstream Radar config must be a JSON object")
    if str(payload.get("schema_version")) != "1":
        raise UpstreamError("unsupported upstream Radar config schema")
    repository = str(payload.get("repository") or "").strip()
    commit = str(payload.get("commit") or "").strip()
    if not repository or len(commit) != 40:
        raise UpstreamError("upstream Radar repository and 40-character commit are required")
    if payload.get("artifacts_consumed") is not False:
        raise UpstreamError("artifacts_consumed must remain false")
    return payload


def declared_reference(config_path: Path = DEFAULT_RADAR_CONFIG) -> RadarReference:
    config = load_upstream_config(config_path)
    return RadarReference(
        repository=str(config["repository"]),
        expected_commit=str(config["commit"]),
        artifacts_consumed=False,
        files_used=(),
    )


def _git_head(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise UpstreamError(f"cannot resolve EvidenceRadar checkout commit: {root}") from exc
    return result.stdout.strip()


def _load_module(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("evidenceradar_editions._radar_network_safety", path)
    if spec is None or spec.loader is None:
        raise UpstreamError(f"cannot load upstream module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inspect_radar_checkout(
    root: Path,
    *,
    config_path: Path = DEFAULT_RADAR_CONFIG,
    allow_drift: bool = False,
) -> RadarNetworkBridge:
    root = root.resolve()
    config = load_upstream_config(config_path)
    expected = str(config["commit"])
    observed = _git_head(root)
    if observed != expected and not allow_drift:
        raise UpstreamError(
            f"EvidenceRadar checkout drift: expected {expected}, observed {observed}; "
            "use --allow-radar-drift only for an intentional compatibility test"
        )

    allowed_paths = tuple(str(value) for value in config.get("allowed_paths", []))
    prohibited_roots = {"artifacts", "runs", "state", "public"}
    for relative in allowed_paths:
        if Path(relative).parts and Path(relative).parts[0] in prohibited_roots:
            raise UpstreamError(f"upstream allowlist illegally references Radar output: {relative}")
        if not (root / relative).exists():
            raise UpstreamError(f"required upstream source path is missing: {relative}")

    license_text = (root / "LICENSE").read_text(encoding="utf-8", errors="replace")
    if "Apache License" not in license_text or "Version 2.0" not in license_text:
        raise UpstreamError("upstream EvidenceRadar license is not recognized as Apache-2.0")

    network_path = root / "tools" / "network_safety.py"
    module = _load_module(network_path)
    required = (
        "validate_public_http_url",
        "bounded_response_text",
        "bounded_response_bytes",
    )
    missing = [name for name in required if not callable(getattr(module, name, None))]
    if missing:
        raise UpstreamError(f"upstream network safety API is missing: {', '.join(missing)}")

    reference = RadarReference(
        repository=str(config["repository"]),
        expected_commit=expected,
        observed_commit=observed,
        verified=observed == expected,
        mode="pinned-source-bridge" if observed == expected else "drift-allowed-source-bridge",
        artifacts_consumed=False,
        files_used=("LICENSE", "tools/network_safety.py"),
    )
    return RadarNetworkBridge(
        reference=reference,
        validate_public_http_url=getattr(module, "validate_public_http_url"),
        bounded_response_text=getattr(module, "bounded_response_text"),
        bounded_response_bytes=getattr(module, "bounded_response_bytes"),
    )
