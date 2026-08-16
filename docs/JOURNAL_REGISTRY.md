# Journal registry and catalog UI

`catalog/journals.json` is the local journal identity registry for EvidenceRadar Editions.

It is intentionally independent from the generated `editions/` tree. The registry stores journal identity and acquisition defaults (name, slug, ISSN, publisher, categories, OA mode, status and direct source adapters). It may record the EvidenceRadar snapshot from which a journal was imported, but normal Editions runs do not need to read EvidenceRadar again.

Operational volume controls live separately in `catalog/processing-policies.json`. Keeping identity and workload policy apart lets a journal move between `FULL`, `TRIAGE`, `INDEX_ONLY` and `SUSPENDED` without rewriting its canonical identity or historical editions. See [`PROCESSING_POLICIES.md`](PROCESSING_POLICIES.md).

## Use without EvidenceRadar

List the local registry:

```bash
python -m evidenceradar_editions journals --enabled-only
python -m evidenceradar_editions journals --category llm_research
python -m evidenceradar_editions journals --publisher Elsevier
python -m evidenceradar_editions journals --processing-mode TRIAGE
python -m evidenceradar_editions journals --processing-mode SUSPENDED
```

Each returned journal includes its resolved processing policy and provenance.

Build an edition from the registry:

```bash
python -m evidenceradar_editions run \
  --journal-slug jama-network-open \
  --start 2026-08-01 \
  --end 2026-08-14 \
  --period-kind month \
  --output-dir work/jama-2026-08
```

`--journal-slug` resolves the journal name, ISSN, canonical slug and direct acquisition sources from `catalog/journals.json`, then applies the workload limits from `catalog/processing-policies.json`. `--radar-root` remains optional and is only needed when an explicit Radar-side hint or provenance lookup is desired.

A journal in `SUSPENDED` mode fails before source acquisition. `--override-processing-policy` is an explicit, provenance-recorded escape hatch for exceptional operator work.

## Publisher providers

Publisher providers expose a selectable journal catalog without vendoring the publisher's whole journal universe into `catalog/journals.json`.

Cambridge Core fully open-access journals are available through the `cambridge` provider:

```bash
python -m evidenceradar_editions journals --provider cambridge
```

The provider catalog is lightweight journal metadata. To build an edition, select one journal by its Cambridge Core slug:

```bash
python -m evidenceradar_editions run \
  --provider cambridge \
  --journal-slug ai-edam \
  --start 2026-08-01 \
  --end 2026-08-31 \
  --period-kind month \
  --output-dir work/ai-edam-2026-08
```

A slug-selected run resolves that journal directly and traverses only that journal's Cambridge Core open-access article listing. It does not scan article pages for sibling Cambridge journals. The provider fails closed when the selected journal page is hybrid (`Contains open access`) rather than a fully open-access journal.

An exact `--journal` title may be used instead of `--journal-slug`; that convenience path first searches the lightweight provider catalog, so the slug form is preferred for direct selection.

Provider journals use the normal Editions processing-policy defaults unless they also have a local registry/policy entry. Provider identity and acquisition remain separate from the generated `editions/` publication store.

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

The Pages build also publishes `/journals.json` as the machine-readable identity registry and `/processing-policies.json` as the workload control plane. `index.json` remains the publication catalog and `search-index.json` remains the article-level search index.

For high-volume editions, revision-level `browse.json` is a bounded Pages projection rather than a duplicate of every canonical article object. The page states the canonical, projected and omitted counts. Omitted records remain in the complete canonical `edition.json`; the projection does not claim quality or relevance ranking.

## Updating the registry

Synchronizing new journals from EvidenceRadar is a deliberate maintenance action, not a runtime dependency. When syncing:

1. pin the EvidenceRadar commit and control-plane config;
2. import only publication containers that have a stable journal identity;
3. keep indexes, repositories, subject feeds and bounded-verification backends out of the journal registry;
4. preserve Editions-native journals that are not currently configured in Radar;
5. validate unique slugs and direct acquisition sources before publishing;
6. add a processing-policy override only when operational evidence supports it;
7. use `SUSPENDED` for future acquisition control, never to erase historical publications.
