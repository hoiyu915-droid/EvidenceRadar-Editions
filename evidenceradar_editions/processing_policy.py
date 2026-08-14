from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Mapping

ALLOWED_PROCESSING_MODES = ("FULL", "TRIAGE", "INDEX_ONLY", "SUSPENDED")
ALLOWED_TRANSLATION_MODES = ("ALL", "DEFERRED", "NONE")
POLICY_FILENAME = "processing-policies.json"

_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?$")

_BUILTIN_MODE_DEFAULTS: dict[str, dict[str, Any]] = {
    "FULL": {
        "source_record_limit": 500,
        "pages_record_limit": 1000,
        "auto_triage_threshold": 1000,
        "triage_pages_record_limit": 250,
        "translation_mode": "ALL",
    },
    "TRIAGE": {
        "source_record_limit": 500,
        "pages_record_limit": 250,
        "auto_triage_threshold": None,
        "triage_pages_record_limit": 250,
        "translation_mode": "DEFERRED",
    },
    "INDEX_ONLY": {
        "source_record_limit": 500,
        "pages_record_limit": 100,
        "auto_triage_threshold": None,
        "triage_pages_record_limit": 100,
        "translation_mode": "NONE",
    },
    "SUSPENDED": {
        "source_record_limit": 0,
        "pages_record_limit": 100,
        "auto_triage_threshold": None,
        "triage_pages_record_limit": 100,
        "translation_mode": "NONE",
    },
}


class ProcessingPolicyError(ValueError):
    """Raised when a journal processing policy is invalid."""


class JournalSuspendedError(ProcessingPolicyError):
    """Raised before network acquisition for a suspended journal."""


@dataclass(frozen=True)
class JournalProcessingPolicy:
    journal_slug: str
    configured_mode: str
    effective_mode: str
    source_record_limit: int
    pages_record_limit: int
    auto_triage_threshold: int | None
    triage_pages_record_limit: int
    translation_mode: str
    note: str | None = None
    policy_source: str = "builtin_default"
    volume_guard_triggered: bool = False
    source_reported_total_max: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "journal_slug": self.journal_slug,
            "configured_mode": self.configured_mode,
            "effective_mode": self.effective_mode,
            "source_record_limit": self.source_record_limit,
            "pages_record_limit": self.pages_record_limit,
            "auto_triage_threshold": self.auto_triage_threshold,
            "triage_pages_record_limit": self.triage_pages_record_limit,
            "translation_mode": self.translation_mode,
            "note": self.note,
            "policy_source": self.policy_source,
            "volume_guard_triggered": self.volume_guard_triggered,
            "source_reported_total_max": self.source_reported_total_max,
        }


def _safe_slug(value: Any) -> str:
    slug = str(value or "").strip()
    if not _SLUG_RE.fullmatch(slug):
        raise ProcessingPolicyError(f"unsafe journal slug in processing policy: {slug!r}")
    return slug


def _mode(value: Any) -> str:
    mode = str(value or "").strip().upper()
    if mode not in ALLOWED_PROCESSING_MODES:
        raise ProcessingPolicyError(
            f"processing mode must be one of {ALLOWED_PROCESSING_MODES}: {mode!r}"
        )
    return mode


def _translation_mode(value: Any) -> str:
    mode = str(value or "").strip().upper()
    if mode not in ALLOWED_TRANSLATION_MODES:
        raise ProcessingPolicyError(
            f"translation mode must be one of {ALLOWED_TRANSLATION_MODES}: {mode!r}"
        )
    return mode


def _integer(
    value: Any,
    *,
    name: str,
    minimum: int,
    maximum: int,
    allow_none: bool = False,
) -> int | None:
    if value is None and allow_none:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ProcessingPolicyError(f"{name} must be an integer") from exc
    if not (minimum <= parsed <= maximum):
        raise ProcessingPolicyError(
            f"{name} must be between {minimum} and {maximum}: {parsed}"
        )
    return parsed


def _object(value: Any, *, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ProcessingPolicyError(f"{name} must be a JSON object")
    return dict(value)


def _builtin_catalog() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "artifact_type": "EvidenceRadar_Editions_ProcessingPolicies",
        "defaults": {"mode": "FULL"},
        "mode_defaults": {
            key: dict(value) for key, value in _BUILTIN_MODE_DEFAULTS.items()
        },
        "journals": {},
    }


