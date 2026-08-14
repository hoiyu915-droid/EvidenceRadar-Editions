from __future__ import annotations

from . import pages_v9
from .pages_v10 import build_pages_site as build_v10_pages_site
from .prefetch_triage_v3 import build_prefetch_triage

# pages_v10 supplies policy fallback and self-describing policy publication.
# Replace only the triage classifier/builder with the precision-hardened v3
# implementation; pages_v9 resolves this global at build time.
pages_v9.build_prefetch_triage = build_prefetch_triage
build_pages_site = build_v10_pages_site

__all__ = ["build_pages_site"]
