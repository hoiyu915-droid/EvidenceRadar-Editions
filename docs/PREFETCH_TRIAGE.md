# Metadata pre-fetch triage

The pre-fetch triage layer answers one narrow operational question:

> Which already-discovered bibliographic records deserve a later fetch attempt or immediate integrity maintenance?

It does **not** answer whether a study is correct, novel, clinically important, statistically convincing, or supported by full text. The current adapters provide titles and bibliographic metadata; therefore the triage output is deliberately labelled as title-and-metadata inference.

## Pipeline position

```text
latest canonical edition metadata
            ↓
structural title / identifier signals
            ↓
source-saturation and journal-volume controls
            ↓
INTEGRITY_REVIEW / FETCH_CANDIDATE / RESERVE / CATALOG_ONLY
            ↓
future abstract or full-text acquisition
```

No abstract or publisher PDF is requested while building the triage artifacts.

## Routes

- `INTEGRITY_REVIEW`: retraction, withdrawal, expression of concern, correction, corrigendum, or erratum. These records are kept separate from research-fetch candidates because they require record maintenance rather than scientific ranking.
- `FETCH_CANDIDATE`: a title or metadata record crosses the configured operational threshold after saturation and journal-cap controls.
- `RESERVE`: a plausible record below the automatic fetch line, or a candidate demoted by a journal soft cap.
- `CATALOG_ONLY`: retained in the complete edition audit without automatic fetch work.

All records remain in canonical `edition.json`. The route does not delete or rewrite article identity.

## Max-path scoring

The engine does not average many mediocre features into a high score. Each article receives a primary path equal to the strongest explicit structural signal:

- integrity event;
- explicit guideline or position statement;
- evidence synthesis;
- randomized trial;
- replication or external validation;
- safety or adverse-event signal;
- dataset, corpus, or benchmark;
- prospective or longitudinal design;
- observational design;
- survey, protocol, case report, editorial, or generic primary metadata.

Identifier and title-specificity bonuses are small. They improve fetchability and record specificity; they do not pretend to improve evidence quality.

The executable values live in `catalog/prefetch-triage-policy.json`.

## Source-saturation guard

A structural term can become meaningless when it describes most of a journal. For example, a data journal can include “dataset” in a large fraction of its titles.

For configured paths, the engine calculates within-journal prevalence. When the path appears at least the configured minimum number of times and exceeds the prevalence threshold, it applies `COMMON_SOURCE_PATTERN` and subtracts the saturation penalty.

This prevents a megajournal or specialized container from occupying the fetch queue merely because its normal article template happens to match one lexical signal.

## Journal soft caps

After thresholding, ordinary fetch candidates are bounded per journal according to the journal processing mode:

- `FULL`: 30;
- `TRIAGE`: 20;
- `INDEX_ONLY`: 10;
- `SUSPENDED`: 0.

Scores at or above `exceptional_bypass` pass through the soft cap. Integrity-review records are not mixed into or consumed by the research-fetch cap.

A demoted candidate becomes `RESERVE` and receives `JOURNAL_SOFT_CAP` in its reason codes.

## Bounded portfolio index, complete edition audits

The root `prefetch-triage-index.json` contains:

- all `INTEGRITY_REVIEW` records;
- all retained `FETCH_CANDIDATE` records;
- a bounded reserve sample per journal.

The reserve sample prevents a worst-case journal from turning the root triage page into another multi-thousand-record payload. Records excluded from the root reserve sample receive `RESERVE_INDEX_SOFT_CAP`.

Every latest edition also publishes a complete `triage.json` containing all of its records, including `CATALOG_ONLY` and reserve records omitted from the root index.

## Published Pages artifacts

```text
/prefetch-triage.html
/prefetch-triage-index.json
/prefetch-triage-policy.json
/journals/<journal>/<period>/rXX/triage.json
```

`index.json` and `links.json` expose the reconciled counts and public URLs. The portal home page links to the human-readable candidate browser, and each revision page links to its complete triage audit.

## Record-level provenance

Each triage record includes:

- primary and matched paths;
- raw and adjusted score components;
- reason codes;
- within-journal path prevalence;
- processing mode and policy source;
- journal soft-cap disposition;
- identifiers and source URLs;
- explicit `abstract_reviewed=false`, `full_text_fetched=false`, and `evidence_evaluated=false` fields.

Those negative provenance fields are contractual. A downstream fetch worker must create a separate receipt before any record can be described as abstract-reviewed, full-text-acquired, or evidence-evaluated.

## Editing and validation

Policy changes are code changes. They must pass the full CI matrix and should be tested against:

- known false-positive phrases such as “consensus clustering” and “recommendation systems”;
- correction/retraction precedence over study-design terms;
- a synthetic 4,397-record journal;
- source-saturation behavior;
- reconciliation between root index counts and complete per-edition audits.

The current layer is intentionally deterministic and API-key-free. A later semantic model can consume the reserve queue, but its response must remain a separate, hash-bound artifact rather than silently replacing this auditable first pass.
