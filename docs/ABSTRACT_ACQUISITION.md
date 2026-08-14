# Abstract Acquisition v1

Abstract Acquisition is the first layer in EvidenceRadar Editions that actually retrieves abstract text. It consumes only the current bounded `AbstractFetchPlan`, which is generated from the public Editorial Shortlist.

```text
4,397 canonical bibliographic records
        ↓
precision-hardened prefetch triage
        ↓
public journal-metric Editorial Shortlist
        ↓
up to 300 FETCH_NOW records
        ↓
AbstractFetchPlan
        ↓
Abstract Acquisition v1
        ↓
sanitzed receipts + ephemeral content-addressed payload vault
```

## Scientific boundary

`ABSTRACT_ACQUIRED` means only that an exact planned identifier returned non-empty abstract text from an allowed metadata source. It does not mean the abstract has been reviewed, the article is in scope after abstract review, full text has been acquired, or evidence quality has been evaluated.

Every public receipt keeps `abstract_reviewed=false`, `full_text_fetched=false`, and `evidence_evaluated=false`. A later review artifact must bind the acquisition receipt and abstract SHA-256 before any `abstract_reviewed=true` claim is allowed.

## Bounded input

The executor accepts only `EvidenceRadar_Editions_AbstractFetchPlan` objects and rejects plans larger than the configured maximum (300 in production). It does not discover additional records.

## Acquisition sources

The plan uses fixed, identifier-based sources.

- **PubMed PMID:** EFetch XML is batched in groups of at most 100 PMIDs. Returned records are indexed by exact PMID.
- **Europe PMC:** core metadata is queried with `PMCID:<PMCID>`, `EXT_ID:<PMID> AND SRC:MED`, or `DOI:"<DOI>"`; the returned identifier must exactly match the planned identifier.
- **Crossref DOI:** `/works/{doi}` is the final DOI fallback; the returned DOI must exactly equal the normalized planned DOI.

No publisher landing-page scraping is performed.

## Final receipt states

`ABSTRACT_ACQUIRED`
: An exact planned record returned non-empty abstract text.

`ABSTRACT_NOT_PRESENT`
: At least one exact planned record was found, all attempted sources completed without transport/parser failure, and none contained an abstract.

`RECORD_NOT_FOUND`
: All applicable planned sources completed successfully but none returned an exact identifier match.

`ACQUISITION_INCONCLUSIVE`
: No abstract was acquired and at least one applicable planned source failed. A source outage is never rewritten as “no abstract”.

`SKIPPED_NO_IDENTIFIER`
: No executable planned identifier exists.

## Payload handling

Abstract text is normalized only enough to remove markup and preserve PubMed section labels. The exact normalized UTF-8 bytes are written to an ephemeral content-addressed vault:

```text
<payload-dir>/<sha256>.txt
```

Public receipts contain only acquisition source, source record identifier, attempt states, abstract SHA-256, byte count, and character count.

Before any GitHub Actions or Pages artifact is uploaded, the workflow verifies every payload hash and size, writes a payload-disposition record, deletes the entire payload vault, and asserts that the vault no longer exists. Abstract text is not committed to Git, placed in Pages, or included in the safe acquisition artifact.

## Public delivery

Pages publishes `/abstract-acquisition.html` and `/abstract-acquisition.json`. The safe Actions artifact contains `abstract-fetch-plan.json`, `abstract-acquisition-receipts.json`, `abstract-payload-disposition.json`, and `abstract-acquisition-manifest.json`.

The receipt binding covers the exact plan binding, record keys, terminal states, source attempts, source record IDs, and abstract SHA-256 values and sizes.

## API contract basis

Implementation follows the public APIs documented by NCBI, Europe PMC and Crossref: NCBI EFetch accepts comma-delimited PubMed UID lists and returns PubMed XML; Europe PMC supports DOI, PMID and PMCID-specific queries with core results; Crossref exposes single-work DOI metadata at `/works/{doi}`, including deposited abstracts when present.
