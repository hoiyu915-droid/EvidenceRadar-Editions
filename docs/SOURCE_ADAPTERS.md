# Source adapters

## Common rules

All adapters are bounded by `max_records`. If the source reports more records than the adapter can deliver within that bound, its receipt records `truncated=true` and the edition becomes `PARTIAL`.

All adapters:

1. receive the same collection and inclusive date range;
2. issue a source-native scoped query;
3. parse bibliographic records without converting them into scientific claims;
4. emit one source receipt;
5. pass records to the same local journal/date/type hard filter;
6. participate in the same identity deduplication stage.

Network requests use public HTTP(S) validation, redirect revalidation, retry policy, timeout and an 8 MiB response limit.

## PubMed

Query shape:

```text
(<exact journal names and/or ISSNs>) AND
("YYYY/MM/DD"[Date - Publication] : "YYYY/MM/DD"[Date - Publication])
```

The adapter uses ESearch for IDs and EFetch for PubMed XML. It extracts PMID, DOI, PMCID, article title, journal, ISSN, publication date, author list, abstract and publication types.

Known limitation: PubMed may index an article after its publisher publication date. A historical reconstruction run sees the current index, not the historical state of the index.

## Europe PMC

Query shape:

```text
(<JOURNAL or ISSN clauses>) AND
FIRST_PDATE:[YYYY-MM-DD TO YYYY-MM-DD]
```

The adapter requests `resultType=core` and cursor pagination. It extracts PMID, PMCID, DOI, journal, ISSN, first publication date, authors, abstract, publication types and OA metadata.

`isOpenAccess=Y` or a PMCID can set `oa_status=YES`; it does not set `fulltext_status=ACCESSIBLE` without a separate direct access observation.

## Crossref

For each collection ISSN, the adapter requests `/works` with:

```text
from-pub-date, until-pub-date, issn
```

If no ISSN is configured, it falls back to `query.container-title` plus the date filter. Cursor pagination and field selection bound the response. Crossref records are always rechecked locally because container-title and date behavior may be broader than the intended collection. `created.date-time` is not used as a publication-date fallback.

Crossref is treated as metadata. A DOI URL is a source link, not proof that full text is readable.

## Adding an adapter

A new adapter belongs in `src/evidenceradar_editions/sources.py` or a dedicated module when it becomes large. It must:

- have deterministic parser tests;
- support `max_records` or another explicit bound;
- expose the exact query in its receipt;
- distinguish no results from failure;
- avoid secrets by default, or document optional secret handling;
- return normalized `Article` objects without bypassing local scope filtering;
- not fetch or ingest EvidenceRadar generated artifacts.
