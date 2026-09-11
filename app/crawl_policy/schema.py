"""Crawl policy schema — module 04.

Full spec: docs/modules/04-crawl-policy.md §6.
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

USER_AGENT = "TechOnHandGrantBot/1.0 (+https://techonhand.org/bot; grants@techonhand.org)"

REQUEST_SPACING_MIN_SECONDS = 3
REQUEST_SPACING_MAX_SECONDS = 5
DAILY_PAGE_CAP_PER_DOMAIN = 200
MAX_CONCURRENT_CONNECTIONS_PER_DOMAIN = 1
ROBOTS_RECHECK_INTERVAL_DAYS = 7


class RobotsCacheEntry(BaseModel):
    domain: str
    fetched_at: datetime
    rules_raw: str
    disallowed_paths: list[str] = []
    crawl_delay: float | None = None
    allowed: bool


class DomainRateState(BaseModel):
    domain: str
    last_request_at: datetime | None = None
    requests_today: int = 0
    day: date
    active_connections: int = 0


class FetchDecision(BaseModel):
    allowed: bool
    reason: str | None = None  # e.g. 'robots_disallowed' | 'daily_cap_reached' | 'rate_limited'
    retry_after: datetime | None = None
