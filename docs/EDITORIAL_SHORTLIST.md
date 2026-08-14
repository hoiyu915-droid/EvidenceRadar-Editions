# Editorial Shortlist v1

The Editorial Shortlist layer answers one deliberately narrow question:

> Which small subset of the already-discovered records should receive abstract acquisition next?

It sits after precision-hardened prefetch triage and before any abstract or full-text review.

```text
4,397 canonical bibliographic records
        ↓
precision-hardened prefetch triage
        ↓
Editorial Shortlist
  FETCH_NOW / HOLD_RESERVE / CATALOG_ONLY
        ↓
bounded AbstractFetchPlan
        ↓
future abstract acquisition and review
```

## What it does not claim

The shortlist uses titles, bibliographic identifiers, journal processing mode, registry categories and prefetch-triage provenance. It does not read an abstract or full text.

`FETCH_NOW` therefore means only:

> allocate the next bounded abstract-acquisition slot to this record.

It does **not** mean that the article is scientifically valid, novel, relevant to a particular decision, clinically actionable, correctly reported or supported by full text.

Every output record keeps:

```text
abstract_fetch_requested = false
abstract_acquired = false
abstract_reviewed = false
full_text_fetched = false
evidence_evaluated = false
```

Those states may change only in a later, separately bound acquisition or review artifact.

## Three editorial routes

### `FETCH_NOW`

A small, identifier-bearing record set selected for the next abstract-acquisition pass.

The default target is 48 records across the whole latest-revision corpus. The selection is deterministic and applies:

- precision-hardened prefetch eligibility;
- per-journal caps based on `FULL`, `TRIAGE`, `INDEX_ONLY` and `SUSPENDED`;
- category floors and soft/hard caps;
- evidence-path floors and soft/hard caps;
- within-journal topic saturation limits;
- near-duplicate-title suppression;
- journal round-robin ordering.

Scientific Reports is currently `TRIAGE` and cannot contribute more than eight `FETCH_NOW` records under the default policy, no matter how many records it publishes.

### `HOLD_RESERVE`

A bounded, diverse reserve queue. It contains unselected prefetch candidates first, then selected prefetch-reserve records. It is not fetched automatically.

The default target is 144 records. Journal and topic caps prevent one high-volume source from filling the whole reserve queue.

### `CATALOG_ONLY`

The record remains in the canonical edition and the complete per-edition shortlist audit, but consumes no abstract-acquisition slot.

Integrity events are also `CATALOG_ONLY` for abstract acquisition and carry:

```text
integrity_attention = true
integrity_action = RECORD_MAINTENANCE
```

Retractions, expressions of concern and corrections therefore remain visible without wasting research-summary slots.

## Selection phases

The selector uses several explicit phases rather than one opaque weighted average:

1. **Category floors** seed broad corpus coverage.
2. **Evidence-path floors** prevent one design family from consuming the list.
3. **Soft-cap fill** expands the list while respecting normal category and path budgets.
4. **Hard-cap fill** relaxes only those soft budgets.
5. **Reserve backfill** is allowed only when the prefetch-candidate pool cannot fill the target under the journal, duplicate and topic constraints.

Every selected or held record receives decision reason codes such as:

```text
CATEGORY_FLOOR:clinical_medicine
PATH_FLOOR:RANDOMIZED_TRIAL
BALANCED_SOFT_FILL
BALANCED_HARD_FILL
PREFETCH_RESERVE_BACKFILL
NEAR_DUPLICATE_TITLE
JOURNAL_FETCH_CAP
FETCH_NOW_GLOBAL_TARGET
```

The reason codes explain operational placement; they are not scientific annotations.

## Published artifacts

Pages builds publish:

```text
/editorial-shortlist.html
/editorial-shortlist.json
/editorial-shortlist-policy.json
/abstract-fetch-plan.json
/journals/<journal>/<period>/rXX/shortlist.json
```

`editorial-shortlist.html` is the human-readable browser.

`editorial-shortlist.json` contains the bounded public work surface: `FETCH_NOW`, `HOLD_RESERVE` and integrity-maintenance records, plus reconciled corpus counts.

`abstract-fetch-plan.json` contains only `FETCH_NOW` records, exact identifiers and preferred fixed-source lookup order. It performs no network request and contains no abstract text.

Every latest revision also receives a complete `shortlist.json` audit containing all canonical records and their editorial route.

## Binding and reproducibility

The layer calculates:

- `policy_sha256` from the normalized executable policy;
- `source_prefetch_digest` from the exact prefetch route, path, score, reasons, identifiers and processing mode of every record;
- `shortlist_binding_sha256` from policy, source digest and all editorial decisions;
- `plan_binding_sha256` from the shortlist binding and exact AbstractFetchPlan entries.

Timestamps are excluded from the bindings. Rebuilding the same inputs produces the same shortlist and plan hashes. Changing a source triage score, route, identifier, decision or policy changes the binding.

## Policy file

The executable policy is `catalog/editorial-shortlist-policy.json`.

Important defaults:

```text
FETCH_NOW target:        48
HOLD_RESERVE target:    144

journal FETCH_NOW caps
  FULL:          4
  TRIAGE:        8
  INDEX_ONLY:    2
  SUSPENDED:     0
```

Category and evidence-path budgets are soft during the first fill and hard during the second. Journal caps, identifier availability, near-duplicate suppression and per-journal topic caps remain hard.

A lightweight temporary catalog may omit the optional policy file. In that case the validated built-in default is used and the resolved policy is still published in the Pages output, keeping the build self-describing.

## Delivery boundary

Editorial Shortlist v1 deliberately stops at a bounded plan. The next layer may fetch only records present in `abstract-fetch-plan.json`, must bind its receipts to `plan_binding_sha256`, and must distinguish:

```text
ABSTRACT_ACQUIRED
ABSTRACT_NOT_PRESENT
RECORD_NOT_FOUND
ACQUISITION_INCONCLUSIVE
SKIPPED_NO_IDENTIFIER
```

It must not reinterpret an HTTP failure as “no abstract,” and it must not turn `FETCH_NOW` into an evidence-quality claim.
