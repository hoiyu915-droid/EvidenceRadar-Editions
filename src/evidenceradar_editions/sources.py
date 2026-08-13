from __future__ import annotations

import calendar
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException

from .http_client import SafeHttpClient
from .models import (
    Article,
    Collection,
    SourceReceipt,
    classify_study_designs,
    clean_text,
    normalize_doi,
    normalize_issn,
    stable_unique,
    utc_now_iso,
)

PUBMED_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
EUROPE_PMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
CROSSREF_WORKS = "https://api.crossref.org/works"
SUPPORTED_SOURCES = ("pubmed", "europe_pmc", "crossref")


class SourceError(RuntimeError):
    """Raised when a source adapter cannot complete its operation."""


@dataclass
class SourceResult:
    articles: list[Article]
    receipt: SourceReceipt


_MONTHS = {
    name.casefold(): index
    for index, name in enumerate(calendar.month_abbr)
    if name
}
_MONTHS.update(
    {
        name.casefold(): index
        for index, name in enumerate(calendar.month_name)
        if name
    }
)


def _node_text(node: Any) -> str:
    if node is None:
        return ""
    return clean_text("".join(node.itertext()))


def _date_value(year: object, month: object = "", day: object = "") -> tuple[str, str]:
    year_text = clean_text(year)
    if not year_text or not year_text[:4].isdigit():
        return "", "UNKNOWN"
    try:
        year_value = int(year_text[:4])
    except ValueError:
        return "", "UNKNOWN"
    month_text = clean_text(month)
    day_text = clean_text(day)
    if month_text:
        if month_text.isdigit():
            month_value = int(month_text)
        else:
            month_value = _MONTHS.get(month_text.casefold(), 0)
        if not month_value:
            return "", "UNKNOWN"
    else:
        month_value = 1
    has_day = day_text.isdigit()
    day_value = int(day_text) if has_day else 1
    precision = "DAY" if month_text and has_day else "MONTH" if month_text else "YEAR"
    try:
        return date(year_value, month_value, day_value).isoformat(), precision
    except ValueError:
        return "", "UNKNOWN"


def _date_from_text(value: object) -> tuple[str, str]:
    text = clean_text(value)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        parsed, precision = _date_value(text[:4], text[5:7], text[8:10])
        return parsed, precision
    if re.fullmatch(r"\d{4}-\d{2}", text):
        return _date_value(text[:4], text[5:7])
    if re.fullmatch(r"\d{4}", text):
        return _date_value(text)
    return "", "UNKNOWN"


def _date_from_parts(parts: object) -> tuple[str, str]:
    if not isinstance(parts, list) or not parts or not isinstance(parts[0], list):
        return "", "UNKNOWN"
    values = parts[0]
    if not values:
        return "", "UNKNOWN"
    return _date_value(
        values[0],
        values[1] if len(values) > 1 else "",
        values[2] if len(values) > 2 else "",
    )


def _article_urls(*, doi: str = "", pmid: str = "", pmcid: str = "", extra: Iterable[str] = ()) -> list[str]:
    values: list[str] = []
    if normalize_doi(doi):
        values.append(f"https://doi.org/{normalize_doi(doi)}")
    if clean_text(pmid):
        values.append(f"https://pubmed.ncbi.nlm.nih.gov/{clean_text(pmid)}/")
    if clean_text(pmcid):
        values.append(f"https://pmc.ncbi.nlm.nih.gov/articles/{clean_text(pmcid).upper()}/")
    values.extend(str(value) for value in extra if str(value).startswith(("http://", "https://")))
    return stable_unique(values)


