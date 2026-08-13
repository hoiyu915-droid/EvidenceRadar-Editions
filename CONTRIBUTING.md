# Contributing

## Development setup

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
ruff check .
pytest
```

Run the deterministic delivery smoke test before opening a PR:

```bash
rm -rf outputs/fixture

evidenceradar-editions build \
  --collection config/collections/jama-network-open.yml \
  --start 2026-08-01 \
  --end 2026-08-31 \
  --fixture-dir tests/fixtures \
  --strict-sources \
  --output outputs/fixture

evidenceradar-editions validate outputs/fixture
python -m build
```

## Change rules

1. Keep direct source query, scope filtering, identity merge, rendering, manifest and validation as separate stages.
2. Never add a dependency on EvidenceRadar `artifacts/`, `runs/`, `state/` or published Pages output.
3. A new source adapter must emit a receipt that distinguishes `SUCCESS`, `NO_RESULTS` and `FAILED`.
4. Metadata must not be promoted to full-text access or verified scientific claims without a matching access／verification receipt.
5. Update fixtures and tests for parser changes. Fixtures must be synthetic or redistributable and must not contain paywalled text.
6. Changes to the pinned EvidenceRadar commit require the compatibility procedure in `docs/UPSTREAM_INTEGRATION.md`.
7. Generated delivery files are not hand-edited; modify canonical inputs or renderer and rebuild.

## Pull requests

Keep a PR focused. The description should state:

- affected contract or adapter;
- evidence that no Radar artifact dependency was introduced;
- tests and validator commands run;
- external API behavior that could not be exercised offline;
- license or third-party material implications.
