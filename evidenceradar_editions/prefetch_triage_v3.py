from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from . import prefetch_triage as base
from .prefetch_triage_precision import extract_paths
from .prefetch_triage_v2 import build_prefetch_triage as _build_v2

# Make the precision classifier the canonical extractor before delegating to the
# complete v2 audit/index implementation.
base.extract_paths = extract_paths


def build_prefetch_triage(
    publications: Iterable[Any],
    *,
    catalog_root: Path | str = Path("catalog"),
    generated_at: str | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    return _build_v2(
        publications,
        catalog_root=catalog_root,
        generated_at=generated_at,
    )


__all__ = ["build_prefetch_triage"]