def _pubmed_date(medline_node: Any) -> tuple[str, str]:
    article_date = medline_node.find("./Article/ArticleDate")
    if article_date is not None:
        value = _date_value(
            article_date.findtext("Year"),
            article_date.findtext("Month"),
            article_date.findtext("Day"),
        )
        if value[0]:
            return value
    pub_date = medline_node.find("./Article/Journal/JournalIssue/PubDate")
    if pub_date is not None:
        value = _date_value(
            pub_date.findtext("Year"),
            pub_date.findtext("Month"),
            pub_date.findtext("Day"),
        )
        if value[0]:
            return value
        medline = clean_text(pub_date.findtext("MedlineDate"))
        match = re.search(r"(?P<year>\d{4})(?:\s+(?P<month>[A-Za-z]{3,9}))?", medline)
        if match:
            return _date_value(match.group("year"), match.group("month") or "")
    return "", "UNKNOWN"


def parse_pubmed_xml(payload: str, *, source: str = "pubmed") -> list[Article]:
    try:
        root = ET.fromstring(payload)
    except (ET.ParseError, DefusedXmlException) as exc:
        raise SourceError("PubMed returned invalid XML") from exc
    articles: list[Article] = []
    for citation in root.findall(".//PubmedArticle"):
        medline = citation.find("./MedlineCitation")
        article_node = medline.find("./Article") if medline is not None else None
        if medline is None or article_node is None:
            continue
        title = _node_text(article_node.find("./ArticleTitle"))
        journal = _node_text(article_node.find("./Journal/Title"))
        if not journal:
            journal = clean_text(medline.findtext("./MedlineJournalInfo/MedlineTA"))
        issns = [
            clean_text(article_node.findtext("./Journal/ISSN")),
            clean_text(medline.findtext("./MedlineJournalInfo/ISSNLinking")),
        ]
        issns = stable_unique(normalize_issn(value) for value in issns if normalize_issn(value))
        identifiers: dict[str, str] = {}
        for node in citation.findall("./PubmedData/ArticleIdList/ArticleId"):
            key = str(node.attrib.get("IdType") or "").casefold()
            value = clean_text(node.text)
            if key and value:
                identifiers[key] = value
        for node in article_node.findall("./ELocationID"):
            if str(node.attrib.get("EIdType") or "").casefold() == "doi":
                identifiers.setdefault("doi", clean_text(node.text))
        authors: list[str] = []
        for author in article_node.findall("./AuthorList/Author"):
            collective = clean_text(author.findtext("CollectiveName"))
            if collective:
                authors.append(collective)
                continue
            family = clean_text(author.findtext("LastName"))
            given = clean_text(author.findtext("ForeName") or author.findtext("Initials"))
            name = clean_text(f"{family}, {given}" if family and given else family or given)
            if name:
                authors.append(name)
        abstract_parts: list[str] = []
        for node in article_node.findall("./Abstract/AbstractText"):
            text = _node_text(node)
            label = clean_text(node.attrib.get("Label"))
            if text:
                abstract_parts.append(f"{label}: {text}" if label else text)
        article_types = stable_unique(
            _node_text(node) for node in article_node.findall("./PublicationTypeList/PublicationType")
        )
        pmcid = identifiers.get("pmc", "")
        doi = normalize_doi(identifiers.get("doi", ""))
        pmid = clean_text(medline.findtext("PMID")) or identifiers.get("pubmed", "")
        publication_date, publication_date_precision = _pubmed_date(medline)
        articles.append(
            Article(
                title=title,
                journal=journal,
                publication_date=publication_date,
                publication_date_precision=publication_date_precision,
                authors=stable_unique(authors),
                issns=issns,
                doi=doi,
                pmid=pmid,
                pmcid=pmcid.upper(),
                abstract="\n\n".join(abstract_parts),
                article_types=article_types,
                study_designs=classify_study_designs(title, article_types),
                urls=_article_urls(doi=doi, pmid=pmid, pmcid=pmcid),
                oa_status="YES" if pmcid else "UNKNOWN",
                sources=[source],
                source_records=[
                    {
                        "source": source,
                        "record_id": pmid or doi or pmcid,
                        "retrieval_depth": "ABSTRACT_OR_METADATA",
                    }
                ],
            )
        )
    return articles


