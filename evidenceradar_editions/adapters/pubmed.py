from __future__ import annotations

from datetime import date
from typing import Any

from defusedxml import ElementTree as ET

from ..http import HttpClient
from ..models import AdapterResult, Article, EditionSpec, SourceCheck, SourceRecord
from ..utils import (
    clean_text,
    normalize_doi,
    normalize_issn,
    parse_loose_date_with_precision,
)

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
        return (
            f"{journal_term} AND "
            f'("{spec.start_date:%Y/%m/%d}"[Date - Publication] : '
            f'"{spec.end_date:%Y/%m/%d}"[Date - Publication])'
        )

    def fetch(self, spec: EditionSpec) -> AdapterResult:
        query = self.query(spec)
        try:
            search = self.client.get_json(
                ESEARCH,
                params={
                    "db": "pubmed",
                    "term": query,
                    "retmode": "json",
                    "retmax": spec.max_records,
                    "sort": "pub date",
                },
            )
            result = search.get("esearchresult") or {}
            ids = list(result.get("idlist") or [])
            try:
                total_available = int(result.get("count"))
            except (TypeError, ValueError):
                total_available = None
            if not ids:
                return AdapterResult(
                    [],
                    SourceCheck(
                        source=self.source,
                        status="NO_RESULTS",
                        query=query,
                        total_available=total_available or 0,
                    ),
                )
            articles: list[Article] = []
            for offset in range(0, len(ids), 200):
                batch = ids[offset : offset + 200]
                xml_bytes = self.client.get_bytes(
                    EFETCH,
                    params={
                        "db": "pubmed",
                        "id": ",".join(batch),
                        "retmode": "xml",
                    },
                )
                articles.extend(self._parse(xml_bytes))
            truncated = bool(
                total_available is not None and total_available > len(ids)
            )
            return AdapterResult(
                articles,
                SourceCheck(
                    source=self.source,
                    status="PARTIAL" if truncated else "SUCCESS",
                    query=query,
                    returned_count=len(ids),
                    total_available=total_available,
                    truncated=truncated,
                    detail=(
                        f"source reported {total_available} records; capped at {len(ids)}"
                        if truncated
                        else None
                    ),
                ),
            )
        except Exception as exc:
            return AdapterResult(
                [],
                SourceCheck(
                    source=self.source,
                    status="FAILED",
                    query=query,
                    detail=f"{type(exc).__name__}: {exc}",
                ),
            )

    @staticmethod
    def _text(node: Any, path: str) -> str | None:
        found = node.find(path)
        if found is None:
            return None
        text = clean_text("".join(found.itertext()))
        return text or None

    @classmethod
    def _publication_date(cls, citation: Any, journal: Any) -> tuple[date, str] | None:
        article_date = citation.find("Article/ArticleDate")
        if article_date is not None:
            value = parse_loose_date_with_precision(
                " ".join(
                    part
                    for part in (
                        cls._text(article_date, "Year"),
                        cls._text(article_date, "Month"),
                        cls._text(article_date, "Day"),
                    )
                    if part
                )
            )
            if value:
                return value
        pub_date_node = journal.find("JournalIssue/PubDate")
        if pub_date_node is None:
            return None
        value = parse_loose_date_with_precision(
            " ".join(
                part
                for part in (
                    cls._text(pub_date_node, "Year"),
                    cls._text(pub_date_node, "Month"),
                    cls._text(pub_date_node, "Day"),
                )
                if part
            )
        )
        return value or parse_loose_date_with_precision(
            cls._text(pub_date_node, "MedlineDate")
        )

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
            published = cls._publication_date(citation, journal)
            if not title or not journal_title or published is None:
                continue
            publication_date, precision = published
            pmid = cls._text(citation, "PMID")
            doi: str | None = None
            pmcid: str | None = None
            for ident in node.findall("PubmedData/ArticleIdList/ArticleId"):
                kind = str(ident.attrib.get("IdType") or "").casefold()
                value = clean_text("".join(ident.itertext()))
                if kind == "doi":
                    doi = normalize_doi(value)
                elif kind == "pmc":
                    pmcid = value.upper()
            if doi is None:
                for ident in article.findall("ELocationID"):
                    if str(ident.attrib.get("EIdType") or "").casefold() == "doi":
                        doi = normalize_doi(clean_text("".join(ident.itertext())))
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
                given = cls._text(author, "ForeName") or cls._text(
                    author, "Initials"
                )
                name = collective or clean_text(
                    " ".join(value for value in (given, family) if value)
                )
                if name:
                    authors.append(name)
            types = [
                clean_text("".join(item.itertext()))
                for item in article.findall("PublicationTypeList/PublicationType")
            ]
            article_type = next((value for value in types if value), None)
            urls: list[str] = []
            if doi:
                urls.append(f"https://doi.org/{doi}")
            pubmed_url = (
                f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None
            )
            if pubmed_url:
                urls.append(pubmed_url)
            if pmcid:
                urls.append(f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/")
            out.append(
                Article(
                    title=title,
                    journal=journal_title,
                    publication_date=publication_date,
                    publication_date_precision=precision,
                    doi=doi,
                    pmid=pmid,
                    pmcid=pmcid,
                    issns=issns,
                    authors=authors,
                    article_type=article_type,
                    urls=urls,
                    source_records=[
                        SourceRecord("pubmed", pmid, pubmed_url)
                    ],
                )
            )
        return out
