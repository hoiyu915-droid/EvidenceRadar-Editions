from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import quote

import requests
from defusedxml import ElementTree as ET

from .http import HttpClient
from .serialization import json_text
from .utils import clean_text, normalize_doi, utc_now_iso

PUBMED_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
EUROPE_PMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
CROSSREF_WORK = "https://api.crossref.org/works/{doi}"

RECEIPTS_FILENAME = "abstract-acquisition-receipts.json"
DISPOSITION_FILENAME = "abstract-payload-disposition.json"
MANIFEST_FILENAME = "abstract-acquisition-manifest.json"

SUPPORTED_SOURCES = {
    "PUBMED_PMID",
    "EUROPE_PMC_PMCID",
    "EUROPE_PMC_PMID",
    "EUROPE_PMC_DOI",
    "CROSSREF_DOI",
}

_FINAL_STATUSES = {
    "ABSTRACT_ACQUIRED",
    "ABSTRACT_NOT_PRESENT",
    "RECORD_NOT_FOUND",
    "ACQUISITION_INCONCLUSIVE",
    "SKIPPED_NO_IDENTIFIER",
}


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def _payload_digest(text: str) -> tuple[str, bytes]:
    payload = text.encode("utf-8")
    return hashlib.sha256(payload).hexdigest(), payload


def _sectioned_text(nodes: Iterable[Any]) -> str | None:
    parts: list[str] = []
    for node in nodes:
        text = clean_text("".join(node.itertext()))
        if not text:
            continue
        label = clean_text(node.attrib.get("Label") or node.attrib.get("NlmCategory") or "")
        if label and not text.casefold().startswith(label.casefold() + ":"):
            text = f"{label}: {text}"
        parts.append(text)
    merged = "\n\n".join(parts).strip()
    return merged or None


def parse_pubmed_abstracts(payload: bytes) -> dict[str, dict[str, Any]]:
    root = ET.fromstring(payload)
    out: dict[str, dict[str, Any]] = {}
    for article in root.findall(".//PubmedArticle"):
        citation = article.find("MedlineCitation")
        if citation is None:
            continue
        pmid_node = citation.find("PMID")
        pmid = clean_text("".join(pmid_node.itertext())) if pmid_node is not None else ""
        if not pmid:
            continue
        abstract = _sectioned_text(citation.findall("Article/Abstract/AbstractText"))
        doi = None
        pmcid = None
        for ident in article.findall("PubmedData/ArticleIdList/ArticleId"):
            kind = str(ident.attrib.get("IdType") or "").casefold()
            value = clean_text("".join(ident.itertext()))
            if kind == "doi":
                doi = normalize_doi(value)
            elif kind == "pmc":
                pmcid = value.upper() or None
        out[pmid] = {
            "record_found": True,
            "abstract": abstract,
            "pmid": pmid,
            "pmcid": pmcid,
            "doi": doi,
        }
    return out


def _europe_pmc_match(raw: Mapping[str, Any], *, kind: str, value: str) -> bool:
    if kind == "pmcid":
        return str(raw.get("pmcid") or "").strip().upper() == value.strip().upper()
    if kind == "pmid":
        return str(raw.get("pmid") or raw.get("id") or "").strip() == value.strip()
    if kind == "doi":
        return normalize_doi(str(raw.get("doi") or "")) == normalize_doi(value)
    return False


def parse_europe_pmc_result(payload: Mapping[str, Any], *, kind: str, value: str) -> dict[str, Any]:
    raw_results = ((payload.get("resultList") or {}).get("result") or [])
    if not isinstance(raw_results, list):
        raise ValueError("Europe PMC resultList.result must be an array")
    for raw in raw_results:
        if not isinstance(raw, Mapping) or not _europe_pmc_match(raw, kind=kind, value=value):
            continue
        abstract = clean_text(raw.get("abstractText")) or None
        return {
            "record_found": True,
            "abstract": abstract,
            "pmid": clean_text(raw.get("pmid") or raw.get("id")) or None,
            "pmcid": clean_text(raw.get("pmcid")).upper() or None,
            "doi": normalize_doi(str(raw.get("doi") or "")),
        }
    return {"record_found": False, "abstract": None}


