# EvidenceRadar source integration

## Purpose

EvidenceRadar Editions is intentionally a separate application. It may reuse narrow, source-side helpers from a compatible EvidenceRadar checkout instead of copying those helpers and letting them drift.

The initial bridge uses `tools/network_safety.py` for:

- public HTTP(S) URL validation;
- bounded response text/bytes.

The allowlist also names `config/radar_master.json` and `tools/publisher_feed.py` for planned compatible source reuse, but v0.1.0 does not implicitly execute them.

## Pin

`config/upstream-radar.json` records the public repository copy. The same bytes are packaged at `evidenceradar_editions/data/upstream-radar.json`, so an installed wheel keeps the pin and fail-closed behavior without relying on the source checkout layout. CI rejects drift between the two copies.

It records:

- upstream repository;
- exact 40-character commit;
- allowed source paths;
- prohibited output roots;
- `artifacts_consumed=false`.

`inspect-upstream` checks the Git commit, required paths and Apache-2.0 license. It rejects drift by default.

## Prohibited dependency

The following upstream roots must not become input paths:

```text
artifacts/
runs/
state/
public/
```

This includes current bundles, old daily reports, Pages history, State ledgers and release output. Editions must be reconstructable by querying its configured external sources directly.

## Pin upgrade procedure

1. Identify the desired upstream commit and review all allowlisted files between old and new pins.
2. Check license and notice changes.
3. Run `inspect-upstream` against the new checkout before changing the pin.
4. Run all fixture tests and delivery validation.
5. Execute one non-publishing live edition for a bounded journal/date range.
6. Compare source receipts, inclusion/exclusion counts, canonical IDs and HTML parity.
7. Update `config/upstream-radar.json`, documentation and changelog in one PR.
8. Do not use `--allow-radar-drift` as a release shortcut.

## When to extract a shared core

A third repository is not required merely because two applications share concepts. A shared package becomes justified when at least two consumers need the same stable, tested API and independent pins create measurable maintenance cost. Until then, the source bridge remains narrow and explicit.
