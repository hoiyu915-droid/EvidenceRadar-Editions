# Abstract review → bounded full-text delivery

This stage deliberately spans more than one micro-step. It starts from the public 300-record `AbstractFetchPlan`, reacquires the planned abstracts in one ephemeral workflow, performs a deterministic structural abstract review, allocates a bounded full-text budget, attempts full-text acquisition, records a structural full-text audit, and only then deletes both payload vaults.

```text
up to 300 AbstractFetchPlan records
        ↓
live abstract acquisition
        ↓
hash-bound ephemeral abstract vault
        ↓
structural abstract review
        ↓
up to 120 FULLTEXT_NOW
        ↓
full-text acquisition
        ↓
structural full-text audit
        ↓
EvidenceReviewPlan (hashes + provenance only)
        ↓
delete abstract + full-text payload vaults
```

## Public scientific boundary

This pipeline contains two different kinds of review and they must not be conflated with evidence appraisal.

`abstract_reviewed=true`
: The acquired abstract bytes were hash-verified and a deterministic structural rule set inspected the text. The rule set detects things such as Methods/Results headings, explicit sample-size language, effect-estimate language, registration, multicentre/external-validation language, limitations, and data/code availability. It does **not** judge whether the claims are correct, clinically important, novel, or at low risk of bias.

`FULLTEXT_ACQUIRED`
: An allowed exact-source route returned full-text bytes and the payload was hash-bound. It does **not** mean the paper has passed an evidence review.

`EvidenceReviewPlan.READY`
: The full-text payload was acquired and structurally audited before deletion. It is a later evidence-review work queue, not an evidence-strength result.

Every full-text receipt remains `evidence_evaluated=false`.

## Full-text allocation

The default monthly full-text budget is 120 records from the abstracts actually acquired. Accessibility does not affect scientific priority: the abstract review chooses `FULLTEXT_NOW` before any full-text route is attempted.

The operational priority combines:

- the existing public pre-fetch evidence path;
- whether the record was a metric-independent `FETCH_CANDIDATE` or a metric-aware reserve admission;
- abstract structural information signals;
- a small field-normalized journal-metric adjustment already governed by the public shortlist;
- per-journal capacity and near-duplicate controls.

The score is explicitly an operational full-text-review priority, not a quality score.

## Full-text sources

### Europe PMC Open Access full-text XML

If the abstract receipt or original identifiers expose a PMCID, the first source is:

```text
https://www.ebi.ac.uk/europepmc/webservices/rest/<PMCID>/fullTextXML
```

Europe PMC documents this endpoint for the Open Access full-text subset. The returned XML is checked against planned PMCID/PMID/DOI identity before being accepted.

### Crossref open-license TDM links

If a DOI is available, Crossref metadata is queried for deposited full-text links. A link is attempted only when:

1. the Crossref record DOI exactly matches the planned DOI;
2. the metadata includes a recognized open-license URL (v1 uses Creative Commons hosts);
3. the link is explicitly marked `intended-application=text-mining`;
4. the content type is XML, plain text, or PDF.

The presence of a Crossref link alone does not imply access. Missing routes, access denial, not-found responses, and transport/parser failures remain separate terminal states.

## Payload governance

Abstract and full-text payloads are content-addressed in separate runner-temporary vaults. Before deletion:

- every abstract hash and size is verified;
- every acquired full-text hash and size is verified;
- structural review/audit artifacts are bound to the corresponding content hashes.

Before any safe Actions artifact or Pages artifact is uploaded, both vaults are deleted and the workflow asserts that neither path still exists.

Safe/public artifacts never contain abstract text, full-text bytes, raw source responses, or extracted full-text prose.

## Public artifacts

```text
/abstract-acquisition.json
/abstract-acquisition.html
/abstract-review.json
/abstract-review.html
/abstract-review-policy.json
/fulltext-fetch-plan.json
/fulltext-acquisition.json
/fulltext-acquisition.html
/evidence-review-plan.json
```

The safe Actions artifact additionally contains the two payload-disposition records and the binding manifest.
