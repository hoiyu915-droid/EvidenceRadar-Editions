# Provider catalog snapshots

Files in this directory are static discovery snapshots produced by publisher adapters for the public GitHub Pages portal.

They are deliberately separate from `catalog/journals.json`:

- `catalog/journals.json` is the local Editions journal identity registry.
- `catalog/providers/*.json` lists journals currently exposed for selection by a publisher provider.
- Appearing in a provider snapshot does **not** mean that a journal is locally registered, already has an Edition, or will be acquired automatically.
- Runtime provider acquisition remains journal-scoped. Selecting `cambridge > <journal-slug>` resolves and fetches only that journal.

## Cambridge

Refresh the Cambridge fully-open-access snapshot from Cambridge Core with:

```bash
python scripts/refresh_cambridge_provider_catalog.py
```

The Cambridge adapter accepts only Cambridge's primary result-title links (`class="part-link"`) and fails closed unless the unique journal count reconciles with Cambridge's declared result count. Related journals and supplementary-volume links embedded in result cards are not separate provider catalog identities.

The public Pages build projects this snapshot to:

```text
/providers/
/providers.json
/providers/cambridge/
/providers/cambridge.json
```

The static snapshot is for discovery and navigation. The live provider adapter remains the authority used when a user actually asks Editions to build a journal.
