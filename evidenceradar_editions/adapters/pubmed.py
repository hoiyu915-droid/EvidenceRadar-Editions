from __future__ import annotations

from datetime import date
from typing import Any

from defusedxml import ElementTree as ET

from ..http import HttpClient
from ..models import AdapterResult, Article, EditionSpec, SourceCheck, SourceRecord
from ..utils import normalize_doi, normalize_issn, parse_loose_date

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

class PubMedAdapter:
    source = "pubmed"

    def __init__(self, client: HttpClient) -> None:
        self.client = client

    @staticmethod
    def query(spec: EditionSpec) -> str:
        journal_name = spec.journal.replace('"', r'\"')
        if spec.issn:
            journal_term = f'("{journal_name}"[Journal] OR "{spec.issn}"[ISSN])'
        else:
            journal_term = f'"{journal_name}"[Journal]'
        return f"{journal_term} AND " f'("{spec.start_date:%Y/%m/%d}"[Date - Publication] : "{spec.end_date:%Y/%m/%d}"[Date - Publication])'

    def fetch(self, spec: EditionSpec) -> AdapterResult:
        query = self.query(spec)
        try:
            search = self.client.get_json(ESEARCH, params={"db": "pubmed", "term": query, "retmode": "json", "retmax": spec.max_records, "sort": "pub date"})
            ids = list((search.get("esearchresult") or {}).get("idlist") or [])
            if not ids:
                return AdapterResult([], SourceCheck(self.source, "NO_RESULTS", query, 0, 0))
            articles: list[Article] = []
            for offset in range(0, len(ids), 200):
                batch = ids[offset: offset + 200]
                xml_bytes = self.client.get_bytes(EFETCH, params={"db": "pubmed", "id": ",".join(batch), "retmode": "xml"})
                articles.extend(self._parse(xml_bytes))
            return AdapterResult(articles, SourceCheck(self.source, "SUCCESS", query, len(ids), 0))
        except Exception as exc:
            return AdapterResult([], SourceCheck(self.source, "FAILED", query, 0, 0, f"{type(exc).__name__}: {exc}"))

    @staticmethod
    def _text(node: Any, path: str) -> str | None:
        found = node.find(path)
        if found is None:
            return None
        text = "".join(found.itertext()).strip()
        return text or None

    @classmethod
    def _parse(cls, payload: bytes) -> list[Article]:
        root = ET.fromstring(payload)
        out: list[Article] = []
        for node in root.findall(".//PubmedArticle"):
            citation = node.find("MedlineCitation")
            article = node.find("MedlineCitation/Article")
            journal = node.find("MedlineCitation/Article/Journal")
            if citation is None or article is None or journal is None:
                continue
            title = cls._text(article, "ArticleTitle")
            journal_title = cls._text(journal, "Title")
            if not title or not journal_title:
                continue
            pub_date_node = journal.find("JournalIssue/PubDate")
            published: date | None = None
            if pub_date_node is not None:
                year = cls._text(pub_date_node, "Year")
                month = cls._text(pub_date_node, "Month")
                day = cls._text(pub_date_node, "Day")
                medline = cls._text(pub_date_node, "MedlineDate")
                published = parse_loose_date(" ".join(v for v in (year, month, day) if v)) or parse_loose_date(medline)
            if published is None:
                continue
            pmid = cls._text(citation, "PMID")
            doi: str | None = None
            pmcid: str | None = None
            for ident in node.findall("PubmedData/ArticleIdList/ArticleId"):
                kind = str(ident.attrib.get("IdType") or "").casefold()
                value = "".join(ident.itertext()).strip()
                if kind == "doi":
                    doi = normalize_doi(value)
                elif kind == "pmc":
                    pmcid = value.upper()
            if doi is None:
                for ident in article.findall("ELocationID"):
                    if str(ident.attrib.get("EIdType") or "").casefold() == "doi":
                        doi = normalize_doi("".join(ident.itertext()).strip())
                        break
            issns: list[str] = []
            issn_node = journal.find("ISSN")
            if issn_node is not None and issn_node.text:
                value = normalize_issn(issn_node.text)
                if value:
                    issns.append(value)
            for item in citation.findall("MedlineJournalInfo/ISSNLinking"):
                value = normalize_issn(item.text)
                if value:
                    issns.append(value)
            authors: list[str] = []
            for author in article.findall("AuthorList/Author"):
                collective = cls._text(author, "CollectiveName")
                family = cls._text(author, "LastName")
                given = cls._text(author, "ForeName") or cls._text(author, "Initials")
                name = collective or " ".join(v for v in (given, family) if v)
                if name:
                    authors.append(name)
            types = ["".join(x.itertext()).strip() for x in article.findall("PublicationTypeList/PublicationType")]
            article_type = types[0] if types else None
            urls = []
            if doi:
                urls.append(f"https://doi.org/{doi}")
            pubmed_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None
            if pubmed_url:
                urls.append(pubmed_url)
            if pmcid:
                urls.append(f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/")
            out.append(Article(title=title, journal=journal_title, publication_date=published, doi=doi, pmid=pmid, pmcid=pmcid, issns=issns, authors=authors, article_type=article_type, urls=urls, source_records=[SourceRecord("pubmed", pmid, pubmed_url)]))
        return out
