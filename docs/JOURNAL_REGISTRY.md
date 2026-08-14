# Journal registry and catalog UI

`catalog/journals.json` is the local journal identity registry for EvidenceRadar Editions.

It is intentionally independent from the generated `editions/` tree. The registry stores journal identity and acquisition defaults (name, slug, ISSN, publisher, categories, OA mode, status and direct source adapters). It may record the EvidenceRadar snapshot from which a journal was imported, but normal Editions runs do not need to read EvidenceRadar again.

## Use without EvidenceRadar

List the local registry:

```bash
python -m evidenceradar_editions journals --enabled-only
python -m evidenceradar_editions journals --category llm_research
python -m evidenceradar_editions journals --publisher Elsevier
```

Build an edition from the registry:

```bash
python -m evidenceradar_editions run \
  --journal-slug jama-network-open \
  --start 2026-08-01 \
  --end 2026-08-14 \
  --period-kind month \
  --output-dir work/jama-2026-08
```

`--journal-slug` resolves the journal name, ISSN, canonical slug and direct acquisition sources from `catalog/journals.json`. `--radar-root` remains optional and is only needed when an explicit Radar-side hint or provenance lookup is desired.

## Pages information architecture

The public portal treats classification as a view, not as URL identity.

The root catalog supports:

- journal / ISSN / article text search;
- domain/category shortcuts;
- publisher filtering;
- month filtering;
- publication-state filtering (selected month has content, no content, any edition, planned);
- OA-mode filtering;
- A–Z shortcuts.

Canonical URLs remain stable:

```text
/journals/<journal-slug>/
/journals/<journal-slug>/<period-key>/
/journals/<journal-slug>/<period-key>/rXX/
```

A registered journal without a published edition receives a lightweight placeholder journal page. When its first edition is published, the generated journal page replaces that placeholder without changing the journal URL.

The Pages build also publishes `/journals.json` as the machine-readable registry. `index.json` remains the publication catalog and `search-index.json` remains the article-level search index.

## Updating the registry

Synchronizing new journals from EvidenceRadar is a deliberate maintenance action, not a runtime dependency. When syncing:

1. pin the EvidenceRadar commit and control-plane config;
2. import only publication containers that have a stable journal identity;
3. keep indexes, repositories, subject feeds and bounded-verification backends out of the journal registry;
4. preserve Editions-native journals that are not currently configured in Radar;
5. validate unique slugs and direct acquisition sources before publishing.