def validate_policy_catalog(value: Mapping[str, Any]) -> dict[str, Any]:
    catalog = dict(value)
    if catalog.get("artifact_type") not in {
        None,
        "EvidenceRadar_Editions_ProcessingPolicies",
    }:
        raise ProcessingPolicyError("unexpected processing policy artifact_type")

    defaults = _object(catalog.get("defaults"), name="processing policy defaults")
    default_mode = _mode(defaults.get("mode") or "FULL")

    raw_mode_defaults = _object(
        catalog.get("mode_defaults"), name="processing policy mode_defaults"
    )
    mode_defaults: dict[str, dict[str, Any]] = {}
    for mode in ALLOWED_PROCESSING_MODES:
        merged = dict(_BUILTIN_MODE_DEFAULTS[mode])
        raw = _object(raw_mode_defaults.get(mode), name=f"mode_defaults.{mode}")
        unknown = set(raw) - {
            "source_record_limit",
            "pages_record_limit",
            "auto_triage_threshold",
            "triage_pages_record_limit",
            "translation_mode",
        }
        if unknown:
            raise ProcessingPolicyError(
                f"mode_defaults.{mode} has unknown fields: {sorted(unknown)}"
            )
        merged.update(raw)
        source_minimum = 0 if mode == "SUSPENDED" else 1
        source_limit = _integer(
            merged.get("source_record_limit"),
            name=f"mode_defaults.{mode}.source_record_limit",
            minimum=source_minimum,
            maximum=5000,
        )
        if mode == "SUSPENDED" and source_limit != 0:
            raise ProcessingPolicyError(
                "mode_defaults.SUSPENDED.source_record_limit must be 0"
            )
        mode_defaults[mode] = {
            "source_record_limit": source_limit,
            "pages_record_limit": _integer(
                merged.get("pages_record_limit"),
                name=f"mode_defaults.{mode}.pages_record_limit",
                minimum=0,
                maximum=5000,
            ),
            "auto_triage_threshold": _integer(
                merged.get("auto_triage_threshold"),
                name=f"mode_defaults.{mode}.auto_triage_threshold",
                minimum=1,
                maximum=1_000_000,
                allow_none=True,
            ),
            "triage_pages_record_limit": _integer(
                merged.get("triage_pages_record_limit"),
                name=f"mode_defaults.{mode}.triage_pages_record_limit",
                minimum=0,
                maximum=5000,
            ),
            "translation_mode": _translation_mode(
                merged.get("translation_mode")
            ),
        }

    raw_journals = _object(catalog.get("journals"), name="processing policy journals")
    journals: dict[str, dict[str, Any]] = {}
    for raw_slug, raw_policy in raw_journals.items():
        slug = _safe_slug(raw_slug)
        item = _object(raw_policy, name=f"journals.{slug}")
        unknown = set(item) - {
            "mode",
            "source_record_limit",
            "pages_record_limit",
            "auto_triage_threshold",
            "triage_pages_record_limit",
            "translation_mode",
            "note",
        }
        if unknown:
            raise ProcessingPolicyError(
                f"journals.{slug} has unknown fields: {sorted(unknown)}"
            )
        if item.get("mode") is not None:
            item["mode"] = _mode(item["mode"])
        if item.get("translation_mode") is not None:
            item["translation_mode"] = _translation_mode(item["translation_mode"])
        for key, minimum, maximum in (
            ("source_record_limit", 0, 5000),
            ("pages_record_limit", 0, 5000),
            ("triage_pages_record_limit", 0, 5000),
        ):
            if item.get(key) is not None:
                item[key] = _integer(
                    item[key],
                    name=f"journals.{slug}.{key}",
                    minimum=minimum,
                    maximum=maximum,
                )
        if "auto_triage_threshold" in item:
            item["auto_triage_threshold"] = _integer(
                item.get("auto_triage_threshold"),
                name=f"journals.{slug}.auto_triage_threshold",
                minimum=1,
                maximum=1_000_000,
                allow_none=True,
            )
        if (
            item.get("mode") == "SUSPENDED"
            and item.get("source_record_limit") not in {None, 0}
        ):
            raise ProcessingPolicyError(
                f"journals.{slug}.source_record_limit must be 0 in SUSPENDED mode"
            )
        if item.get("note") is not None:
            note = str(item["note"]).strip()
            item["note"] = note or None
        journals[slug] = item

    return {
        "schema_version": str(catalog.get("schema_version") or "1.0"),
        "artifact_type": "EvidenceRadar_Editions_ProcessingPolicies",
        "defaults": {"mode": default_mode},
        "mode_defaults": mode_defaults,
        "journals": journals,
    }


def load_processing_policy_catalog(
    catalog_root: Path | str = Path("catalog"),
) -> dict[str, Any]:
    path = Path(catalog_root) / POLICY_FILENAME
    if not path.is_file():
        return validate_policy_catalog(_builtin_catalog())
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ProcessingPolicyError("processing policy catalog must be a JSON object")
    return validate_policy_catalog(value)


