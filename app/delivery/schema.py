"""Delivery schema — module 14.

Full spec: docs/modules/14-delivery.md §6.
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

CLOSING_SOON_DIGEST_WINDOW_DAYS = 21


class GrantRecordSummary(BaseModel):
    grant_id: str
    grant_title: str
    funder_name: str
    composite_score: int
    closing_date: date | None = None
    review_app_link: str


class SourceHealthWarning(BaseModel):
    source_id: str
    source_name: str
    status: str  # 'DEGRADED' | 'QUARANTINED'
    reason: str


class DigestContent(BaseModel):
    period_start: datetime
    period_end: datetime
    new_recommended: list[GrantRecordSummary]
    closing_within_21_days: list[GrantRecordSummary]
    source_health_warnings: list[SourceHealthWarning]


class DigestSendRecord(BaseModel):
    id: str
    sent_at: datetime
    recipient_count: int
    new_recommended_count: int
    closing_soon_count: int
    warning_count: int
    status: str  # 'sent' | 'failed'
    error: str | None = None
