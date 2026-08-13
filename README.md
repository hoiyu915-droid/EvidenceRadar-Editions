# EvidenceRadar-Editions

Scoped journal/date reconstruction and HTML publication rendering beside EvidenceRadar — without consuming EvidenceRadar result artifacts.

## Purpose

EvidenceRadar-Editions accepts a journal plus an inclusive publication-date range, queries public bibliographic sources directly, reconciles duplicate records, and emits a reproducible edition bundle.

The architecture is deliberately different from “Radar output → monthly renderer”:

```text
EvidenceRadar source/config definitions      Public bibliographic APIs
                 │                                      │
                 └──────── source hints ───────┐         │
                                               ▼         ▼
                                      EvidenceRadar-Editions
                                               │
                                    strict journal/date scope
                                               │
                                      identity reconciliation
                                               │
                                  JSON + HTML + manifest
```

`EvidenceRadar-Editions` does **not** ingest `EvidenceRadar_Report.html`, `EvidenceRadar_Run.json`, `EvidenceRadar_Evidence.json`, `EvidenceRadar_State.json`, Work Packs, or previous Radar result bundles as its publication corpus.

## Upstream reference

v0.1 is designed against:

- repository: `hoiyu915-droid/EvidenceRadar`
- commit: `6da659df845e4b76072dae016120ca76ed9c27c4`
- control plane: `config/radar_master.json`

When `--radar-root` is supplied, Editions reads the upstream source configuration to identify matching source IDs and feed hints and records the configuration SHA-256. Publication records are still queried from source APIs during the Editions run.

For safety, v0.1 records config-derived RSS/Atom feed hints but does not request those dynamic URLs. The active acquisition lanes are PubMed, Europe PMC and Crossref.

## Historical reconstruction semantics

An edition generated today for `2025-01-01 → 2025-01-31` means:

> current-source reconstruction of the historical publication window

It does not claim to reproduce what EvidenceRadar had observed on 2025-01-31. Bibliographic metadata, indexing, PMCID assignment, DOI metadata and source state may have changed since that period. The bundle records `retrieved_at`, source checks, the Radar reference commit/config hash, and output hashes.

## Install

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

Python 3.11+ is supported.

## Build a scoped edition

```sh
evidenceradar-editions run \
  --journal "JAMA Network Open" \
  --issn 2574-3805 \
  --slug jama-network-open \
  --start 2026-08-01 \
  --end 2026-08-31 \
  --radar-root ../EvidenceRadar \
  --radar-commit 6da659df845e4b76072dae016120ca76ed9c27c4 \
  --output-dir dist/jama-network-open/2026-08
```

The slug is fail-closed: lowercase ASCII letters, digits and internal hyphens only, 1–80 characters. Date ranges and source names are validated before acquisition.

## Output contract

Each successful run emits:

```text
EvidenceRadar_Edition.json
EvidenceRadar_Edition.html
EvidenceRadar_Edition.manifest.json
```

The JSON file is the canonical structured edition. HTML is rendered deterministically from that object. The manifest records the edition ID, software version, upstream Radar commit, article count, byte sizes and SHA-256 values for the JSON and HTML files.

Validate an edition with:

```sh
evidenceradar-editions validate --bundle-dir dist/jama-network-open/2026-08
```

Validation checks the no-Radar-output-artifact boundary, record counts, unique canonical IDs, publication-window membership, DOI normalization, manifest identity/counts, byte sizes and SHA-256 integrity.

## Source lanes

- **PubMed:** journal/ISSN plus publication-date query; ESearch followed by batched EFetch XML.
- **Europe PMC:** journal query bounded by `FIRST_PDATE`, with cursor pagination.
- **Crossref:** fixed `/works` endpoint, publication-date/type filters, optional ISSN filter, and cursor pagination.
- **Radar feed hint:** provenance-only in v0.1; config-derived feed URLs are not fetched.

Every acquired record is post-filtered against the requested journal and inclusive publication window before it enters the edition. Identity reconciliation prefers DOI, then PMID, then PMCID, then normalized title plus publication date.

## Evidence boundary

This is a bibliographic edition/reconstruction tool, not a substitute for EvidenceRadar claim verification. A record appearing in a bibliographic source does not establish that full text was read or that a scientific claim was verified. v0.1 does not generate free-form “important finding” summaries from discovery metadata.

## Tests and CI

```sh
python -m unittest discover -s tests -v
python -m evidenceradar_editions --help
```

GitHub Actions runs the test suite on Python 3.11, 3.12 and 3.13 for pull requests and `main`.

## Open source

The repository follows EvidenceRadar's two-layer licensing boundary:

- Apache-2.0 for executable source code, tests, validators, executable configuration and automation unless otherwise noted;
- CC BY 4.0 for original documentation and original report layout/arrangement unless otherwise noted.

Third-party bibliographic material is not relicensed. See [`docs/OPEN_SOURCE.md`](docs/OPEN_SOURCE.md), [`NOTICE.md`](NOTICE.md), and [`LICENSE-CONTENT.md`](LICENSE-CONTENT.md).