def parse_europe_pmc_json(payload: Mapping[str, Any], *, source: str = "europe_pmc") -> list[Article]:
    result_list = payload.get("resultList", {})
    records = result_list.get("result", []) if isinstance(result_list, Mapping) else []
    if not isinstance(records, list):
        raise SourceError("Europe PMC resultList.result is not an array")
    articles: list[Article] = []
    for record in records:
        if not isinstance(record, Mapping):
            continue
        title = clean_text(record.get("title"))
        journal = clean_text(record.get("journalTitle"))
        journal_info = record.get("journalInfo")
        if isinstance(journal_info, Mapping):
            journal_obj = journal_info.get("journal")
            if not journal and isinstance(journal_obj, Mapping):
                journal = clean_text(journal_obj.get("title"))
        issn_values: list[object] = [record.get("journalIssn"), record.get("issn")]
        if isinstance(journal_info, Mapping):
            journal_obj = journal_info.get("journal")
            if isinstance(journal_obj, Mapping):
                issn_values.extend(
                    [journal_obj.get("issn"), journal_obj.get("essn"), journal_obj.get("pissn")]
                )
        issns = stable_unique(
            normalize_issn(value) for value in issn_values if normalize_issn(value)
        )
        doi = normalize_doi(record.get("doi"))
        pmid = clean_text(record.get("pmid"))
        pmcid = clean_text(record.get("pmcid")).upper()
        print_publication_date = (
            journal_info.get("printPublicationDate")
            if isinstance(journal_info, Mapping)
            else ""
        )
        publication_date, publication_date_precision = _date_from_text(
            record.get("firstPublicationDate")
            or record.get("electronicPublicationDate")
            or print_publication_date
        )
        authors: list[str] = []
        author_list = record.get("authorList")
        if isinstance(author_list, Mapping) and isinstance(author_list.get("author"), list):
            authors = [
                clean_text(item.get("fullName") or item.get("lastName"))
                for item in author_list["author"]
                if isinstance(item, Mapping)
            ]
        if not authors:
            authors = [part.strip() for part in clean_text(record.get("authorString")).split(",")]
        pub_types: list[str] = []
        pub_type_list = record.get("pubTypeList")
        if isinstance(pub_type_list, Mapping) and isinstance(pub_type_list.get("pubType"), list):
            pub_types = [clean_text(value) for value in pub_type_list["pubType"]]
        is_oa = str(record.get("isOpenAccess") or "").upper() in {"Y", "YES", "TRUE"}
        extra_urls: list[str] = []
        if pmid:
            extra_urls.append(f"https://europepmc.org/article/MED/{pmid}")
        elif pmcid:
            extra_urls.append(f"https://europepmc.org/article/PMC/{pmcid}")
        articles.append(
            Article(
                title=title,
                journal=journal,
                publication_date=publication_date,
                publication_date_precision=publication_date_precision,
                authors=stable_unique(authors),
                issns=issns,
                doi=doi,
                pmid=pmid,
                pmcid=pmcid,
                abstract=clean_text(record.get("abstractText")),
                article_types=stable_unique(pub_types),
                study_designs=classify_study_designs(title, pub_types),
                urls=_article_urls(doi=doi, pmid=pmid, pmcid=pmcid, extra=extra_urls),
                oa_status="YES" if is_oa or pmcid else "UNKNOWN",
                sources=[source],
                source_records=[
                    {
                        "source": source,
                        "record_id": pmid or pmcid or doi,
                        "retrieval_depth": "ABSTRACT_OR_METADATA",
                        "is_open_access_metadata": is_oa,
                    }
                ],
            )
        )
    return articles


