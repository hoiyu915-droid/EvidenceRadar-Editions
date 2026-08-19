# Incremental date backfill

## Contract

Incremental backfill extends an existing monthly Edition without reacquiring the
already-covered prefix of that month.

For a base covering `2026-08-01..2026-08-14`, a request for
`2026-08-15..2026-08-19` performs this sequence:

1. validate the latest immutable monthly base revision;
2. acquire only `2026-08-15..2026-08-19` from the journal's configured sources;
3. fail closed on a source-access gap or partial source coverage;
4. merge by stable canonical identity and retain any article-bound translation
   already present in the base;
5. write a new full monthly snapshot revision with an explicit backfill receipt;
6. rebuild Pages from the canonical store after the guarded publication merge.

The result is not described as a new current-source reconstruction of the whole
month. Its data semantics are:

```text
incremental_acquisition_merged_with_immutable_base_snapshot
```

This distinction matters because the previously covered prefix is inherited
from a validated immutable snapshot rather than queried again.

## Continuity and revision rules

- The acquisition start must be exactly one day after the latest base end.
- One backfill request cannot cross a calendar-month boundary.
- The result revision must be the base revision plus one.
- Existing revision bytes are never overwritten.
- Stable IDs are deduplicated across the base and delta.
- New untranslated records remain visibly untranslated; inherited translations
  retain their original hash-bound provenance.
- A rerun with an existing matching receipt and valid targets is idempotent.

These rules target missing suffix dates. Repairing a hole inside an already
published window requires a separately audited repair mode because the
provenance and conflict semantics differ.

## Static Pages behavior

GitHub Pages does not execute the acquisition or merge. GitHub Actions builds a
complete deployment snapshot from the canonical JSON store:

```text
immutable r01 + live date delta -> immutable r02 -> Pages-time HTML projection
```

The Git deployment contains all existing site files, but only the requested
journals acquire new source data and canonical revisions. Global search and
journal navigation already choose the highest revision for each logical period,
so an `r02` becomes the current August view while `r01` remains browsable.

## Batch request

`catalog/backfill-request.json` is the executable request. It fixes:

- the exact journal slugs and their order;
- acquisition start and end dates;
- the target revision;
- a stable request ID used for the receipt and publication branch.

The production workflow writes
`catalog/coverage/backfills/<request-id>.json`, publishes all generated targets
in one guarded PR, dispatches Pages once, and waits for the exact merged SHA.

## Cambridge provider editions

Cambridge journals use a provider catalog separate from the core journal
registry. Follow the dedicated
[Cambridge incremental backfill operator note](CAMBRIDGE_INCREMENTAL_BACKFILL.md)
before preparing or diagnosing a Cambridge batch.
