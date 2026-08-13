from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .fileio import save_text
from .serialization import json_sha256, json_text
from .utils import safe_http_metadata_url, sha256_bytes, utc_now_iso

TRANSLATION_REQUEST_TYPE = "EvidenceRadar_Editions_TranslationRequest"
TRANSLATION_RESPONSE_TYPE = "EvidenceRadar_Editions_TranslationResponse"
ALLOWED_BASES = {"TITLE_ONLY", "METADATA", "ABSTRACT", "FULL_TEXT"}


class TranslationContractError(ValueError):
    pass


def _article_title(article: dict[str, Any]) -> str:
    return str(article.get("title_original") or article.get("title") or "").strip()


def _request_items(run: dict[str, Any]) -> list[dict[str, Any]]:
    articles = run.get("articles") or []
    if not isinstance(articles, list):
        raise TranslationContractError("edition articles must be a list")
    items: list[dict[str, Any]] = []
    for article in articles:
        if not isinstance(article, dict):
            raise TranslationContractError("edition article is not an object")
        canonical_id = str(article.get("canonical_id") or "").strip()
        title = _article_title(article)
        if not canonical_id or not title:
            raise TranslationContractError(
                "translation request article lacks identity or title"
            )
        items.append(
            {
                "canonical_id": canonical_id,
                "title_original": title,
                "publication_date": article.get("publication_date"),
                "publication_date_precision": article.get(
                    "publication_date_precision", "DAY"
                ),
                "authors": article.get("authors") or [],
                "identifiers": {
                    "doi": article.get("doi"),
                    "pmid": article.get("pmid"),
                    "pmcid": article.get("pmcid"),
                },
                "source_urls": article.get("urls") or [],
                "required_output": [
                    "title_zh_tw",
                    "summary_zh_tw",
                    "basis",
                    "source_url_when_basis_exceeds_title",
                ],
            }
        )
    return items


def _request_binding(run: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "artifact_type": TRANSLATION_REQUEST_TYPE,
        "edition_id": run.get("edition_id"),
        "language": "zh-TW",
        "source_edition_sha256": json_sha256(run),
        "items": items,
    }


def translation_request_sha256(run: dict[str, Any]) -> str:
    items = _request_items(run)
    return sha256_bytes(json_text(_request_binding(run, items)).encode("utf-8"))


def build_translation_request(run: dict[str, Any]) -> dict[str, Any]:
    items = _request_items(run)
    binding = _request_binding(run, items)
    request_sha = sha256_bytes(json_text(binding).encode("utf-8"))
    return {
        **binding,
        "request_id": f"{run.get('edition_id')}__zh-TW",
        "request_binding_sha256": request_sha,
        "created_at": utc_now_iso(),
        "instructions": {
            "title_zh_tw": "翻譯為台灣繁體中文的自然題名，保留必要縮寫與專有名詞。",
            "summary_zh_tw": (
                "寫成供讀者判斷是否值得點開原文的精簡繁中導讀。不得捏造研究設計、數字或結果。"
            ),
            "basis": (
                "只看題名時使用 TITLE_ONLY；實際讀取書目資料、摘要或全文時，"
                "才可分別使用 METADATA、ABSTRACT、FULL_TEXT。"
            ),
            "source_binding": (
                "basis 不是 TITLE_ONLY 時，必須提供 source_url，且該 URL 必須來自該篇文章的 source_urls。"
            ),
            "preserve_original_title": True,
            "medical_advice": False,
        },
        "item_count": len(items),
    }


def write_translation_request(run: dict[str, Any], path: Path) -> dict[str, Any]:
    request = build_translation_request(run)
    save_text(path, json_text(request))
    return request


def _validate_response_item(
    item: dict[str, Any],
) -> tuple[str, str, str, str, str | None]:
    canonical_id = str(item.get("canonical_id") or "").strip()
    title = str(item.get("title_zh_tw") or "").strip()
    summary = str(item.get("summary_zh_tw") or "").strip()
    basis = str(item.get("basis") or "").strip().upper()
    source_url = safe_http_metadata_url(
        str(item.get("source_url") or "").strip() or None
    )
    if not canonical_id:
        raise TranslationContractError("translation item lacks canonical_id")
    if not title:
        raise TranslationContractError(
            f"translation item lacks title_zh_tw: {canonical_id}"
        )
    if not summary:
        raise TranslationContractError(
            f"translation item lacks summary_zh_tw: {canonical_id}"
        )
    if len(title) > 500:
        raise TranslationContractError(f"translated title is too long: {canonical_id}")
    if len(summary) > 1200:
        raise TranslationContractError(
            f"translated summary is too long: {canonical_id}"
        )
    if basis not in ALLOWED_BASES:
        raise TranslationContractError(
            f"translation basis must be one of {sorted(ALLOWED_BASES)}: {canonical_id}"
        )
    if basis != "TITLE_ONLY" and source_url is None:
        raise TranslationContractError(
            f"translation basis {basis} requires source_url: {canonical_id}"
        )
    return canonical_id, title, summary, basis, source_url