def parse_crossref_json(payload: Mapping[str, Any], *, source: str = "crossref") -> list[Article]:
    message = payload.get("message", {})
    records = message.get("items", []) if isinstance(message, Mapping) else []
    if not isinstance(records, list):
        raise SourceError("Crossref message.items is not an array")
    articles: list[Article] = []
    for record in records:
        if not isinstance(record, Mapping):
            continue
        title_values = record.get("title", [])
        title = clean_text(title_values[0] if isinstance(title_values, list) and title_values else title_values)
        venue_values = record.get("container-title", [])
        journal = clean_text(
            venue_values[0] if isinstance(venue_values, list) and venue_values else venue_values
        )
        issn_values = record.get("ISSN", [])
        if not isinstance(issn_values, list):
            issn_values = [issn_values]
        issns = stable_unique(
            normalize_issn(value) for value in issn_values if normalize_issn(value)
        )
        publication_date = ""
        publication_date_precision = "UNKNOWN"
        for field in ("published-online", "published-print", "published", "issued"):
            value = record.get(field)
            if isinstance(value, Mapping):
                publication_date, publication_date_precision = _date_from_parts(
                    value.get("date-parts")
                )
            if publication_date:
                break
        authors: list[str] = []
        for author in record.get("author", []) if isinstance(record.get("author"), list) else []:
            if not isinstance(author, Mapping):
                continue
            family = clean_text(author.get("family"))
            given = clean_text(author.get("given"))
            name = clean_text(f"{family}, {given}" if family and given else family or given)
            if name:
                authors.append(name)
        doi = normalize_doi(record.get("DOI"))
        article_types = stable_unique([record.get("type"), record.get("subtype")])
        extra_urls: list[str] = []
        if str(record.get("URL") or "").startswith(("http://", "https://")):
            extra_urls.append(str(record["URL"]))
        links = record.get("link", [])
        if isinstance(links, list):
            extra_urls.extend(
                str(link.get("URL"))
                for link in links
                if isinstance(link, Mapping)
                and str(link.get("URL") or "").startswith(("http://", "https://"))
            )
        articles.append(
            Article(
                title=title,
                journal=journal,
                publication_date=publication_date,
                publication_date_precision=publication_date_precision,
                authors=stable_unique(authors),
                issns=issns,
                doi=doi,
                abstract=clean_text(record.get("abstract")),
                article_types=article_types,
                study_designs=classify_study_designs(title, article_types),
                urls=_article_urls(doi=doi, extra=extra_urls),
                oa_status="UNKNOWN",
                sources=[source],
                source_records=[
                    {
                        "source": source,
                        "record_id": doi,
                        "retrieval_depth": "METADATA",
                    }
                ],
            )
        )
    return articles


def _fixture_path(fixture_dir: Path | None, source: str) -> Path | None:
    if fixture_dir is None:
        return None
    suffix = ".xml" if source == "pubmed" else ".json"
    path = fixture_dir / f"{source}{suffix}"
    if not path.is_file():
        raise SourceError(f"fixture mode requires {path.name}")
    return path


