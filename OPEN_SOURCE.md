# Open-source statement

EvidenceRadar Editions is published as an auditable reference implementation for scoped journal reconstruction.

## License map

| Material | License |
|---|---|
| Python source, validators, schemas, tests, workflows, executable config, agent skill | Apache License 2.0 |
| Original documentation, report prose/layout, original selection and arrangement | Creative Commons Attribution 4.0 |
| Third-party bibliographic facts, abstracts, identifiers and linked source material | Not relicensed; original terms apply |

Contributions are accepted under the license applicable to the file being changed. By submitting a contribution, a contributor represents that they have the right to submit it and agrees that it may be distributed under that existing project license. No separate contributor license agreement is currently required.

## Reuse of EvidenceRadar source

The project may dynamically import allowlisted, commit-pinned helper code from EvidenceRadar under Apache-2.0. The pin and allowlist are public in `config/upstream-radar.json`. Editions records both expected and observed commit in provenance and refuses unexpected drift by default.

No EvidenceRadar generated artifact is an input to the Editions pipeline. This keeps two questions separate:

- source code reuse and compatible governance;
- publication data provenance for a specific edition.

## Reproducibility promise

A deliverable edition binds:

- collection configuration hash;
- inclusive publication-date range;
- source names and exact query receipts;
- retrieval timestamp;
- upstream source pin, when used;
- canonical article IDs;
- byte size and SHA-256 for every delivered artifact.

This makes a build explainable and tamper-evident. It does not promise that third-party databases will return identical records forever.
