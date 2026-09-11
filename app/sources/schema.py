"""Source Registry schema — module 02.

Full spec: docs/modules/02-source-registry.md §6.
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel


class SourceClass(str, Enum):
    A_OPPORTUNITY = "A"  # open calls, RFPs — crawled, enters extraction pipeline
    B_PROSPECTING = "B"  # funder-prospecting datasets (IATI, 360Giving, Candid)
    C_DISCOVERY = "C"  # Serper/RSS/newsletter feeds -> PENDING_QUALIFICATION


class SourceStatus(str, Enum):
    PENDING_QUALIFICATION = "pending_qualification"
    ACTIVE = "active"
    DEGRADED = "degraded"
    QUARANTINED = "quarantined"
    RETIRED = "retired"


class SourceOrigin(str, Enum):
    SEED = "toh-grants-engine seed"
    DISCOVERY = "discovery"
    MANUAL = "manual"


class Source(BaseModel):
    id: str
    name: str
    homepage_url: str
    listing_urls: list[str] = []
    source_class: SourceClass
    ingest_tier: int  # 0 | 1 | 2
    crawl_cadence_hours: int
    priority: int  # 1-5
    robots_allowed: bool
    robots_checked_at: datetime | None = None
    user_agent_policy: str | None = None
    status: SourceStatus
    last_success_at: datetime | None = None
    last_error: str | None = None
    notes: str | None = None
    origin: SourceOrigin
    created_at: datetime
    updated_at: datetime


class SourceMetricsDaily(BaseModel):
    source_id: str
    day: date
    pages_fetched: int = 0
    records_extracted: int = 0
    records_recommended: int = 0
    schema_errors: int = 0
    blocked_responses: int = 0
    total_responses: int = 0
