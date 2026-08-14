# Default end-to-end Edition pipeline

The default production contract is no longer “build an Edition artifact and stop”. A live scoped Edition now publishes into the canonical store, merges through a generated PR, explicitly dispatches the normal Pages workflow, and waits for that downstream workflow to finish.

```text
live scoped source acquisition
→ validated Edition bundle
→ canonical editions/ publication
→ generated publication branch + PR
→ squash merge to main
→ explicit Pages workflow_dispatch
→ corpus prefetch triage
→ public journal-metric shortlist (≤300 abstracts)
→ live abstract acquisition
→ hash-bound structural abstract review
→ access-independent full-text allocation (≤120)
→ open full-text acquisition
→ full-text structural audit
→ deterministic evidence-reporting audit
→ evaluated editorial projection
→ safe artifacts + Pages
```

## Why the Pages workflow is explicitly dispatched

GitHub deliberately suppresses most recursive workflow triggers caused by `GITHUB_TOKEN`. The live workflow therefore does not depend on a generated merge accidentally triggering another workflow. After the publication PR merges, it calls `pages.yml` with `workflow_dispatch`, resolves the downstream run by the exact merge SHA, and waits for that run to succeed.

A live publication fails closed if `main` moves between source acquisition and publication. The workflow stages only the exact generated canonical target and refuses unrelated staged paths.

## Translation boundary

Canonical live publication is allowed to enter the store before zh-TW translation is complete. Pages therefore builds with `--allow-untranslated`; any existing translation remains visible, while untranslated records retain their source-language title and their basis remains explicit. Translation completion is not used as an evidence-priority signal.

## Evidence Evaluation v1

Evidence Evaluation v1 reads only hash-verified full-text payloads before the ephemeral full-text vault is deleted. XML and plain-text payloads receive a design-aware reporting checklist. The checklist records whether design-relevant elements are detectable, for example randomization, primary outcomes, sample size, effect-estimate language, trial registration, search strategy, risk-of-bias methods, confounding adjustment, external validation, limitations, funding and conflicts.

`evidence_evaluated=true` has a deliberately narrow meaning:

> a deterministic full-text evidence-reporting checklist was executed on hash-verified machine-readable text.

It does **not** mean formal risk of bias, causal validity, effect magnitude, clinical importance, novelty or recommendation strength has been established. Those dimensions remain explicit `false`/unclaimed fields rather than being inferred from a journal metric or reporting completeness.

PDF-only payloads are not silently promoted. If the production runner has no machine-readable text representation, the record ends as `LIMITED_PDF_OR_UNPARSEABLE_TEXT` with `evidence_evaluated=false`.

## Evaluated editorial projection

The final public projection uses only records that completed the full-text evidence-reporting audit. It combines the already-public abstract/full-text priority with reporting coverage, applies a penalty for missing critical reporting signals, enforces per-journal caps, and round-robins across evidence paths.

Routes are:

- `FEATURED`: higher public editorial-attention priority after the full-text reporting audit;
- `EVIDENCE_RESERVE`: evaluated but outside the bounded featured target or journal cap;
- `LIMITED_REVIEW`: full text was acquired but machine-readable evidence evaluation could not be completed.

`FEATURED` is not an endorsement and is not a scientific quality grade.

## Public artifacts

The default Pages workflow publishes:

```text
abstract-acquisition.json/html
abstract-review.json/html
fulltext-fetch-plan.json
fulltext-acquisition.json/html
evidence-review-plan.json              # compatibility / provenance handoff
evidence-evaluation-policy.json
evidence-evaluation.json/html
evaluated-edition.json/html
```

The safe Actions artifact additionally carries hash-bound manifests and payload-disposition records. Abstract and full-text raw payloads are verified and deleted before any artifact upload. Publisher XML/PDF/text payloads are not committed to Git or placed in Pages.
