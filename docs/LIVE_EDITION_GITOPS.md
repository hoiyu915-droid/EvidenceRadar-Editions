# Live Edition GitOps entrypoint

EvidenceRadar Editions has two equivalent production entrypoints for a scoped live Edition:

1. GitHub Actions `workflow_dispatch` on **Build and publish a live scoped edition**.
2. A reviewed update to `catalog/live-edition-request.json` on `main`.

The GitOps file exists so public operation does not depend on an operator clicking an Actions form. A request change is ordinary repository history: it is reviewable, diffable, attributable, and can be reproduced later.

```json
{
  "artifact_type": "EvidenceRadar_Editions_LiveEditionRequest",
  "request_id": "example",
  "journal_slug": "jama-network-open",
  "start": "2026-08-14",
  "end": "2026-08-14",
  "period_kind": "day",
  "revision": 1,
  "max_records": "",
  "sources": "",
  "allow_planned": false,
  "override_processing_policy": false
}
```

The workflow validates ISO dates, positive revision/budget values and the allowed period-kind vocabulary before source acquisition.

## Terminal behavior

A valid request does not stop at an Actions bundle:

```text
request
→ live source acquisition
→ bundle validation
→ canonical `editions/` publication
→ canonical-store validation
→ exact-path staging only
→ guarded publication to `main`
→ explicit `pages.yml` workflow_dispatch
→ wait for the exact downstream main SHA
→ default 300-abstract / 120-fulltext evidence lane
→ deterministic full-text evidence-reporting audit
→ evaluated editorial projection
→ safe artifact + Pages deployment
```

The preferred publication route is a generated pull request with an expected-head-SHA squash merge. Some repositories disable pull-request creation for `GITHUB_TOKEN`; in that specific permission failure only, the workflow may use `DIRECT_FAST_FORWARD_FALLBACK`. The fallback is guarded by the exact pre-acquisition `main` SHA and refuses to run if `main` moved. Unrelated paths cannot be staged.

The downstream Pages workflow is explicitly dispatched because GitHub intentionally suppresses most recursive workflow triggers caused by `GITHUB_TOKEN`. The live workflow resolves the downstream run by the exact canonical main SHA and waits for it to succeed.

## Scientific boundary

Completing the terminal workflow does not convert automation into peer review. `evidence_evaluated=true` means the documented deterministic reporting checklist ran on hash-verified machine-readable full text. Formal risk-of-bias, causal validity, effect magnitude interpretation, clinical importance and recommendation strength are not claimed by this lane.

Raw abstract/full-text payloads remain ephemeral. They are hash-verified and deleted before safe Actions/Page artifacts are uploaded.
