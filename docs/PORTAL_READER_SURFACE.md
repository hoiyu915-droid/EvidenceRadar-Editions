# Reader-facing portal boundary

The GitHub Pages landing page is a discovery surface for journals and articles, not a pipeline status dashboard.

The reader-facing journal projection is:

```text
core journal registry
UNION
publisher-provider journals that already have a canonical published Edition
```

Provider discovery-only journals are excluded from the main portal until they have a canonical Edition. The provider catalog remains available as a separate discovery surface.

Abstract acquisition, abstract review, full-text acquisition, evidence evaluation, evaluated-edition, shortlist, and other provenance/audit artifacts remain published as dedicated HTML/JSON files. They do not accumulate banners on the landing page.

`portal-journals.json` is the machine-readable projection backing the main journal browser. `journals.json` remains the core registry and is not silently expanded by provider discovery metadata.
