# Architecture

## Boundary

EvidenceRadar-Editions owns scoped acquisition, period identity, edition rendering, translation handoff, archive publication and Pages indexing.

EvidenceRadar remains the reference source/config producer. Editions may read a pinned `config/radar_master.json` to discover journal-specific source IDs and feed hints, but it must not ingest EvidenceRadar result artifacts as its corpus.

```text
Pinned EvidenceRadar source/config ── hints/provenance ──┐
                                                         │
Public bibliographic endpoints ── direct query ──────────┤
                                                         ▼
                                              canonical edition data
                                                         │
                                      hash-bound zh-TW enrichment
                                                         │
                         ┌───────────────────────────────┴──────────────┐
                         ▼                                              ▼
                standalone interactive HTML                immutable archive + Pages
```

## Primary identities

The human-facing ontology is:

```text
journal × period × revision
```

A run timestamp is provenance, not the primary browsing key.

Examples:

```text
jama-network-open × 2026-08 × r01
bjsm × 2026-W33 × r02
sports-medicine × 2026-08-01--2026-08-14 × r01
```

## Data layers

1. **Acquisition:** fixed public adapters query the requested period.
2. **Scope enforcement:** every source result is checked locally against journal/ISSN and inclusive publication dates. DAY/MONTH/YEAR precision is preserved and matched by interval overlap.
3. **Identity reconciliation:** DOI, PMID, PMCID, then normalized title/date fingerprint.
4. **Canonical edition JSON:** the source of truth for renderer and archive.
5. **Translation handoff:** response binds the exact source JSON SHA-256.
6. **Renderer:** self-contained zh-Hant HTML with filters; no independent substantive claims.
7. **Validator:** checks identity, exact source receipts, truncation/run status, scope, translation coverage/provenance, hashes and JSON→HTML byte parity.
8. **Archive:** append-only journal/period/revision directories.
9. **Pages:** derives catalog and article search index from validated archive entries.

## Publication invariant

`publish` requires complete zh-TW content by default. A caller can explicitly allow untranslated bundles for development, but Pages production should not.

An existing archive revision is immutable. Changed bytes require a new revision number.
