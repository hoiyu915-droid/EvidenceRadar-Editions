from ..models import AdapterResult, SourceCheck

class RadarFeedAdapter:
    source = "radar_rss"
    def __init__(self, client, hints):
        self.hints = hints
    def fetch(self, spec):
        return AdapterResult([], SourceCheck(self.source, "NOT_ATTEMPTED", "Radar source hint only", 0, 0))
