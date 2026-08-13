from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .utils import normalize_issn, normalize_name

@dataclass(frozen=True)
class RadarHints:
    matched_source_ids: tuple[str, ...] = ()
    feeds: tuple[str, ...] = ()
    upstream_commit: str | None = None
    config_sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"matched_source_ids": list(self.matched_source_ids), "feeds": list(self.feeds), "upstream_commit": self.upstream_commit, "config_sha256": self.config_sha256}


def load_radar_hints(radar_root: Path | None, *, journal: str, issn: str | None, explicit_commit: str | None = None) -> RadarHints:
    if radar_root is None:
        return RadarHints(upstream_commit=explicit_commit)
    config_path = radar_root / "config" / "radar_master.json"
    if not config_path.is_file():
        raise FileNotFoundError(f"Radar master config not found: {config_path}")
    payload = config_path.read_bytes()
    data = json.loads(payload.decode("utf-8"))
    sources = data.get("sources") or {}
    if not isinstance(sources, dict):
        raise ValueError("Radar master config sources must be an object")

    target_name = normalize_name(journal)
    target_issn = normalize_issn(issn)
    matched: list[str] = []
    feeds: list[str] = []
    for source_id, raw in sources.items():
        if not isinstance(raw, dict):
            continue
        source_name = normalize_name(str(raw.get("journal") or ""))
        source_issn = normalize_issn(str(raw.get("crossref_issn") or ""))
        name_match = bool(source_name and source_name == target_name)
        issn_match = bool(target_issn and source_issn and target_issn == source_issn)
        if not (name_match or issn_match):
            continue
        matched.append(str(source_id))
        raw_feeds = raw.get("feeds") or []
        if isinstance(raw_feeds, list):
            feeds.extend(str(v) for v in raw_feeds if str(v).startswith(("http://", "https://")))
        endpoint = raw.get("endpoint")
        if raw.get("adapter") == "rss_atom" and isinstance(endpoint, str) and endpoint.startswith(("http://", "https://")):
            feeds.append(endpoint)

    return RadarHints(matched_source_ids=tuple(sorted(set(matched))), feeds=tuple(sorted(set(feeds))), upstream_commit=explicit_commit, config_sha256=hashlib.sha256(payload).hexdigest())
