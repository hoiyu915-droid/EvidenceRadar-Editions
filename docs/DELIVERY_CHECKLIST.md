# Delivery checklist

## Code and configuration

- [ ] Collection profile validates and uses exact journal identities.
- [ ] Date range is explicit, inclusive and recorded.
- [ ] Source selection is explicit or inherited from the collection.
- [ ] Upstream Radar pin is exact when the source bridge is used.
- [ ] No path under Radar `artifacts/`, `runs/`, `state/` or `public/` is consumed.
- [ ] No secret, cookie, private data, publisher PDF or paywalled full text is present.

## Test gates

- [ ] `ruff check .`
- [ ] `pytest`
- [ ] Deterministic fixture edition builds.
- [ ] `evidenceradar-editions validate <fixture-output>` passes.
- [ ] `python -m build` creates wheel and sdist.

## Live-run gates

- [ ] Every configured source has one receipt.
- [ ] Failures are `FAILED`, not `NO_RESULTS`.
- [ ] Local hard filter counts are plausible and reviewed.
- [ ] Canonical IDs are unique.
- [ ] `status=PARTIAL` or `FAILED` is visible when appropriate.
- [ ] Historical semantics state current-source reconstruction.
- [ ] HTML opens without external assets and supports mobile search/filter.

## Handoff

- [ ] Deliver all four files together.
- [ ] Do not hand-edit one artifact after validation.
- [ ] Preserve `manifest.json` alongside the report.
- [ ] Record repository commit or release tag outside the bundle when publishing.
