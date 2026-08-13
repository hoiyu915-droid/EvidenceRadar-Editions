# zh-TW Translation Contract

GitHub Actions does not require a private translation API. The acquisition runner emits a `TranslationRequest.zh-TW.json` that can be completed by ChatGPT Work or another authorized translator.

## Binding

The request contains `source_edition_sha256` plus `request_binding_sha256`, both calculated from deterministic JSON serialization. A response is rejected unless it carries the same edition ID, language, source SHA-256 and request-binding SHA-256.

This prevents a response generated for one retrieval from being silently applied to another retrieval of the same journal/period.

## Per-article output

Every item uses the canonical article ID and must include:

- `title_zh_tw`
- `summary_zh_tw`
- `basis`

Allowed `basis` values:

| Value | Meaning |
|---|---|
| `TITLE_ONLY` | Only the title was used. The summary must not state study findings. |
| `METADATA` | Bibliographic/index metadata was read. |
| `ABSTRACT` | The abstract was actually read. |
| `FULL_TEXT` | A full-text source was actually obtained and read. |

A public HTML report surfaces this basis. Translation is a navigation layer, not permission to fabricate a result or upgrade source access.

## Publication gate

`validate --require-zh-tw` requires every displayed article to have both a Traditional Chinese title and summary and requires the aggregate translation state to be `COMPLETE`.

## Source binding

When `basis` is `METADATA`, `ABSTRACT` or `FULL_TEXT`, the response must provide `source_url`, and that URL must already be bound to the same article in the canonical edition. `TITLE_ONLY` may omit it.

Translation request and response filenames inherit the edition self-describing stem so multiple journals and periods cannot collide in one directory.
