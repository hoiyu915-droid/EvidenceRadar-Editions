from __future__ import annotations

from collections import defaultdict

from .models import Article
from .utils import normalize_doi, normalize_issn, normalize_name, normalize_title_key


def journal_matches(article: Article, *, journal: str, issn: str | None) -> bool:
    if normalize_name(article.journal) == normalize_name(journal):
        return True
    if issn:
        target = normalize_issn(issn)
        return bool(target and target in {normalize_issn(v) for v in article.issns})
    return False


def _aliases(article: Article) -> set[str]:
    values = {f"title:{normalize_title_key(article.title)}|{article.publication_date.isoformat()}"}
    doi = normalize_doi(article.doi)
    if doi:
        values.add(f"doi:{doi}")
    if article.pmid:
        values.add(f"pmid:{article.pmid.strip()}")
    if article.pmcid:
        values.add(f"pmcid:{article.pmcid.strip().upper()}")
    return values


def _merge_into(target: Article, other: Article) -> None:
    if not target.doi and other.doi:
        target.doi = other.doi
    if not target.pmid and other.pmid:
        target.pmid = other.pmid
    if not target.pmcid and other.pmcid:
        target.pmcid = other.pmcid
    if not target.article_type and other.article_type:
        target.article_type = other.article_type
    if len(other.authors) > len(target.authors):
        target.authors = list(other.authors)
    target.issns = sorted(set(target.issns + other.issns))
    target.urls = sorted(set(target.urls + other.urls))
    seen = {(r.source, r.source_id, r.url) for r in target.source_records}
    for record in other.source_records:
        key = (record.source, record.source_id, record.url)
        if key not in seen:
            target.source_records.append(record)
            seen.add(key)


def deduplicate_articles(articles: list[Article]) -> list[Article]:
    groups: list[Article] = []
    alias_to_index: dict[str, int] = {}
    for article in articles:
        aliases = _aliases(article)
        hits = {alias_to_index[a] for a in aliases if a in alias_to_index}
        if hits:
            index = min(hits)
            target = groups[index]
            _merge_into(target, article)
            for alias in _aliases(target) | aliases:
                alias_to_index[alias] = index
        else:
            index = len(groups)
            groups.append(article)
            for alias in aliases:
                alias_to_index[alias] = index
    groups.sort(key=lambda a: (a.publication_date, a.title.casefold()), reverse=True)
    return groups


def counts_by_source(articles: list[Article]) -> dict[str, int]:
    bucket: defaultdict[str, set[str]] = defaultdict(set)
    for article in articles:
        for record in article.source_records:
            bucket[record.source].add(article.canonical_id)
    return {key: len(value) for key, value in sorted(bucket.items())}