def policy_for_slug(
    slug: str,
    *,
    catalog_root: Path | str = Path("catalog"),
    catalog: Mapping[str, Any] | None = None,
) -> JournalProcessingPolicy:
    safe_slug = _safe_slug(slug)
    policy_catalog = (
        validate_policy_catalog(catalog)
        if catalog is not None
        else load_processing_policy_catalog(catalog_root)
    )
    default_mode = _mode((policy_catalog.get("defaults") or {}).get("mode") or "FULL")
    override = dict((policy_catalog.get("journals") or {}).get(safe_slug) or {})
    configured_mode = _mode(override.pop("mode", default_mode))
    mode_defaults = dict(
        (policy_catalog.get("mode_defaults") or {}).get(configured_mode)
        or _BUILTIN_MODE_DEFAULTS[configured_mode]
    )
    note = override.pop("note", None)
    mode_defaults.update(override)

    source_limit = int(mode_defaults["source_record_limit"])
    if configured_mode == "SUSPENDED":
        if source_limit != 0:
            raise ProcessingPolicyError(
                f"journals.{safe_slug}.source_record_limit must be 0 in SUSPENDED mode"
            )
        source_limit = 0
    elif source_limit < 1:
        raise ProcessingPolicyError(
            f"non-suspended journal {safe_slug} requires source_record_limit >= 1"
        )

    policy_source = (
        f"{POLICY_FILENAME}:journals.{safe_slug}"
        if safe_slug in (policy_catalog.get("journals") or {})
        else f"{POLICY_FILENAME}:defaults"
    )
    return JournalProcessingPolicy(
        journal_slug=safe_slug,
        configured_mode=configured_mode,
        effective_mode=configured_mode,
        source_record_limit=source_limit,
        pages_record_limit=int(mode_defaults["pages_record_limit"]),
        auto_triage_threshold=(
            int(mode_defaults["auto_triage_threshold"])
            if mode_defaults.get("auto_triage_threshold") is not None
            else None
        ),
        triage_pages_record_limit=int(mode_defaults["triage_pages_record_limit"]),
        translation_mode=_translation_mode(mode_defaults["translation_mode"]),
        note=str(note).strip() if note else None,
        policy_source=policy_source,
    )


def validate_policy_journal_references(
    journal_slugs: Iterable[str],
    *,
    catalog_root: Path | str = Path("catalog"),
    catalog: Mapping[str, Any] | None = None,
) -> None:
    known = {_safe_slug(value) for value in journal_slugs}
    policy_catalog = (
        validate_policy_catalog(catalog)
        if catalog is not None
        else load_processing_policy_catalog(catalog_root)
    )
    unknown = sorted(set(policy_catalog.get("journals") or {}) - known)
    if unknown:
        raise ProcessingPolicyError(
            f"processing policy references unregistered journals: {unknown}"
        )


def apply_volume_guard(
    policy: JournalProcessingPolicy,
    source_checks: Iterable[Mapping[str, Any]] | None = None,
    *,
    observed_total: int | None = None,
) -> JournalProcessingPolicy:
    totals: list[int] = []
    if observed_total is not None:
        totals.append(max(0, int(observed_total)))
    for check in source_checks or ():
        value = check.get("total_available")
        if value is None:
            continue
        try:
            totals.append(max(0, int(value)))
        except (TypeError, ValueError):
            continue
    total_max = max(totals) if totals else None
    updated = replace(policy, source_reported_total_max=total_max)
    threshold = policy.auto_triage_threshold
    if (
        policy.effective_mode == "FULL"
        and threshold is not None
        and total_max is not None
        and total_max > threshold
    ):
        return replace(
            updated,
            effective_mode="TRIAGE",
            pages_record_limit=min(
                policy.pages_record_limit,
                policy.triage_pages_record_limit,
            ),
            translation_mode="DEFERRED",
            volume_guard_triggered=True,
        )
    return updated


def allow_suspended_override(
    policy: JournalProcessingPolicy,
) -> JournalProcessingPolicy:
    if policy.configured_mode != "SUSPENDED":
        return policy
    full = _BUILTIN_MODE_DEFAULTS["FULL"]
    return replace(
        policy,
        effective_mode="FULL",
        source_record_limit=int(full["source_record_limit"]),
        pages_record_limit=int(full["pages_record_limit"]),
        auto_triage_threshold=int(full["auto_triage_threshold"]),
        triage_pages_record_limit=int(full["triage_pages_record_limit"]),
        translation_mode=str(full["translation_mode"]),
        volume_guard_triggered=False,
        source_reported_total_max=None,
    )


def ensure_load_allowed(
    policy: JournalProcessingPolicy,
    *,
    allow_override: bool = False,
) -> JournalProcessingPolicy:
    if policy.configured_mode != "SUSPENDED":
        return policy
    if not allow_override:
        reason = f" ({policy.note})" if policy.note else ""
        raise JournalSuspendedError(
            f"journal is SUSPENDED by {policy.policy_source}: {policy.journal_slug}{reason}"
        )
    return allow_suspended_override(policy)
