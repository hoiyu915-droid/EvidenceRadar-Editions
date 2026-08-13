from __future__ import annotations

from ..http import HttpClient
from ..models import AdapterResult, Article, EditionSpec, SourceCheck, SourceRecord
from ..utils import normalize_doi, normalize_issn, parse_loose_date

ENDPOINT = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

class EuropePmcAdapter:
    source = "europe_pmc"

    def __init__(self, client: HttpClient) -> None:
        self.client = client

    @staticmethod
    def query(spec: EditionSpec) -> str:
        journal_name = spec.journal.replace('"', r'\"')
        return f'JOURNAL:"{journal_name}" AND FIRST_PDATE:[{spec.start_date.isoformat()} TO {spec.end_date.isoformat()}]'

    def fetch(self, spec: EditionSpec) -> AdapterResult:
        query = self.query(spec)
        try:
            articles: list[Article] = []
            returned_count = 0
            cursor: str | None = "*"
            remaining = spec.max_records
            while remaining > 0 and cursor:
                data = self.client.get_json(ENDPOINT, params={"query": query, "format": "json", "resultType": "lite", "pageSize": min(remaining, 1000), "cursorMark": cursor})
                raw_results = ((data.get("resultList") or {}).get("result") or [])
                if not raw_results:
                    break
                for raw in raw_results:
                    if not isinstance(raw, dict):
                        continue
                    title = str(raw.get("title") or "").strip()
                    journal = str(raw.get("journalTitle") or "").strip()
                    published = parse_loose_date(str(raw.get("firstPublicationDate") or raw.get("electronicPublicationDate") or raw.get("dateOfPublication") or ""))
                    if not title or not journal or published is None:
                        continue
                    pmid = str(raw.get("pmid") or raw.get("id") or "").strip() or None
                    pmcid = str(raw.get("pmcid") or "").strip().upper() or None
                    doi = normalize_doi(str(raw.get("doi") or ""))
                    issns = []
                    normalized_issn = normalize_issn(str(raw.get("journalIssn") or ""))
                    if normalized_issn:
                        issns.append(normalized_issn)
                    author_string = str(raw.get("authorString") or "").strip()
                    authors = [p.strip() for p in author_string.split(",") if p.strip()] if author_string else []
                    urls = []
                    if doi:
                        urls.append(f"https://doi.org/{doi}")
                    if pmcid:
                        urls.append(f"https://europepmc.org/article/PMC/{pmcid}")
                    elif pmid:
                        urls.append(f"https://europepmc.org/article/MED/{pmid}")
                    articles.append(Article(title=title, journal=journal, publication_date=published, doi=doi, pmid=pmid, pmcid=pmcid, issns=issns, authors=authors, urls=urls, source_records=[SourceRecord("europe_pmc", pmcid or pmid, urls[-1] if urls else None)]))
                consumed = len(raw_results)
                returned_count += consumed
                remaining -= consumed
                next_cursor = str(data.get("nextCursorMark") or "")
                if consumed == 0 or not next_cursor or next_cursor == cursor:
                    break
                cursor = next_cursor
            status = "SUCCESS" if articles else "NO_RESULTS"
            return AdapterResult(articles, SourceCheck(self.source, status, query, returned_count, 0))
        except Exception as exc:
            return AdapterResult([], SourceCheck(self.source, "FAILED", query, 0, 0, f"{type(exc).__name__}: {exc}"))
