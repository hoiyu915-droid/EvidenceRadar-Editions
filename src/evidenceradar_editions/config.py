from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from .models import Collection


def load_collection(path: Path) -> tuple[Collection, str]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read collection config: {path}") from exc
    if not isinstance(raw, dict):
        raise ValueError("collection config must be a YAML object")
    if str(raw.get("schema_version", "1")) != "1":
        raise ValueError("unsupported collection schema_version")
    collection = Collection.from_mapping(raw)
    canonical = json.dumps(collection.as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return collection, hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON document must be an object: {path}")
    return value
