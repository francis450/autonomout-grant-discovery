"""Tiered ingestion schema — module 05.

Full spec: docs/modules/05-tiered-ingestion.md §6.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

TIER2_MAX_STEPS = 40
TIER2_MAX_SECONDS = 180
ESCALATION_WINDOW_RUNS = 3
ESCALATION_TOKEN_THRESHOLD = 400


class FetchRun(BaseModel):
    id: str
    source_id: str
    url: str
    tier_used: int  # 0 | 1 | 2
    fetched_at: datetime
    status_code: int | None = None
    content_hash: str | None = None
    token_count: int | None = None
    had_dated_content: bool | None = None
    blocked: bool = False
    error: str | None = None
    duration_ms: int = 0


class Tier2RunStep(BaseModel):
    fetch_run_id: str
    step_number: int
    action: str  # 'click' | 'fill' | 'navigate' | ...
    target: str
    timestamp: datetime