def fetch_pubmed(
    collection: Collection,
    start: date,
    end: date,
    *,
    client: SafeHttpClient,
    fixture_dir: Path | None = None,
    max_records: int = 5000,
) -> SourceResult:
    journal_terms = [f'"{name}"[jour]' for name in collection.venue_names]
    journal_terms.extend(f"{issn}[issn]" for issn in collection.issns)
    query = (
        f"({' OR '.join(journal_terms)}) AND "
        f'("{start:%Y/%m/%d}"[Date - Publication] : "{end:%Y/%m/%d}"[Date - Publication])'
    )
    retrieved_at = utc_now_iso()
    fixture = _fixture_path(fixture_dir, "pubmed")
    if fixture:
        payload = fixture.read_text(encoding="utf-8")
        articles = parse_pubmed_xml(payload)
        return SourceResult(
            articles,
            SourceReceipt(
                source="pubmed",
                status="SUCCESS" if articles else "NO_RESULTS",
                query=query,
                endpoint=f"fixture://{fixture.name}",
                retrieved_at=retrieved_at,
                returned_count=len(articles),
                request_count=0,
                metadata={"fixture": True},
            ),
        )

    ids: list[str] = []
    request_count = 0
    retstart = 0
    total = 0
    while len(ids) < max_records:
        retmax = min(500, max_records - len(ids))
        response = client.get(
            f"{PUBMED_BASE}/esearch.fcgi",
            params={
                "db": "pubmed",
                "term": query,
                "retmode": "json",
                "retmax": retmax,
                "retstart": retstart,
                "sort": "pub date",
            },
        )
        request_count += 1
        payload = response.json()
        result = payload.get("esearchresult", {}) if isinstance(payload, Mapping) else {}
        page_ids = result.get("idlist", []) if isinstance(result, Mapping) else []
        if not isinstance(page_ids, list):
            raise SourceError("PubMed esearch idlist is not an array")
        ids.extend(clean_text(value) for value in page_ids if clean_text(value))
        try:
            total = int(result.get("count", 0))
        except (TypeError, ValueError):
            total = len(ids)
        retstart += len(page_ids)
        if not page_ids or retstart >= total or len(ids) >= max_records:
            break

    ids = ids[:max_records]
    articles: list[Article] = []
    for offset in range(0, len(ids), 200):
        response = client.get(
            f"{PUBMED_BASE}/efetch.fcgi",
            params={
                "db": "pubmed",
                "id": ",".join(ids[offset : offset + 200]),
                "retmode": "xml",
            },
        )
        request_count += 1
        articles.extend(parse_pubmed_xml(response.text))
    return SourceResult(
        articles,
        SourceReceipt(
            source="pubmed",
            status="SUCCESS" if articles else "NO_RESULTS",
            query=query,
            endpoint=PUBMED_BASE,
            retrieved_at=retrieved_at,
            returned_count=len(articles),
            request_count=request_count,
            metadata={
                "reported_count": total,
                "id_count": len(ids),
                "parse_drop_count": max(0, len(ids) - len(articles)),
                "max_records": max_records,
                "truncated": total > len(ids),
            },
        ),
    )


def fetch_europe_pmc(
    collection: Collection,
    start: date,
    end: date,
    *,
    client: SafeHttpClient,
    fixture_dir: Path | None = None,
    max_records: int = 5000,
) -> SourceResult:
    terms = [f'JOURNAL:"{name}"' for name in collection.venue_names]
    terms.extend(f"ISSN:{issn}" for issn in collection.issns)
    query = f"({' OR '.join(terms)}) AND FIRST_PDATE:[{start.isoformat()} TO {end.isoformat()}]"
    retrieved_at = utc_now_iso()
    fixture = _fixture_path(fixture_dir, "europe_pmc")
    if fixture:
        payload = json.loads(fixture.read_text(encoding="utf-8"))
        articles = parse_europe_pmc_json(payload)
        return SourceResult(
            articles,
            SourceReceipt(
                source="europe_pmc",
                status="SUCCESS" if articles else "NO_RESULTS",
                query=query,
                endpoint=f"fixture://{fixture.name}",
                retrieved_at=retrieved_at,
                returned_count=len(articles),
                request_count=0,
                metadata={"fixture": True},
            ),
        )

    articles: list[Article] = []
    cursor = "*"
    request_count = 0
    hit_count = 0
    while len(articles) < max_records:
        response = client.get(
            EUROPE_PMC_SEARCH,
            params={
                "query": query,
                "format": "json",
                "resultType": "core",
                "pageSize": min(200, max_records - len(articles)),
                "cursorMark": cursor,
            },
        )
        request_count += 1
        payload = response.json()
        if not isinstance(payload, Mapping):
            raise SourceError("Europe PMC response is not an object")
        try:
            hit_count = int(payload.get("hitCount", 0))
        except (TypeError, ValueError):
            hit_count = 0
        page = parse_europe_pmc_json(payload)
        articles.extend(page)
        next_cursor = clean_text(payload.get("nextCursorMark"))
        if not page or not next_cursor or next_cursor == cursor or len(articles) >= hit_count:
            break
        cursor = next_cursor
    return SourceResult(
        articles[:max_records],
        SourceReceipt(
            source="europe_pmc",
            status="SUCCESS" if articles else "NO_RESULTS",
            query=query,
            endpoint=EUROPE_PMC_SEARCH,
            retrieved_at=retrieved_at,
            returned_count=min(len(articles), max_records),
            request_count=request_count,
            metadata={
                "reported_count": hit_count,
                "max_records": max_records,
                "truncated": hit_count > min(len(articles), max_records),
            },
        ),
    )


