# Security policy

## Supported branch

Security fixes target the current `main` branch.

## Data and network boundary

Default acquisition uses fixed public endpoints for PubMed, Europe PMC and Crossref. The `radar_rss` lane is provenance-only in v0.2 and does not fetch config-derived URLs.

Do not add code that silently uploads local documents, browser sessions, credentials, private user data, paid full text or publisher PDFs.

Generated HTML escapes provider metadata and is validated against canonical JSON. Do not replace this with raw provider HTML injection.

## Secrets

No API key is required for the default acquisition or translation handoff. Never commit API keys, cookies or tokens. Translation responses should contain only the required navigation text and provenance fields.

## Reports

Report vulnerabilities privately to the repository owner. Do not attach credentials or sensitive material to a public issue.
