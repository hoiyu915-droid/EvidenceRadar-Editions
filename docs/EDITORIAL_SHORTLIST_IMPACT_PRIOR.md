# Editorial Shortlist v2: public journal-metric prior

Editorial Shortlist v2 replaces the fixed per-journal `4 / 8 / 2` FETCH_NOW
limits with a public, reproducible allocation policy.

The purpose is narrow:

> allocate up to 300 abstract-fetch slots across the already-discovered monthly
> corpus without embedding one operator's personal reading preferences.

It does **not** use a journal metric as an article-level evidence or quality
score. It does not claim that a selected article is valid, novel, relevant,
clinically actionable, or supported by its abstract or full text.

## Pipeline position

```text
canonical edition metadata
        ↓
precision-hardened prefetch triage
        ↓
Editorial Shortlist v2
  FETCH_NOW / HOLD_RESERVE / CATALOG_ONLY
        ↓
≤300-record AbstractFetchPlan
        ↓
future bounded abstract acquisition
```

No abstract or full text is requested while building the shortlist.

## Public metric registry

`catalog/journal-impact-metrics.json` stores one auditable record per registered
journal. Each record contains:

- journal identity and registry categories;
- publisher-displayed Journal Impact Factor (JIF), where available;
- publisher-displayed CiteScore as a fallback;
- the metric year when the publisher page labels one;
- the observation date;
- the publisher URL and a source note;
- an explicit status when no current public metric was verified.

The registry intentionally does not scrape or redistribute proprietary JCR
tables. It records only values displayed publicly by the journal or publisher.

JIF is preferred when both metrics are available. A CiteScore-only journal is
compared with the CiteScores of all other journals in the same local registry
category, including journals that also publish a JIF. This avoids creating a
one-item fallback peer group.

## Field normalization

Raw JIF values are not compared across the whole portfolio. For each metric
kind, v2 computes a midrank percentile within every local registry category:

```text
clinical_medicine × JIF
llm_research × JIF
llm_research × CiteScore
sport_science × JIF
...
```

A journal assigned to several categories receives the arithmetic mean of its
category percentiles. The categories are the public taxonomy in
`catalog/journals.json`, not a user-specific preference profile.

A journal with no current publisher-displayed metric receives percentile `50`.
Missing data is therefore neutral, not a penalty. PLOS journals are also neutral
because PLOS does not promote Journal Impact Factor as an assessment tool.

## Two-stage admission

The metric does not decide whether a strong structural signal is allowed to
compete.

### 1. Metric-independent candidate pass

Fetchable precision-hardened `FETCH_CANDIDATE` records are considered first,
using journal round-robin, topic caps, near-duplicate suppression, journal hard
caps, and the global 300-record ceiling.

This preserves recall for explicit guideline, synthesis, randomized-trial,
replication, safety, resource, and other structural signals even when the
journal has a low or missing metric.

### 2. Metric-aware reserve allocation

Remaining slots are filled from prefetch `RESERVE` records. Each journal gets a
transparent adaptive target:

```text
ceil(fetchable eligible records
     × metric capture rate
     × processing-mode modifier)
```

The default capture bands are:

| Registry-category percentile | Capture rate |
| --- | ---: |
| 90–100 | 100% |
| 75–<90 | 90% |
| 50–<75 | 80% |
| <50 | 70% |
| missing metric | 75% |

Processing-mode modifiers are:

| Mode | Modifier | Hard journal cap |
| --- | ---: | ---: |
| `FULL` | 1.00 | 40 |
| `TRIAGE` | 0.45 | 60 |
| `INDEX_ONLY` | 0.20 | 8 |
| `SUSPENDED` | 0.00 | 0 |

The adaptive target is a soft allocation. If global capacity remains, a
metric-prior journal round-robin may use spare capacity up to the hard cap. A
high-volume source can therefore contribute more than a tiny fixed number, but
cannot consume the entire monthly queue.

## Global budget and routes

The default monthly soft ceiling is 300 `FETCH_NOW` records. The policy does not
manufacture 300 records when fewer are eligible and fetchable.

All other eligible records become `HOLD_RESERVE`; they remain visible for a
later pass. Non-eligible records remain `CATALOG_ONLY`. Integrity records stay
visible with `RECORD_MAINTENANCE` and never consume abstract-fetch slots.

Every record remains in its immutable canonical edition and complete
per-edition `shortlist.json` audit.

## Acquisition boundary

Every shortlist decision and AbstractFetchPlan item retains:

```text
abstract_fetch_requested = false
abstract_acquired = false
abstract_reviewed = false
full_text_fetched = false
evidence_evaluated = false
```

`FETCH_NOW` means only that the record has been allocated an abstract-fetch
slot. A later acquisition artifact must change the acquisition state.

## Reproducibility and tamper evidence

The shortlist binds:

- the normalized executable shortlist policy;
- the normalized journal-impact registry;
- the exact prefetch route, path, score, reasons, identifiers, and processing
  mode for every record;
- every final editorial decision;
- the exact AbstractFetchPlan entries and source order.

Changing the policy, metric registry, source triage, identifiers, or decisions
changes the corresponding SHA-256 binding. Timestamps are excluded from the
binding inputs.

## Maintenance

Journal metrics are evidence inputs, not constants. Updates must:

1. use a publisher or journal page;
2. record the observation date and metric year when explicitly labelled;
3. preserve the previous value in Git history;
4. run the full CI matrix and production-corpus regression;
5. inspect changes in journal, category, metric-kind, and processing-mode
   distributions before merge.

A missing or disputed value should be removed and allowed to fall back to the
neutral prior rather than guessed from a third-party ranking site.
