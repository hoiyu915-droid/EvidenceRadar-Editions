# Retrospective reindex of existing editions

The volume-aware policy applies to both future acquisition and already-published canonical editions.

A retrospective reindex does **not** rewrite immutable `editions/**/edition.json` files. Instead, every Pages deployment rebuilds the presentation/search layer from the current processing policy:

1. discover the highest revision for each journal/period;
2. resolve the journal's `FULL`, `TRIAGE`, `INDEX_ONLY` or `SUSPENDED` policy;
3. apply the same volume guard used by revision-level browsing;
4. build a bounded `browse.json` for each latest revision;
5. rebuild the root `search-index.json` from those projected records only;
6. expose canonical, projected and omitted counts in `index.json`, `links.json` and `search-index.json`.

This closes an important scaling loophole: a large edition can no longer be reduced to 250 records on its own revision page and then silently expanded back to thousands of records in the global search payload.

The complete bibliographic archive remains in each canonical edition JSON. A record omitted from the default browser/search payload is not deleted, rejected, down-ranked scientifically or marked irrelevant. The projection is an operational capacity control only.

For example, a 4,397-record latest edition under the default volume guard contributes 250 records to the default global search index and keeps the remaining 4,147 in canonical storage.
