# Security policy

## Supported versions

The latest release and current `main` branch receive security fixes.

## Reporting

Please report security issues privately through GitHub's security-advisory interface for this repository. Do not include access tokens, private article content, session cookies or personal data in a public issue.

## Security boundaries

- Only public HTTP(S) endpoints are allowed; DNS results must be globally routable.
- Redirect targets are revalidated.
- Response bodies are size-bounded.
- Source queries use explicit time and journal scope, followed by local hard filtering.
- A Radar source checkout must match the pinned commit unless drift is explicitly allowed and recorded.
- Radar generated artifacts are prohibited inputs.
- Secrets are not required for the default adapters and must never be committed.
- Generated HTML escapes source text and only emits validated HTTP(S) links.

A successful build is not proof that a third-party source is complete or trustworthy. Source receipts and provenance exist so that such limitations stay visible.
