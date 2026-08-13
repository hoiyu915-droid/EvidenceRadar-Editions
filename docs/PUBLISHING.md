# Publishing and GitHub Pages

## Archive layout

Published bundles are copied into:

```text
archive/journals/<journal-slug>/<period-key>/r<revision>/
```

Each directory contains clean static aliases (`index.html`, `edition.json`, `manifest.json`) and self-describing download filenames.

## Revision policy

- Same revision + same bytes: idempotent.
- Same revision + different bytes: fail.
- Reconstructed or corrected edition with different bytes: increment revision.

The stable period URL lists every revision and identifies the highest revision as latest; it does not erase or silently redirect away the revision history.

## Portal indexes

The Pages builder derives, rather than hand-edits:

- `index.json`: journal/period/revision catalog.
- `search-index.json`: article title, DOI, PMID and edition URL.
- `links.json`: public base and machine-readable endpoints.

The root page lists all available editions and offers client-side filters. Article search loads `search-index.json` only after the reader enters a query.

## Deployment

The Pages workflow validates archive entries before copying any file. It uses the repository archive as publication input, not expiring GitHub Actions artifacts.