def parse_crossref_result(payload: Mapping[str, Any], *, doi: str) -> dict[str, Any]:
    raw = payload.get("message")
    if not isinstance(raw, Mapping):
        raise ValueError("Crossref message must be an object")
    observed = normalize_doi(str(raw.get("DOI") or ""))
    expected = normalize_doi(doi)
    if observed != expected:
        return {"record_found": False, "abstract": None}
    abstract = clean_text(raw.get("abstract")) or None
    return {"record_found": True, "abstract": abstract, "doi": observed}


def validate_plan(plan: Mapping[str, Any], *, maximum_items: int = 300) -> dict[str, Any]:
    value = dict(plan)
    if value.get("artifact_type") != "EvidenceRadar_Editions_AbstractFetchPlan":
        raise ValueError("unexpected abstract fetch plan type")
    items = value.get("items")
    if not isinstance(items, list):
        raise ValueError("abstract fetch plan items must be an array")
    if int(value.get("item_count") or -1) != len(items):
        raise ValueError("abstract fetch plan item_count mismatch")
    if not 0 <= len(items) <= maximum_items:
        raise ValueError(f"abstract fetch plan exceeds maximum_items={maximum_items}")
    binding = str(value.get("plan_binding_sha256") or "")
    if len(binding) != 64:
        raise ValueError("abstract fetch plan binding is missing")
    keys: set[str] = set()
    for raw in items:
        if not isinstance(raw, Mapping):
            raise ValueError("abstract fetch plan item must be an object")
        key = str(raw.get("record_key") or "")
        if not key or key in keys:
            raise ValueError("abstract fetch plan record_key must be unique and non-empty")
        keys.add(key)
        if raw.get("status") != "PLANNED":
            raise ValueError(f"plan item is not PLANNED: {key}")
        for flag in ("abstract_fetch_requested", "abstract_acquired", "abstract_reviewed", "full_text_fetched", "evidence_evaluated"):
            if raw.get(flag) is not False:
                raise ValueError(f"plan item {key} has invalid {flag}")
        order = raw.get("source_order")
        if not isinstance(order, list) or any(str(x) not in SUPPORTED_SOURCES for x in order):
            raise ValueError(f"plan item {key} has unsupported source_order")
    return value


