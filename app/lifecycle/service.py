"""Record lifecycle service layer — module 10.

Full spec: docs/modules/10-record-lifecycle.md

recompute_lifecycle() and next_recheck_due() are pure functions, implemented
for real (§8). Re-fetch execution, diffing, withdrawn detection, and
reopening-watch persistence need module 05/16 (DB, fetch) — stubbed.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from dateutil.relativedelta import relativedelta

from app.extraction.schema import DeadlineType, GrantRecord, LifecycleStatus, ReviewStatus
from app.lifecycle.schema import (
    CLOSING_SOON_WINDOW_DAYS,
    RECHECK_CADENCE_DAYS_CLOSING_SOON,
    RECHECK_CADENCE_DAYS_DEFAULT,
    RECHECK_CADENCE_DAYS_UNKNOWN,
    REOPENING_WATCH_MONTHS_AFTER_CLOSE,
    ReopeningWatch,
)


def recompute_lifecycle(record: GrantRecord, withdrawn_signal: bool = False,
                         as_of: date | None = None) -> LifecycleStatus:
    as_of = as_of or datetime.now().astimezone().date()
    if record.deadline_type == DeadlineType.UNKNOWN_UNSPECIFIED:
        return LifecycleStatus.UNKNOWN
    if record.deadline_type == DeadlineType.ROLLING:
        return LifecycleStatus.OPEN
    if withdrawn_signal:
        return LifecycleStatus.WITHDRAWN
    if record.closing_date is None:
        return LifecycleStatus.UNKNOWN
    days_to_close = (record.closing_date - as_of).days
    if days_to_close < 0:
        return LifecycleStatus.CLOSED
    if days_to_close <= CLOSING_SOON_WINDOW_DAYS:
        return LifecycleStatus.CLOSING_SOON
    return LifecycleStatus.OPEN


def next_recheck_due(record: GrantRecord) -> date | None:
    """None means never re-fetched (ARCHIVED records). See §8."""
    if record.review_status == ReviewStatus.ARCHIVED:
        return None
    base = record.last_checked_at.date()
    if record.lifecycle_status == LifecycleStatus.CLOSING_SOON:
        return base + timedelta(days=RECHECK_CADENCE_DAYS_CLOSING_SOON)
    if record.lifecycle_status == LifecycleStatus.UNKNOWN:
        return base + timedelta(days=RECHECK_CADENCE_DAYS_UNKNOWN)
    return base + timedelta(days=RECHECK_CADENCE_DAYS_DEFAULT)


def check_withdrawn(fetch_result, prior_fetch_result=None) -> bool:
    """Two consecutive 404/410s, or re-fetched content no longer classifies
    as an opportunity (module 07). See §7.1, §8.
    """
    raise NotImplementedError("See docs/modules/10-record-lifecycle.md §7.1, §8")


def diff_and_record_history(record_id: str, old_record: GrantRecord, new_record: GrantRecord) -> None:
    """Writes closing_date/amount_details/eligibility_text diffs to
    record_history; raises a review flag on tracked-field changes for
    queued records. See §7.3, §7.4.
    """
    raise NotImplementedError("See docs/modules/10-record-lifecycle.md §7.3, §7.4")


def build_reopening_watch(record: GrantRecord) -> ReopeningWatch:
    """Called when a FIXED_DATE record transitions to CLOSED. Computes the
    watch (due 11 months after closing) but does not persist it — wire a
    repository insert per §7.6, §8 once module 16's storage is in place.
    Reuses module 11's title/funder normalization for later recurrence
    matching against reopening_watches.
    """
    if record.deadline_type != DeadlineType.FIXED_DATE or record.closing_date is None:
        raise ValueError("reopening watch requires a FIXED_DATE record with a closing_date")
    from app.dedup.service import (
        normalize_title,  # local import avoids a hard cross-module dependency at load time
    )

    return ReopeningWatch(
        id="",  # assign on persistence
        original_record_id=record.grant_id,
        funder_name_normalized=record.funder_name_normalized,
        title_normalized=normalize_title(record.grant_title),
        closed_at=record.closing_date,
        watch_due_at=record.closing_date + relativedelta(months=REOPENING_WATCH_MONTHS_AFTER_CLOSE),
        status="pending",
    )
