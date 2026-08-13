from __future__ import annotations

import json
from typing import Any
import requests

class HttpClient:
    def __init__(self, timeout: int = 30) -> None:
        self.timeout = timeout

    def get_bytes(self, url: str, *, params: dict[str, Any] | None = None) -> bytes:
        response = requests.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return bytes(response.content)

    def get_json(self, url: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        data = json.loads(self.get_bytes(url, params=params).decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("expected JSON object")
        return data
