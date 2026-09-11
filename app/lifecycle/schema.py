"""Record lifecycle schema — module 10.

Full spec: docs/modules/10-record-lifecycle.md §6.
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

CLOSING_SOON_WINDOW_DAYS = 21
RECHECK_CADENCE_DAYS_DEFAULT = 7
RECHECK_CADENCE_DAYS_CLOSING_SOON = 2
RECHECK_CADENCE_DAYS_UNKNOWN = 14
WITHDRAWN_CONSECUTIVE_404_COUNT = 2
REOPENING_WATCH_MONTHS_AFTER_CLOSE = 11


class RecordHistoryEntry(BaseModel):
    id: str
    grant_record_id: str
    changed_at: datetime
    change_type: str  # 'recheck_diff' | 'lifecycle_transition' | 'reopening_watch_created'
    field_name: str | None = None
    old_value: str | None = None
    new_value: str | None = None
    triggered_review_flag: bool = False


class ReopeningWatch(BaseModel):
    id: str
    original_record_id: str
    funder_name_normalized: str
    title_normalized: str
    closed_at: date
    watch_due_at: date
    status: str = "pending"  # 'pending' | 'checked_reopened' | 'checked_not_reopened'