class AbstractAcquirer:
    def __init__(self, client: HttpClient | None = None, *, payload_dir: Path, crossref_mailto: str | None = None) -> None:
        self.client = client or HttpClient(timeout=20, response_limit=8 * 1024 * 1024)
        self.payload_dir = Path(payload_dir)
        self.payload_dir.mkdir(parents=True, exist_ok=True)
        self.crossref_mailto = str(crossref_mailto or "").strip() or None
        self.pubmed_cache: dict[str, dict[str, Any]] = {}
        self.pubmed_prefetch_error: str | None = None

    def prefetch_pubmed(self, items: Iterable[Mapping[str, Any]]) -> None:
        pmids = sorted({str((item.get("identifiers") or {}).get("pmid") or "").strip() for item in items if "PUBMED_PMID" in list(item.get("source_order") or []) and str((item.get("identifiers") or {}).get("pmid") or "").strip()})
        if not pmids:
            return
        try:
            for offset in range(0, len(pmids), 100):
                batch = pmids[offset : offset + 100]
                payload = self.client.get_bytes(PUBMED_EFETCH, params={"db": "pubmed", "id": ",".join(batch), "retmode": "xml", "tool": "EvidenceRadar-Editions"}, limit=8 * 1024 * 1024)
                self.pubmed_cache.update(parse_pubmed_abstracts(payload))
        except Exception as exc:
            self.pubmed_prefetch_error = f"{type(exc).__name__}: {exc}"

    def _write_payload(self, text: str) -> tuple[str, int, int]:
        digest, payload = _payload_digest(text)
        path = self.payload_dir / f"{digest}.txt"
        if path.exists():
            if path.read_bytes() != payload:
                raise ValueError("content-addressed abstract payload collision")
        else:
            path.write_bytes(payload)
        return digest, len(payload), len(text)

    def _pubmed(self, item: Mapping[str, Any]) -> dict[str, Any]:
        pmid = str((item.get("identifiers") or {}).get("pmid") or "").strip()
        if not pmid:
            return {"status": "NOT_APPLICABLE", "detail": "missing PMID"}
        found = self.pubmed_cache.get(pmid)
        if found:
            return {"status": "FOUND_WITH_ABSTRACT" if found.get("abstract") else "FOUND_NO_ABSTRACT", "record": found}
        if self.pubmed_prefetch_error:
            return {"status": "FAILED", "detail": self.pubmed_prefetch_error}
        return {"status": "NOT_FOUND"}

    def _europe_pmc(self, item: Mapping[str, Any], source: str) -> dict[str, Any]:
        identifiers = item.get("identifiers") or {}
        if source == "EUROPE_PMC_PMCID":
            kind, value = "pmcid", str(identifiers.get("pmcid") or "").strip()
        elif source == "EUROPE_PMC_PMID":
            kind, value = "pmid", str(identifiers.get("pmid") or "").strip()
        else:
            kind, value = "doi", str(identifiers.get("doi") or "").strip()
        if not value:
            return {"status": "NOT_APPLICABLE", "detail": f"missing {kind.upper()}"}
        query = f'DOI:"{value}"' if kind == "doi" else f"PMCID:{value}" if kind == "pmcid" else f"EXT_ID:{value} AND SRC:MED"
        try:
            payload = self.client.get_json(EUROPE_PMC_SEARCH, params={"query": query, "format": "json", "resultType": "core", "pageSize": 5}, limit=4 * 1024 * 1024)
            found = parse_europe_pmc_result(payload, kind=kind, value=value)
        except Exception as exc:
            return {"status": "FAILED", "detail": f"{type(exc).__name__}: {exc}"}
        if not found.get("record_found"):
            return {"status": "NOT_FOUND"}
        return {"status": "FOUND_WITH_ABSTRACT" if found.get("abstract") else "FOUND_NO_ABSTRACT", "record": found}

    def _crossref(self, item: Mapping[str, Any]) -> dict[str, Any]:
        doi = str((item.get("identifiers") or {}).get("doi") or "").strip()
        if not doi:
            return {"status": "NOT_APPLICABLE", "detail": "missing DOI"}
        try:
            params = {"mailto": self.crossref_mailto} if self.crossref_mailto else None
            payload = self.client.get_json(CROSSREF_WORK.format(doi=quote(doi, safe="/")), params=params, limit=4 * 1024 * 1024)
            found = parse_crossref_result(payload, doi=doi)
        except requests.HTTPError as exc:
            if getattr(exc.response, "status_code", None) == 404:
                return {"status": "NOT_FOUND"}
            return {"status": "FAILED", "detail": f"{type(exc).__name__}: {exc}"}
        except Exception as exc:
            return {"status": "FAILED", "detail": f"{type(exc).__name__}: {exc}"}
        if not found.get("record_found"):
            return {"status": "NOT_FOUND"}
        return {"status": "FOUND_WITH_ABSTRACT" if found.get("abstract") else "FOUND_NO_ABSTRACT", "record": found}

    def _attempt(self, item: Mapping[str, Any], source: str) -> dict[str, Any]:
        if source == "PUBMED_PMID":
            result = self._pubmed(item)
        elif source.startswith("EUROPE_PMC_"):
            result = self._europe_pmc(item, source)
        elif source == "CROSSREF_DOI":
            result = self._crossref(item)
        else:
            result = {"status": "FAILED", "detail": f"unsupported source {source}"}
        return {"source": source, **result}

    def acquire(self, item: Mapping[str, Any]) -> dict[str, Any]:
        attempts: list[dict[str, Any]] = []
        acquired: dict[str, Any] | None = None
        for source in item.get("source_order") or []:
            attempt = self._attempt(item, str(source))
            record = attempt.pop("record", None)
            attempts.append(attempt)
            if attempt["status"] == "FOUND_WITH_ABSTRACT" and record:
                acquired = {"source": str(source), **record}
                break
        has_failure = any(x["status"] == "FAILED" for x in attempts)
        has_no_abstract = any(x["status"] == "FOUND_NO_ABSTRACT" for x in attempts)
        meaningful = [x for x in attempts if x["status"] != "NOT_APPLICABLE"]
        if acquired:
            status = "ABSTRACT_ACQUIRED"
        elif not meaningful:
            status = "SKIPPED_NO_IDENTIFIER"
        elif has_failure:
            status = "ACQUISITION_INCONCLUSIVE"
        elif has_no_abstract:
            status = "ABSTRACT_NOT_PRESENT"
        else:
            status = "RECORD_NOT_FOUND"
        receipt = {
            "ordinal": int(item.get("ordinal") or 0), "record_key": item.get("record_key"), "canonical_id": item.get("canonical_id"),
            "journal": item.get("journal"), "journal_slug": item.get("journal_slug"), "period_key": item.get("period_key"), "revision": item.get("revision"),
            "title_original": item.get("title_original"), "identifiers": dict(item.get("identifiers") or {}), "planned_source_order": list(item.get("source_order") or []),
            "status": status, "attempts": attempts, "acquired_source": acquired.get("source") if acquired else None, "source_record_id": None, "source_url": None,
            "abstract_sha256": None, "abstract_bytes": 0, "abstract_characters": 0, "abstract_fetch_requested": True, "abstract_acquired": bool(acquired),
            "abstract_reviewed": False, "full_text_fetched": False, "evidence_evaluated": False,
        }
        if acquired:
            if acquired.get("pmcid"):
                receipt["source_record_id"] = acquired["pmcid"]
            elif acquired.get("pmid"):
                receipt["source_record_id"] = acquired["pmid"]
            else:
                receipt["source_record_id"] = acquired.get("doi")
            if acquired["source"] == "PUBMED_PMID" and acquired.get("pmid"):
                receipt["source_url"] = f"https://pubmed.ncbi.nlm.nih.gov/{acquired['pmid']}/"
            elif acquired["source"] == "EUROPE_PMC_PMCID" and acquired.get("pmcid"):
                receipt["source_url"] = f"https://europepmc.org/article/PMC/{acquired['pmcid']}"
            elif acquired["source"].startswith("EUROPE_PMC_") and acquired.get("pmid"):
                receipt["source_url"] = f"https://europepmc.org/article/MED/{acquired['pmid']}"
            elif acquired.get("doi"):
                receipt["source_url"] = f"https://doi.org/{acquired['doi']}"
            digest, byte_count, char_count = self._write_payload(str(acquired["abstract"]))
            receipt["abstract_sha256"] = digest
            receipt["abstract_bytes"] = byte_count
            receipt["abstract_characters"] = char_count
        return receipt


