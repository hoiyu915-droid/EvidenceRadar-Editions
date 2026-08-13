from __future__ import annotations

import json
from typing import Any

from .utils import sha256_bytes


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def json_bytes(value: Any) -> bytes:
    return json_text(value).encode("utf-8")


def json_sha256(value: Any) -> str:
    return sha256_bytes(json_bytes(value))
