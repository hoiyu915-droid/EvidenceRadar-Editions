# Contributing

Contributions are welcome when they preserve the central boundary: Editions may reuse EvidenceRadar source/config semantics but must not silently convert upstream output artifacts into its corpus.

Before opening a pull request:

```sh
python -m compileall -q evidenceradar_editions tests
python -m unittest discover -s tests -v
python -m evidenceradar_editions --help
```

Source-adapter changes need network-free fixtures covering query construction, parsing, failure state and post-fetch scope enforcement.

Renderer or publication changes must preserve canonical JSON→HTML byte parity and update validators/tests for new invariants. Do not weaken a validation rule merely to pass malformed output.

Code or text adapted from EvidenceRadar or another project must preserve applicable license and NOTICE obligations.
