# Prefetch triage signal precision

The first production artifact audit exposed a predictable problem with bare lexical matching: words that look like research-design signals can have unrelated meanings.

The precision layer therefore treats title patterns as structural phrases rather than isolated keywords.

## Hardened cases

- Molecular `DNA replication`, `replication fork`, and the adjective `reproducible` do not count as replication/reproducibility studies. The path requires `replication study/attempt/analysis/experiment/report`, `reproducibility`, or explicit external/independent/validation-study language.
- `guidelines-aligned`, compliance with guidelines, studies of guideline developers, and an `expert consensus` comparator do not become guidance publications. Guidance must begin the title, begin a subtitle, or use an explicit position/consensus statement or expert-consensus recommendation/report phrase.
- `Re:`, `Comment on`, `Reply`, `Response to`, letters, and `Concerns about` are classified as correspondence before embedded phrases such as `systematic review`, `mortality`, `toxicity`, or `prospective study` are considered. They remain catalog-only unless another integrity rule applies.
- `Non-Randomised Trial` does not match the randomized-trial path.
- A named dataset used by a study, such as `the All of Us Dataset`, is not automatically a published data resource. Dataset matching requires resource-construction language such as `novel dataset`, `dataset for/of/...`, or an explicit benchmark/corpus/database/data-resource phrase.
- The word `longitudinal` must describe a study, analysis, cohort, data, follow-up, or survey. `Longitudinal care` is not a longitudinal design. Retrospective and generic cohort-study titles remain observational unless an explicit prospective signal is present.

## Precedence

The order remains:

1. retraction/expression-of-concern and correction integrity events;
2. correspondence/editorial routing;
3. structural research paths;
4. generic primary metadata.

Within structural paths, the existing maximum-path rule selects the strongest explicit reason. No weighted average is introduced.

## Regression expectations

Precision changes must retain these invariants:

- every latest canonical record appears in exactly one per-edition `triage.json` entry;
- root index counts reconcile with per-edition audit counts;
- `abstract_reviewed`, `full_text_fetched`, and `evidence_evaluated` remain false before a separate acquisition receipt exists;
- journal and reserve soft caps remain enforced;
- correspondence cannot consume a research fetch slot merely because it quotes the title of the paper being discussed.