def acquire_plan(plan: Mapping[str, Any], *, payload_dir: Path, client: HttpClient | None = None, maximum_items: int = 300, generated_at: str | None = None, crossref_mailto: str | None = None) -> dict[str, Any]:
    validated = validate_plan(plan, maximum_items=maximum_items)
    acquirer = AbstractAcquirer(client, payload_dir=payload_dir, crossref_mailto=crossref_mailto)
    acquirer.prefetch_pubmed(validated["items"])
    receipts = [acquirer.acquire(item) for item in validated["items"]]
    if len(receipts) != len(validated["items"]):
        raise ValueError("receipt count differs from plan item count")
    if [x["record_key"] for x in receipts] != [x["record_key"] for x in validated["items"]]:
        raise ValueError("receipt ordering differs from plan")
    counts = Counter(str(x["status"]) for x in receipts)
    source_counts = Counter(str(x["acquired_source"]) for x in receipts if x.get("acquired_source"))
    if any(status not in _FINAL_STATUSES for status in counts):
        raise ValueError("unexpected final acquisition status")
    receipt_binding = _digest({"plan_binding_sha256": validated["plan_binding_sha256"], "items": [{"record_key": x["record_key"], "status": x["status"], "attempts": x["attempts"], "acquired_source": x["acquired_source"], "source_record_id": x["source_record_id"], "abstract_sha256": x["abstract_sha256"], "abstract_bytes": x["abstract_bytes"], "abstract_characters": x["abstract_characters"]} for x in receipts]})
    return {
        "schema_version": "1.0", "artifact_type": "EvidenceRadar_Editions_AbstractAcquisitionReceipts", "generated_at": generated_at or utc_now_iso(),
        "plan_binding_sha256": validated["plan_binding_sha256"], "receipt_binding_sha256": receipt_binding, "plan_item_count": len(validated["items"]), "receipt_count": len(receipts),
        "counts": {"abstract_acquired": counts["ABSTRACT_ACQUIRED"], "abstract_not_present": counts["ABSTRACT_NOT_PRESENT"], "record_not_found": counts["RECORD_NOT_FOUND"], "acquisition_inconclusive": counts["ACQUISITION_INCONCLUSIVE"], "skipped_no_identifier": counts["SKIPPED_NO_IDENTIFIER"], "by_status": dict(sorted(counts.items())), "by_acquired_source": dict(sorted(source_counts.items()))},
        "scientific_boundary": "ABSTRACT_ACQUIRED means an exact planned identifier returned abstract text. No abstract has been reviewed and no evidence-quality claim is made.",
        "payload_policy": {"storage": "EPHEMERAL_CONTENT_ADDRESSED_VAULT", "public_receipts_contain_abstract_text": False, "delete_before_artifact_upload": True},
        "items": receipts,
    }


