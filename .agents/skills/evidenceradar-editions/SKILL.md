---
name: evidence-radar-editions
description: Build and validate a journal edition for an explicit publication-date range without consuming EvidenceRadar generated artifacts.
---

# EvidenceRadar Editions

Read `README.md`, `docs/EDITION_CONTRACT.md`, `docs/SOURCE_ADAPTERS.md`, `docs/UPSTREAM_INTEGRATION.md`, the selected collection YAML and `config/upstream-radar.json` before changing or running the project.

## Execution contract

1. Resolve one collection profile and an inclusive `start`／`end` date.
2. Query configured primary bibliographic sources directly.
3. Preserve one receipt per source with `SUCCESS`, `NO_RESULTS` or `FAILED`.
4. Apply local journal／ISSN, date and article-type filtering.
5. Deduplicate by shared DOI, PMID, PMCID or title fallback identity.
6. Generate `index.html`, `edition.json`, `sources.json` and `manifest.json` together.
7. Run `evidenceradar-editions validate` before delivery.

Never use EvidenceRadar `artifacts/`, `runs/`, `state/` or Pages output as an Editions input. A pinned EvidenceRadar checkout may be used only for allowlisted source-side helpers, and its observed commit must be written into provenance.

Do not interpret metadata or abstracts as verified scientific claims. Do not mark full text accessible without a direct access receipt. Do not publish publisher PDFs or paywalled text.