def apply_translation_response(
    run: dict[str, Any],
    response: dict[str, Any],
    *,
    require_complete: bool = True,
) -> dict[str, Any]:
    if response.get("artifact_type") != TRANSLATION_RESPONSE_TYPE:
        raise TranslationContractError("unexpected translation response artifact_type")
    if response.get("edition_id") != run.get("edition_id"):
        raise TranslationContractError("translation response edition_id mismatch")
    if response.get("request_id") not in {
        None,
        f"{run.get('edition_id')}__zh-TW",
    }:
        raise TranslationContractError("translation response request_id mismatch")
    if response.get("language") != "zh-TW":
        raise TranslationContractError("translation response language must be zh-TW")
    expected_source_sha = json_sha256(run)
    if response.get("source_edition_sha256") != expected_source_sha:
        raise TranslationContractError(
            "translation response source edition hash mismatch"
        )
    expected_request_sha = translation_request_sha256(run)
    if response.get("request_binding_sha256") != expected_request_sha:
        raise TranslationContractError(
            "translation response request binding hash mismatch"
        )

    articles = run.get("articles") or []
    article_by_id = {
        str(article.get("canonical_id")): article
        for article in articles
        if isinstance(article, dict) and article.get("canonical_id")
    }
    items = response.get("items") or []
    if not isinstance(items, list):
        raise TranslationContractError("translation response items must be a list")
    if response.get("item_count") is not None and response.get("item_count") != len(
        items
    ):
        raise TranslationContractError("translation response item_count mismatch")
    translated: dict[str, tuple[str, str, str, str | None]] = {}
    for raw in items:
        if not isinstance(raw, dict):
            raise TranslationContractError(
                "translation response item must be an object"
            )
        canonical_id, title, summary, basis, source_url = _validate_response_item(
            raw
        )
        if canonical_id in translated:
            raise TranslationContractError(
                f"duplicate translation item: {canonical_id}"
            )
        article = article_by_id.get(canonical_id)
        if article is None:
            raise TranslationContractError(
                f"unknown translation item: {canonical_id}"
            )
        if source_url is not None:
            allowed_urls = {
                safe_http_metadata_url(str(value))
                for value in (article.get("urls") or [])
            }
            if source_url not in allowed_urls:
                raise TranslationContractError(
                    f"translation source_url is not bound to the article: {canonical_id}"
                )
        translated[canonical_id] = (title, summary, basis, source_url)

    missing = sorted(set(article_by_id) - set(translated))
    if require_complete and missing:
        raise TranslationContractError(
            f"translation response is incomplete; missing {len(missing)} article(s)"
        )

    enriched = copy.deepcopy(run)
    for article in enriched.get("articles") or []:
        canonical_id = str(article.get("canonical_id") or "")
        values = translated.get(canonical_id)
        if values is None:
            article["translation_status"] = "MISSING"
            continue
        title, summary, basis, source_url = values
        article["title_zh_tw"] = title
        article["summary_zh_tw"] = summary
        article["translation_basis"] = basis
        article["translation_source_url"] = source_url
        article["translation_status"] = "COMPLETE"

    total = len(article_by_id)
    translated_count = len(translated)
    response_sha = sha256_bytes(json_text(response).encode("utf-8"))
    status = (
        "NOT_REQUIRED"
        if total == 0
        else "COMPLETE"
        if translated_count == total
        else "PARTIAL"
    )
    enriched["translation"] = {
        "language": "zh-TW",
        "status": status,
        "translated_articles": translated_count,
        "total_articles": total,
        "source_edition_sha256": expected_source_sha,
        "request_binding_sha256": expected_request_sha,
        "response_sha256": response_sha,
        "response_generated_at": response.get("generated_at"),
    }
    enriched.setdefault("counts", {})["translated_articles"] = translated_count
    return enriched


def load_translation_response(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TranslationContractError(
            "translation response must be a JSON object"
        )
    return value
