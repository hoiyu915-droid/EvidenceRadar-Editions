from __future__ import annotations

from . import pages_v9, prefetch_triage, prefetch_triage_v2
from .prefetch_triage_v2 import build_prefetch_triage
from .triage_policy_defaults import load_triage_policy

# Pages may be built from a lightweight temporary journal catalog that does not
# copy every optional policy file. Keep both triage layers on the same validated
# built-in fallback rather than disabling triage or mutating the caller catalog.
prefetch_triage.load_triage_policy = load_triage_policy
prefetch_triage_v2.load_triage_policy = load_triage_policy
pages_v9.build_prefetch_triage = build_prefetch_triage
build_pages_site = pages_v9.build_pages_site

__all__ = ["build_pages_site"]
