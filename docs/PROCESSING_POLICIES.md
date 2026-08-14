# Volume-aware journal processing policies

`catalog/processing-policies.json` is the Editions control plane for journals whose publication volume is too high for one uniform workflow.

The policy is deliberately separate from `catalog/journals.json`:

- `journals.json` answers **what the publication container is**;
- `processing-policies.json` answers **how much automated work Editions may perform for it**.

Changing a processing mode does not change journal identity, evidence quality, or the scientific value of any article.

## The important boundary

The current PubMed, Europe PMC, Crossref and journal-specific adapters acquire **bibliographic metadata**. They do not download every publisher PDF and they do not perform full-text evidence evaluation.

Accordingly, the pipeline distinguishes these counts:

1. source-reported records;
2. metadata records returned under the per-source cap;
3. locally accepted and deduplicated canonical records;
4. records projected into the default Pages browser;
5. records receiving a later translation, commentary, abstract review or full-text audit.

A record that stops at steps 1–4 must never be described as full-text fetched, evidence evaluated or scientifically verified.

## Modes

| Mode | New metadata acquisition | Automatic translation handoff | Default Pages browser | Intended use |
| --- | --- | --- | --- | --- |
| `FULL` | Yes, under the configured per-source cap | Yes | All records up to the FULL browser limit | Normal-volume journals |
| `TRIAGE` | Yes, under a bounded cap | Deferred | Limited deterministic projection | High-volume journals that still need coverage |
| `INDEX_ONLY` | Yes, under a bounded cap | None | Small metadata projection | Discovery/catalog coverage without automatic editorial work |
| `SUSPENDED` | No | None | Historical editions remain available; their browser may still be projected | Temporarily stop future loading without deleting history |

`SUSPENDED` is a future-acquisition control. It does not erase or rewrite already published canonical editions.

## Automatic volume guard

A journal configured as `FULL` can be downgraded to effective `TRIAGE` for one run when a source reports more records than `auto_triage_threshold`.

The guard:

- clamps acquisition before the source adapter can consume an operator-supplied oversized budget;
- records both configured and effective modes in `edition.json`;
- changes automatic translation to `DEFERRED`;
- applies the TRIAGE Pages limit;
- never auto-suspends a journal;
- never calls the resulting subset “best,” “relevant,” or “high quality.”

Pages applies the same guard to already stored editions using the canonical article count. This prevents an edition with thousands of records from placing the whole article array in `browse.json`.

## Pages projection

The canonical `edition.json` remains complete. `browse.json` is a non-destructive browser projection:

```text
canonical edition.json: 4,397 records
Pages browse.json:         250 records
omitted from browser:    4,147 records
```

The omitted records remain in the canonical JSON. Projection order is the existing deterministic canonical article order. It is an operational capacity limit, not evidence scoring or editorial ranking.

The rendered page shows all three numbers and links to the complete canonical JSON. The root Pages catalog also publishes `processing-policies.json` and a machine-readable `volume_projection` summary.

## Editing the policy file

Example:

```json
{
  "journals": {
    "example-megajournal": {
      "mode": "TRIAGE",
      "source_record_limit": 500,
      "pages_record_limit": 250,
      "translation_mode": "DEFERRED",
      "note": "High-volume broad-scope source."
    },
    "temporarily-disabled-journal": {
      "mode": "SUSPENDED",
      "note": "Publisher date feed is currently unreliable."
    }
  }
}
```

Journal keys must be registered slugs. CI rejects unknown slugs, unsafe values, unsupported modes, invalid limits and a `SUSPENDED` mode with a non-zero source budget.

List policies:

```bash
python -m evidenceradar_editions journals --processing-mode TRIAGE
python -m evidenceradar_editions journals --processing-mode SUSPENDED
```

A normal registry-based run respects the policy automatically:

```bash
python -m evidenceradar_editions run \
  --journal-slug scientific-reports \
  --start 2026-08-01 \
  --end 2026-08-31 \
  --period-kind month \
  --output-dir work/scientific-reports-2026-08
```

A suspended run fails before any adapter is called. An exceptional operator override must be explicit:

```bash
python -m evidenceradar_editions run \
  --journal-slug temporarily-disabled-journal \
  --start 2026-08-01 \
  --end 2026-08-31 \
  --override-processing-policy \
  --output-dir work/override
```

The override is written into processing provenance. It is not silent.

## Publishing metadata-only modes

`TRIAGE` and `INDEX_ONLY` intentionally do not create an automatic all-article translation request. Their acquisition bundles still validate as metadata editions. Publishing them before later editorial enrichment is explicit:

```bash
python -m evidenceradar_editions publish \
  --bundle-dir work/example \
  --editions-root editions \
  --allow-untranslated

python -m evidenceradar_editions build-pages \
  --editions-root editions \
  --catalog-root catalog \
  --repository OWNER/REPO \
  --output-dir _site \
  --allow-untranslated
```

An operator can later run the explicit `translation-request` command for a chosen edition. Policy suppresses blanket automatic work; it does not make later review impossible.
