from __future__ import annotations

from typing import Any

from ..models import AdapterResult, EditionSpec, SourceCheck


class RadarFeedAdapter:
    """Provenance-only adapter for feed hints selected by the Radar control plane."""

    source = "radar_rss"

    def __init__(self, client: Any, hints: Any) -> None:
        self.hints = hints

    def fetch(self, spec: EditionSpec) -> AdapterResult:
        feed_count = len(getattr(self.hints, "feeds", ()) or ())
        detail = (
            f"{feed_count} matching Radar feed hint(s) recorded; dynamic feed fetch disabled"
            if feed_count
            else "no matching Radar feed hint; dynamic feed fetch disabled"
        )
        return AdapterResult(
            [],
            SourceCheck(
                source=self.source,
                status="NOT_ATTEMPTED",
                query="Radar source hint only",
                total_available=feed_count,
                detail=detail,
            ),
        )
