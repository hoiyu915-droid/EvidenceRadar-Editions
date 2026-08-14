# Metadata semantic triage

EvidenceRadar Editions uses metadata triage to turn a very large bibliographic archive into an explainable queue for later abstract or full-text review.

The executable policy is [`catalog/metadata-triage-policy.json`](../catalog/metadata-triage-policy.json). Its current identifier is `metadata-title-triage-v1`.

## What this stage does

Every article in the latest immutable revision of each journal/period is evaluated using only fields already present in the canonical edition:

- original title;
- source article type;
- DOI, PMID and PMCID presence;
- source-record provenance;
- publication role derived conservatively from title prefixes.

The result is attached only to generated Pages/search artifacts. Canonical `editions/**/edition.json` files are not rewritten.

Each record receives:

- a tier: `ALERT`, `HIGH`, `MEDIUM` or `LOW`;
- an attention class such as `EVIDENCE_SYNTHESIS`, `CONTROLLED_TRIAL`, `SAFETY_ALERT`, `CORRECTION` or `PRIMARY_RESEARCH`;
- a next-action recommendation;
- explicit reason codes;
- a declaration that scientific judgment still requires an abstract or full text.

## Tiers and actions

| Tier | Meaning | Typical action |
| --- | --- | --- |
| `ALERT` | Metadata indicates a retraction, expression of concern or withdrawal notice | `VERIFY_IMMEDIATELY` |
| `HIGH` | Metadata indicates a study form that often deserves earlier human review, such as a guideline, systematic synthesis, controlled trial, external validation, replication/null result or reusable dataset | `FETCH_PRIORITY` |
| `MEDIUM` | A plausible research record without a stronger metadata signal, or a cohort, protocol, ordinary review or case report | `FETCH_IF_CAPACITY` |
| `LOW` | Correction, editorial, front matter or another record normally kept for context rather than automatic evidence review | `METADATA_ONLY` |

These tiers are **operational queue positions**, not evidence grades. A `HIGH` record can be weak, biased, redundant or irrelevant after reading it. A `MEDIUM` record can be decisive. No tier asserts novelty, effect magnitude, methodological quality, applicability or truth.

## Reason codes

The policy exposes named reason codes rather than a fake-precision score. Examples include:

- `SAFETY_ALERT`;
- `GUIDANCE`;
- `EVIDENCE_SYNTHESIS`;
- `CONTROLLED_TRIAL`;
- `REPLICATION_OR_NULL`;
- `RESOURCE_OR_BENCHMARK`;
- `VALIDATION_OR_DIAGNOSTIC`;
- `PROSPECTIVE_OR_COHORT`;
- `PROTOCOL`;
- `REVIEW`;
- `CASE_REPORT`;
- `CORRECTION`;
- `EDITORIAL_OR_FRONTMATTER`;
- `NO_STRONG_METADATA_SIGNAL`.

Identifier and provenance reasons such as `HAS_DOI`, `HAS_PMID`, `HAS_PMCID` and `MULTI_SOURCE_METADATA` are added separately. They improve traceability; they do not prove scientific quality.

Terminal signals are ordered deliberately. For example, `Correction: Systematic review ...` remains a correction rather than being promoted as a systematic review, and `Editorial Expression of Concern ...` remains a safety alert rather than an ordinary editorial.

## Projection after all-record triage

The processing-policy limits from `catalog/processing-policies.json` still control how many records the default Pages browser/search payload may contain. The crucial difference is that the limit is applied **after every canonical record in that edition has been triaged**.

Within an edition, projected records are selected by:

1. tier order;
2. round-robin attention-class buckets within each tier;
3. stable metadata ordering;
4. near-duplicate title suppression using token Jaccard similarity;
5. deterministic fallback filling when a tier still has remaining capacity.

This prevents the previous canonical-first-N behavior from hiding a strong metadata signal merely because it appeared late in the source order.

The global triage dashboard additionally interleaves journals within each tier. A megajournal cannot consume the entire first page while other journals have records at the same tier.

## Current-corpus reprocessing

A production build reads every latest-revision canonical edition and creates two distinct public payloads:

- `metadata-triage.json`: all latest-revision canonical records with triage metadata, loaded only by the dedicated dashboard;
- `search-index.json`: the bounded default projection used by the portal search.

The existing 4,397-record corpus is therefore fully triaged once per production build. Records omitted from the default search payload remain available in `metadata-triage.json` and in each immutable canonical edition JSON.

## Public files

A triaged Pages deployment contains:

```text
metadata-triage-policy.json
metadata-triage.json
metadata-triage/index.html
search-index.json
index.json
links.json
journals/<journal>/<period>/rXX/browse.json
journals/<journal>/<period>/rXX/index.html
```

`index.json` and `links.json` publish canonical, priority-candidate, projected and omitted counts plus the active policy identifier. Per-revision `browse.json` publishes canonical/projected/omitted counts and both canonical and projected tier distributions.

## Build locally

```bash
python -m evidenceradar_editions.triage_delivery \
  --editions-root editions \
  --catalog-root catalog \
  --repository hoiyu915-droid/EvidenceRadar-Editions \
  --output-dir _site-triage
```

The command first builds the normal Pages site from canonical editions, then replaces only generated browsing/search artifacts with the triage-aware projections. It never mutates the canonical store.

## Deployment sequence

The ordinary workflow, `Publish EvidenceRadar Editions portal`, builds and deploys the canonical Pages projection. After it succeeds, `Publish metadata-triaged Editions portal` checks out the exact triggering main commit, rebuilds from the canonical editions, validates count invariants and deploys the triaged portal as the final production surface.

The second workflow verifies that:

- the all-record triage count equals the length of `metadata-triage.json`;
- projected search count equals the number of search records;
- canonical minus projected equals omitted;
- every triage record declares the metadata-only basis;
- public links and policy identifiers agree.

## Promotion to evidence review

Metadata triage answers only: **which records should receive scarce attention next?**

A later abstract/full-text stage must preserve a separate state transition, for example:

```text
METADATA_TRIAGED
→ ABSTRACT_REQUESTED / FULLTEXT_REQUESTED
→ ABSTRACT_ACQUIRED / FULLTEXT_ACQUIRED
→ EVIDENCE_EVALUATED
→ EDITORIAL_SELECTED
```

Until one of those later artifacts exists, Editions must not describe a record as full-text fetched, evidence evaluated, verified, high quality or clinically actionable.

## Changing the policy

Policy changes are executable-contract changes. A pull request should include:

1. the exact phrase or article-type rule;
2. why metadata alone supports that operational routing decision;
3. positive tests;
4. collision tests against higher-priority terminal signals;
5. a full-corpus rebuild showing tier and projection deltas;
6. confirmation that canonical edition bytes remain untouched.

Thresholds and phrases should be calibrated against retained editorial anchor sets. They must not be tuned merely to produce a desired number of `HIGH` records.