def fetch_crossref(
    collection: Collection,
    start: date,
    end: date,
    *,
    client: SafeHttpClient,
    fixture_dir: Path | None = None,
    max_records: int = 5000,
) -> SourceResult:
    query_description = {
        "issns": list(collection.issns),
        "journal": collection.name,
        "from-pub-date": start.isoformat(),
        "until-pub-date": end.isoformat(),
    }
    query = json.dumps(query_description, ensure_ascii=False, sort_keys=True)
    retrieved_at = utc_now_iso()
    fixture = _fixture_path(fixture_dir, "crossref")
    if fixture:
        payload = json.loads(fixture.read_text(encoding="utf-8"))
        articles = parse_crossref_json(payload)
        return SourceResult(
            articles,
            SourceReceipt(
                source="crossref",
                status="SUCCESS" if articles else "NO_RESULTS",
                query=query,
                endpoint=f"fixture://{fixture.name}",
                retrieved_at=retrieved_at,
                returned_count=len(articles),
                request_count=0,
                metadata={"fixture": True},
            ),
        )

    articles: list[Article] = []
    request_count = 0
    scopes = list(collection.issns) or [""]
    reported_by_scope: dict[str, int] = {}
    truncated = False
    for scope_index, issn in enumerate(scopes):
        cursor = "*"
        scope_key = issn or f"journal:{collection.name}"
        while len(articles) < max_records:
            filters = [f"from-pub-date:{start.isoformat()}", f"until-pub-date:{end.isoformat()}"]
            if issn:
                filters.append(f"issn:{issn}")
            params: dict[str, Any] = {
                "filter": ",".join(filters),
                "rows": min(200, max_records - len(articles)),
                "cursor": cursor,
            }
            if not issn:
                params["query.container-title"] = collection.name
            response = client.get(CROSSREF_WORKS, params=params)
            request_count += 1
            payload = response.json()
            if not isinstance(payload, Mapping):
                raise SourceError("Crossref response is not an object")
            message = payload.get("message", {})
            if not isinstance(message, Mapping):
                raise SourceError("Crossref message is not an object")
            try:
                reported_by_scope[scope_key] = int(message.get("total-results", 0))
            except (TypeError, ValueError):
                reported_by_scope[scope_key] = 0
            page = parse_crossref_json(payload)
            articles.extend(page)
            next_cursor = clean_text(message.get("next-cursor"))
            if len(articles) >= max_records:
                truncated = bool(next_cursor and next_cursor != cursor)
                break
            if not page or not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
        if len(articles) >= max_records:
            if scope_index < len(scopes) - 1:
                truncated = True
            break
    delivered = articles[:max_records]
    return SourceResult(
        delivered,
        SourceReceipt(
            source="crossref",
            status="SUCCESS" if delivered else "NO_RESULTS",
            query=query,
            endpoint=CROSSREF_WORKS,
            retrieved_at=retrieved_at,
            returned_count=len(delivered),
            request_count=request_count,
            metadata={
                "reported_counts": reported_by_scope,
                "max_records": max_records,
                "truncated": truncated,
            },
        ),
    )


def fetch_source(
    source: str,
    collection: Collection,
    start: date,
    end: date,
    *,
    client: SafeHttpClient,
    fixture_dir: Path | None = None,
    max_records: int = 5000,
) -> SourceResult:
    adapters = {
        "pubmed": fetch_pubmed,
        "europe_pmc": fetch_europe_pmc,
        "crossref": fetch_crossref,
    }
    try:
        adapter = adapters[source]
    except KeyError as exc:
        raise SourceError(f"unsupported source: {source}") from exc
    return adapter(
        collection,
        start,
        end,
        client=client,
        fixture_dir=fixture_dir,
        max_records=max_records,
    )