def validate_payload_vault(receipts: Mapping[str, Any], payload_dir: Path) -> dict[str, Any]:
    payload_root = Path(payload_dir)
    expected: dict[str, tuple[int, int]] = {}
    for item in receipts.get("items") or []:
        if item.get("status") != "ABSTRACT_ACQUIRED":
            continue
        digest = str(item.get("abstract_sha256") or "")
        if len(digest) != 64:
            raise ValueError("acquired receipt is missing abstract_sha256")
        expected[digest] = (int(item.get("abstract_bytes") or 0), int(item.get("abstract_characters") or 0))
    actual_files = sorted(payload_root.glob("*.txt")) if payload_root.exists() else []
    actual_names = {path.stem for path in actual_files}
    if actual_names != set(expected):
        raise ValueError("payload vault content set does not match acquired receipts")
    for path in actual_files:
        payload = path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if digest != path.stem:
            raise ValueError(f"payload hash mismatch: {path.name}")
        byte_count, char_count = expected[digest]
        text = payload.decode("utf-8")
        if len(payload) != byte_count or len(text) != char_count:
            raise ValueError(f"payload size mismatch: {path.name}")
    return {"payload_object_count": len(actual_files), "payload_bytes": sum(path.stat().st_size for path in actual_files)}


def delete_payload_vault(payload_dir: Path) -> None:
    root = Path(payload_dir)
    if root.exists():
        if root.is_symlink() or not root.is_dir():
            raise ValueError("payload vault path is unsafe")
        shutil.rmtree(root)


__all__ = ["DISPOSITION_FILENAME", "MANIFEST_FILENAME", "RECEIPTS_FILENAME", "SUPPORTED_SOURCES", "AbstractAcquirer", "acquire_plan", "delete_payload_vault", "parse_crossref_result", "parse_europe_pmc_result", "parse_pubmed_abstracts", "validate_payload_vault", "validate_plan"]
