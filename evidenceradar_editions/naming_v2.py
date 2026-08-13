from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

ALLOWED_PERIOD_KINDS = ("auto", "day", "week", "month", "range")


@dataclass(frozen=True)
class EditionIdentity:
    journal_slug: str
    period_kind: str
    period_key: str
    period_label_zh_tw: str
    period_status: str
    period_complete: bool
    revision: int
    edition_key: str
    publication_id: str
    artifact_stem: str

    def to_dict(self) -> dict[str, object]:
        return {
            "journal_slug": self.journal_slug,
            "period_kind": self.period_kind,
            "period_key": self.period_key,
            "period_label_zh_tw": self.period_label_zh_tw,
            "period_status": self.period_status,
            "period_complete": self.period_complete,
            "revision": self.revision,
            "edition_key": self.edition_key,
            "publication_id": self.publication_id,
            "artifact_stem": self.artifact_stem,
        }


def _last_day_of_month(value: date) -> int:
    return calendar.monthrange(value.year, value.month)[1]


def _same_calendar_month(start: date, end: date) -> bool:
    return start.year == end.year and start.month == end.month


def _is_full_month(start: date, end: date) -> bool:
    return start.day == 1 and _same_calendar_month(start, end) and end.day == _last_day_of_month(start)


def _is_month_to_date(start: date, end: date) -> bool:
    return start.day == 1 and _same_calendar_month(start, end) and start <= end and end.day <= _last_day_of_month(start)


def infer_period_kind(start: date, end: date) -> str:
    if start == end:
        return "day"
    if _is_full_month(start, end):
        return "month"
    if start.weekday() == 0 and end == start + timedelta(days=6) and start.isocalendar()[:2] == end.isocalendar()[:2]:
        return "week"
    return "range"


def resolve_period_kind(start: date, end: date, requested: str = "auto") -> str:
    if requested not in ALLOWED_PERIOD_KINDS:
        raise ValueError(f"unsupported period kind: {requested}")
    inferred = infer_period_kind(start, end)
    if requested == "auto":
        return inferred
    if requested == "month" and _is_month_to_date(start, end):
        return "month"
    if requested != inferred and requested != "range":
        raise ValueError(f"period {start.isoformat()}..{end.isoformat()} is {inferred}, not {requested}")
    return requested


def period_key(start: date, end: date, kind: str) -> str:
    if kind == "day":
        return start.isoformat()
    if kind == "month":
        return f"{start.year:04d}-{start.month:02d}"
    if kind == "week":
        year, week, _ = start.isocalendar()
        return f"{year:04d}-W{week:02d}"
    return f"{start.isoformat()}--{end.isoformat()}"


def period_complete(start: date, end: date, kind: str) -> bool:
    return _is_full_month(start, end) if kind == "month" else True


def period_status(start: date, end: date, kind: str) -> str:
    return "MTD" if kind == "month" and not _is_full_month(start, end) else "FINAL"


def period_label_zh_tw(start: date, end: date, kind: str) -> str:
    if kind == "day":
        return f"{start.year} 年 {start.month} 月 {start.day} 日"
    if kind == "month":
        if _is_full_month(start, end):
            return f"{start.year} 年 {start.month} 月"
        return f"{start.year} 年 {start.month} 月（MTD 至 {end.month} 月 {end.day} 日）"
    if kind == "week":
        year, week, _ = start.isocalendar()
        return f"{year} 年第 {week} 週（{start.isoformat()} 至 {end.isoformat()}）"
    return f"{start.isoformat()} 至 {end.isoformat()}"


def build_identity(*, slug: str, start: date, end: date, period_kind_requested: str = "auto", revision: int = 1) -> EditionIdentity:
    if revision < 1 or revision > 9999:
        raise ValueError("revision must be between 1 and 9999")
    kind = resolve_period_kind(start, end, period_kind_requested)
    key = period_key(start, end, kind)
    complete = period_complete(start, end, kind)
    status = period_status(start, end, kind)
    edition_key = f"{slug}__{key}"
    publication_id = f"{edition_key}__r{revision:02d}"
    return EditionIdentity(
        journal_slug=slug,
        period_kind=kind,
        period_key=key,
        period_label_zh_tw=period_label_zh_tw(start, end, kind),
        period_status=status,
        period_complete=complete,
        revision=revision,
        edition_key=edition_key,
        publication_id=publication_id,
        artifact_stem=f"EvidenceRadar_Editions__{publication_id}",
    )
