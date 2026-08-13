from __future__ import annotations

from ..http import HttpClient
from ..models import AdapterResult, Article, EditionSpec, SourceCheck, SourceRecord
from ..utils import date_from_parts, normalize_doi, normalize_issn

ENDPOINT = "https://api.crossref.org/works"

class CrossrefAdapter:
    source = "crossref"

    def __init__(self, client: HttpClient) -> None:
        self.client = client

    @staticmethod
    def query(spec: EditionSpec) -> str:
        return f"{spec.journal}; {spec.start_date.isoformat()}..{spec.end_date.isoformat()}"

    def fetch(self, spec: EditionSpec) -> AdapterResult:
        query = self.query(spec)
        filters = [f"from-pub-date:{spec.start_date.isoformat()}", f"until-pub-date:{spec.end_date.isoformat()}", "type:journal-article"]
        if spec.issn:
            filters.append(f"issn:{spec.issn}")
        base_params = {"filter": ",".join(filters), "query.container-title": spec.journal}
        try:
            articles: list[Article] = []
            returned_count = 0
            remaining = spec.max_records
            cursor: str | None = "*"
            while remaining > 0 and cursor:
                params = dict(base_params)
                params["rows"] = min(remaining, 1000)
                params["cursor"] = cursor
                data = self.client.get_json(ENDPOINT, params=params)
                message = data.get("message") or {}
                items = message.get("items") or []
                if not items:
                    break
                for raw in items:
                    if not isinstance(raw, dict):
                        continue
                    titles = raw.get("title") or []
                    journals = raw.get("container-title") or []
                    title = str(titles[0]).strip() if isinstance(titles, list) and titles else ""
                    journal = str(journals[0]).strip() if isinstance(journals, list) and journals else ""
                    published = None
                    for key in ("published-online", "published-print", "published"):
                        block = raw.get(key) or {}
                        parts = block.get("date-parts") if isinstance(block, dict) else None
                        if isinstance(parts, list) and parts:
                            published = date_from_parts(parts[0])
                        if published:
                            break
                    if not title or not journal or published is None:
                        continue
                    doi = normalize_doi(str(raw.get("DOI") or ""))
                    issns = [v for v in (normalize_issn(str(x)) for x in (raw.get("ISSN") or [])) if v]
                    authors = []
                    for person in raw.get("author") or []:
                        if isinstance(person, dict):
                            name = " ".join(str(person.get(k) or "").strip() for k in ("given", "family")).strip()
                            if name:
                                authors.append(name)
                    url_value = str(raw.get("URL") or "").strip() or (f"https://doi.org/{doi}" if doi else None)
                    articles.append(Article(title=title, journal=journal, publication_date=published, doi=doi, issns=issns, authors=authors, article_type=str(raw.get("type") or "") or None, urls=[url_value] if url_value else [], source_records=[SourceRecord("crossref", doi, url_value)]))
                consumed = len(items)
                returned_count += consumed
                remaining -= consumed
                next_cursor = str(message.get("next-cursor") or "")
                if consumed == 0 or not next_cursor or next_cursor == cursor:
                    break
                cursor = next_cursor
            status = "SUCCESS" if articles else "NO_RESULTS"
            return AdapterResult(articles, SourceCheck(self.source, status, query, returned_count, 0))
        except Exception as exc:
            return AdapterResult([], SourceCheck(self.source, "FAILED", query, 0, 0, f"{type(exc).__name__}: {exc}"))
