# Edition delivery contract v1.0

An EvidenceRadar Edition is one immutable logical bundle represented by four files in one directory.

## Scope contract

The build request supplies:

- one collection profile;
- one inclusive start date;
- one inclusive end date;
- one or more supported source adapters;
- one retrieval timestamp;
- optional pinned EvidenceRadar source checkout.

Every normalized record is locally filtered after retrieval. A record is eligible only when:

1. the complete uncertainty interval implied by publication-date precision falls inside the inclusive period;
2. ISSN or exact normalized journal title／alias matches the collection;
3. article type satisfies `include_types` and `exclude_types`.

Day precision maps to one day, month precision to the full calendar month, and year precision to the full calendar year. A coarse record is excluded when its possible interval crosses the requested boundary; it is never silently assigned to the first day of a week or partial month.

A source query alone is never trusted as the final scope gate.

## `edition.json`

Required top-level fields:

| Field | Meaning |
|---|---|
| `schema_version` | Contract version, currently `1.0` |
| `edition_id` | Stable collection/period identifier |
| `status` | `COMPLETE`, `PARTIAL`, or `FAILED` based on source failures and explicit record-bound truncation |
| `retrieved_at` | UTC retrieval timestamp |
| `data_semantics` | Current-source historical reconstruction statement |
| `collection` | Canonical collection profile |
| `period` | Inclusive date scope, timezone and date basis |
| `article_count` | Number of canonical articles after deduplication |
| `raw_record_count` | Number of parsed source records before local scope filtering |
| `scope_filter_counts` | Explicit rejection ledger |
| `articles` | Canonical article array |
| `warnings` | Non-fatal limitations |
| `provenance` | Producer, upstream source pin and config hash |

Each article contains a `canonical_id`, identifiers, venue/date, authors, abstract where supplied, OA/full-text status, source URLs and source-record provenance.

## `sources.json`

Each configured adapter emits exactly one receipt:

- `SUCCESS`: operation completed and returned at least one raw record;
- `NO_RESULTS`: operation completed and returned zero raw records;
- `FAILED`: the operation did not complete successfully.

A receipt records source, status, exact query description, endpoint, retrieval timestamp, raw record count, HTTP request count, error and adapter metadata. When a configured record bound prevents full pagination, metadata records `truncated=true` and the edition status is `PARTIAL` even though the completed source operation remains `SUCCESS`.

`NO_RESULTS` must never be used for a timeout, parse failure, blocked endpoint or unattempted source.

## `index.html`

The HTML is a projection of `edition.json` and `sources.json`. It contains:

- edition and article identity markers;
- visible source status table;
- current-source reconstruction warning;
- client-side search, OA and study-design filters;
- escaped source metadata and safe HTTP(S) links;
- producer/upstream provenance.

The HTML does not carry separate scientific claims that are absent from canonical JSON.

## `manifest.json`

The manifest binds exactly:

- `index.html`;
- `edition.json`;
- `sources.json`.

For each file it records relative path, byte size and SHA-256. The manifest is not self-hashed. Release systems may sign or hash the complete directory externally.

## Validation boundary

The validator fails on:

- missing artifact;
- unsupported schema version;
- article count or HTML marker mismatch;
- empty, unknown or duplicate canonical IDs;
- invalid source status;
- absent query/endpoint receipt;
- missing `artifacts_consumed=false` upstream statement;
- wrong artifact set, byte size or SHA-256;
- local-only links in HTML.

Passing v1.0 validation means the bundle is internally coherent and tamper-evident. It does not certify source completeness, research quality or clinical validity.
