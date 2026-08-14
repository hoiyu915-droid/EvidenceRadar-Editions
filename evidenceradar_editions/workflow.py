from __future__ import annotations

from .bundle import write_bundle
from .engine_v2 import build_run
from .translation import write_translation_request
from .validate import validate_bundle
from .workflow_v2 import RADAR_PIN, run_workflow


def main() -> int:
    return run_workflow(
        build_run=build_run,
        write_bundle=write_bundle,
        write_translation_request=write_translation_request,
        validate_bundle=validate_bundle,
    )


if __name__ == "__main__":
    raise SystemExit(main())
