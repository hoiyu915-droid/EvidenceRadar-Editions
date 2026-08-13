# Publishing and GitHub Pages

## Canonical storage

Production publication data lives under `editions/`, not `archive/`.

Monthly editions use:

```text
editions/<journal-slug>/<YYYY>/<MM>/r<revision>/
  edition.json
  manifest.json
  storage.json
```

Day, week and arbitrary-range editions are sharded below the same journal/year tree without competing with calendar-month directories:

```text
editions/<journal>/<YYYY>/<MM>/days/<DD>/rXX/
editions/<journal>/<ISO-YYYY>/weeks/Wxx/rXX/
editions/<journal>/<YYYY>/ranges/<period-key>/rXX/
```

The canonical store deliberately does **not** keep HTML. `edition.json` is the content source of truth and `manifest.json` preserves the validated bundle hashes, including the deterministic HTML hash. `storage.json` records the storage policy.

## Revision policy

- Same revision + same canonical bytes: idempotent.
- Same revision + different bytes: fail closed.
- Reconstructed or corrected edition with different bytes: increment revision.
- MTD and month-end FINAL builds remain the same logical `YYYY-MM` period and use different revisions.

## Pages build

Pages renders HTML from canonical JSON during the workflow. It materializes a temporary compatibility bundle only inside the runner, then builds the public navigation surface:

```text
_site/
  index.html
  index.json
  search-index.json
  links.json
  journals/<journal>/index.html
  journals/<journal>/<period>/index.html
  journals/<journal>/<period>/rXX/index.html
```

The root page is the journal master table. A journal page lists months/periods; the period page lists immutable revisions; the revision page is the interactive report.

The repository never commits `_site`, generated HTML, ZIP downloads, or duplicate self-describing aliases into `editions/`. Download-friendly filenames exist only in generated bundles / Pages output / release assets.

## Journal registry

`catalog/journals.json` is the lightweight tracked-journal registry. It is small metadata, not a copy of the publication corpus.

## Legacy compatibility

The v0.2 `archive/` API remains available only when a caller explicitly passes `--archive-root`. Production CLI and Pages default to `--editions-root editions`.

## Deployment

Repository Settings → Pages → Build and deployment must use **GitHub Actions**. The workflow itself does not attempt to modify that repository setting. Once enabled, `.github/workflows/pages.yml` validates the store, rebuilds HTML from JSON and deploys the static site.
