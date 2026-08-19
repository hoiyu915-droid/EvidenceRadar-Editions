# Cambridge incremental backfill operator note

## Catalog boundary

Cambridge discovery lives in `catalog/providers/cambridge.json`, not in the core
`catalog/journals.json` registry. Do not copy provider journals into the core
registry, the August coverage checklist, or the completion checklist merely to
make an incremental run resolve them.

Only Cambridge journals that already have a validated immutable monthly Edition
are eligible for incremental backfill. Provider-catalog discovery by itself is
not a canonical base.

## Required request and grouping

`catalog/backfill-request.json` must declare `"provider": "cambridge"`. The
incremental resolver loads the validated Cambridge provider snapshot and checks
that the requested provider agrees with the provider recorded by the immutable
base Edition.

One batch has one acquisition window and one target revision. Group journals
only when all of these are identical:

- latest canonical base period end;
- latest canonical base revision;
- acquisition start, which must be exactly one day after the base end;
- target revision, which must be the base revision plus one.

For example, an `r01` ending August 16 targets `r02` with acquisition beginning
August 17. A journal already at `r02` ending August 16 must be a separate `r03`
batch even though its missing-date window is also August 17 onward.

## Known failure and fix

Workflow run
[`32251954959`](https://github.com/hoiyu915-droid/EvidenceRadar-Editions/actions/runs/32251954959)
failed before acquisition with `journal is not registered: ai-edam`. The live
Edition path understood provider journals, but the incremental path resolved
only the core registry. No canonical publication was written by that failed
run.

PR [`#50`](https://github.com/hoiyu915-droid/EvidenceRadar-Editions/pull/50)
added provider-aware incremental resolution. Unknown providers, provider/base
identity mismatches, inactive provider records, source-access gaps, and partial
source coverage still fail closed.

## Publication verification

After merging the request:

1. require successful live acquisition and canonical validation for every
   journal in the receipt;
2. require the generated full-snapshot revision and receipt on `main`;
3. require the Pages workflow to deploy the exact generated `main` SHA;
4. fetch each public revision HTML, `edition.json`, and `manifest.json` and
   verify HTTP 200, period end, revision, article count, and run status;
5. confirm the protected checklist/catalog files remain byte-identical.
