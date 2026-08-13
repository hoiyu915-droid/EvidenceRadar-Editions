from __future__ import annotations

from xml.etree import ElementTree as ET
from typing import Any


def _node(parent: ET.Element, tag: str, text: Any = None, **attrs: str) -> ET.Element:
    node = ET.SubElement(parent, tag, attrs)
    if text is not None:
        node.text = str(text)
    return node


def render_html(run: dict[str, Any]) -> str:
    scope = run["scope"]
    root = ET.Element("html", {"lang": "en"})
    head = _node(root, "head")
    _node(head, "meta", charset="utf-8")
    _node(head, "title", scope["journal"])
    body = _node(root, "body", **{"data-edition-id": run["edition_id"]})
    main = _node(body, "main")
    _node(main, "h1", scope["journal"])
    _node(main, "p", f"{scope['start_date']} to {scope['end_date']}")
    _node(main, "p", "Current public-source reconstruction of the historical publication window; not a replay of past Radar observations.")
    upstream = run["upstream_radar"]
    _node(main, "p", f"Retrieved {run['retrieved_at']}; Radar reference {upstream.get('commit') or 'not pinned'}")
    _node(main, "h2", "Source coverage")
    checks = _node(main, "ul")
    for check in run["source_checks"]:
        _node(checks, "li", f"{check['source']}: {check['status']} — returned {check['returned_count']}, accepted {check['accepted_count']}")
    _node(main, "h2", "Articles")
    for article in run["articles"]:
        card = _node(main, "article", **{"class": "paper", "data-canonical-id": article["canonical_id"]})
        _node(card, "p", article["publication_date"])
        _node(card, "h3", article["title"])
        _node(card, "p", article["journal"])
        identifiers = [f"DOI {article['doi']}" if article.get("doi") else "", f"PMID {article['pmid']}" if article.get("pmid") else "", f"PMCID {article['pmcid']}" if article.get("pmcid") else ""]
        _node(card, "p", " · ".join(v for v in identifiers if v))
    if not run["articles"]:
        _node(main, "p", "No matching articles.")
    return "<!doctype html>\n" + ET.tostring(root, encoding="unicode", method="html") + "\n"
