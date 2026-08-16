from __future__ import annotations

from . import pages_v4
from .pages_curation_v2 import enhance_revision_pages

# pages_v4 owns canonical revision materialization, but its curated revision
# renderer is resolved from this module global at build time. Replace only that
# Pages-facing projection; canonical edition JSON and immutable artifact HTML
# remain unchanged.
pages_v4.enhance_revision_pages = enhance_revision_pages

from .pages_v16 import build_pages_site

__all__ = ["build_pages_site"]
