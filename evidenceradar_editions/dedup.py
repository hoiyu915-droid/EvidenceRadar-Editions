from __future__ import annotations

from collections import defaultdict

from .models import Article
from .utils import normalize_doi, normalize_issn, normalize_name, normalize_title_key


def journal_matches(article: Article, *, journal: str, issn: str | None) -> bool:
    if normalize_name(article.journal) == normalize_name(journal):
        return True
    if issn:
        target = normalize_issn(issn)
        observed = {value for value in (normalize_issn(v) for v in article.issns) if value}
        return bool(target and target in observed)
    return False


def _aliases(article: Article) -> set[str]:
    values = {
        f"title:{normalize_title_key(article.title)}|{normalize_name(article.journal)}|{article.publication_date.isoformat()}"
    }
    doi = normalize_doi(article.doi)
    if doi:
        values.add(f"doi:{doi}")
    if article.pmid:
        values.add(f"pmid:{article.pmid.strip()}")
    if article.pmcid:
        values.add(f"pmcid:{article.pmcid.strip().upper()}")
    return values


def _merge_into(target: Article, other: Article) -> None:
    precision_rank = {"YEAR": 1, "MONTH": 2, "DAY": 3}
    if other.publication_date < target.publication_date:
        target.publication_date = other.publication_date
        target.publication_date_precision = other.publication_date_precision
    elif (
        other.publication_date == target.publication_date
        and precision_rank.get(other.publication_date_precision, 0)
        > precision_rank.get(target.publication_date_precision, 0)
    ):
        target.publication_date_precision = other.publication_date_precision
    if not target.doi and other.doi:
        target.doi = other.doi
    if not target.pmid and other.pmid:
        target.pmid = other.pmid
    if not target.pmcid and other.pmcid:
        target.pmcid = other.pmcid
    if not target.article_type and other.article_type:
        target.article_type = other.article_type
    if not target.title_zh_tw and other.title_zh_tw:
        target.title_zh_tw = other.title_zh_tw
    if not target.summary_zh_tw and other.summary_zh_tw:
        target.summary_zh_tw = other.summary_zh_tw
    if not target.translation_basis and other.translation_basis:
        target.translation_basis = other.translation_basis
    if not target.translation_source_url and other.translation_source_url:
        target.translation_source_url = other.translation_source_url
    if len(other.authors) > len(target.authors):
        target.authors = list(other.authors)
    target.issns = sorted(set(target.issns + other.issns))
    target.urls = sorted(set(target.urls + other.urls))
    seen = {(record.source, record.source_id, record.url) for record in target.source_records}
    for record in other.source_records:
        key = (record.source, record.source_id, record.url)
        if key not in seen:
            target.source_records.append(record)
            seen.add(key)


def deduplicate_articles(articles: list[Article]) -> list[Article]:
    """Merge identity-linked records, including transitive alias chains."""

    if not articles:
        return []
    parent = list(range(len(articles)))

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    owner: dict[str, int] = {}
    for index, article in enumerate(articles):
        for alias in _aliases(article):
            previous = owner.get(alias)
            if previous is not None:
                union(index, previous)
            else:
                owner[alias] = index

    buckets: defaultdict[int, list[Article]] = defaultdict(list)
    for index, article in enumerate(articles):
        buckets[find(index)].append(article)

    groups: list[Article] = []
    for members in buckets.values():
        target = members[0]
        for other in members[1:]:
            _merge_into(target, other)
        groups.append(target)
    groups.sort(key=lambda article: (article.publication_date, article.title.casefold()), reverse=True)
    return groups


def counts_by_source(articles: list[Article]) -> dict[str, int]:
    bucket: defaultdict[str, set[str]] = defaultdict(set)
    for article in articles:
        for record in article.source_records:
            bucket[record.source].add(article.canonical_id)
    return {key: len(value) for key, value in sorted(bucket.items())}
