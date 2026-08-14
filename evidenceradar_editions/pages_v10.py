from __future__ import annotations

from . import pages_v9
from .prefetch_triage_v2 import build_prefetch_triage

# Keep v9's Pages orchestration while replacing its triage builder with the
# bounded portfolio-index implementation. Full per-edition triage audits remain
# unchanged and complete.
pages_v9.build_prefetch_triage = build_prefetch_triage
build_pages_site = pages_v9.build_pages_site

__all__ = ["build_pages_site"]
