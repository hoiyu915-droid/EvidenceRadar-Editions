from __future__ import annotations

import json
from pathlib import Path

from .bundle import HTML_NAME, JSON_NAME, MANIFEST_NAME
from .utils import normalize_doi


def validate_bundle(root: Path) -> list[str]:
    errors: list[str] = []
    json_path = root / JSON_NAME
    html_path = root / HTML_NAME
    manifest_path = root / MANIFEST_NAME
    for path in (json_path, html_path, manifest_path):
        if not path.is_file():
            errors.append(f"missing artifact: {path.name}")
    if errors:
        return errors
    try:
        run = json.loads(json_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"bundle parse failed: {exc}"]
    if run.get("upstream_radar", {}).get("uses_radar_output_artifacts") is not False:
        errors.append("Radar output artifacts must not be an Editions input")
    articles = run.get("articles") or []
    if run.get("counts", {}).get("articles") != len(articles):
        errors.append("article count mismatch")
    ids = [a.get("canonical_id") for a in articles]
    if len(ids) != len(set(ids)):
        errors.append("duplicate canonical IDs")
    scope = run.get("scope") or {}
    start = str(scope.get("start_date") or "")
    end = str(scope.get("end_date") or "")
    for article in articles:
        published = str(article.get("publication_date") or "")
        if not (start <= published <= end):
            errors.append(f"article outside period: {article.get('canonical_id')}")
        doi = article.get("doi")
        if doi and normalize_doi(doi) != doi:
            errors.append(f"DOI is not normalized: {doi}")
    if manifest.get("edition_id") != run.get("edition_id"):
        errors.append("manifest edition id mismatch")
    if manifest.get("article_count") != len(articles):
        errors.append("manifest article count mismatch")
    return errors
