"""Crawl policy service layer — module 04.

Full spec: docs/modules/04-crawl-policy.md

can_fetch() is the mandatory gate every fetch in modules 03/05/06 must call
before making any HTTP request. No evasion mechanism (proxy rotation,
CAPTCHA solving, login-wall bypass) may ever be added here — see §7.5, §14.
Not implemented yet — stubs only; requires robots.txt fetch/parse and a
Redis-backed rate limiter (module 16).
"""
from __future__ import annotations

from app.crawl_policy.schema import FetchDecision, RobotsCacheEntry


def get_or_refresh_robots(domain: str) -> RobotsCacheEntry:
    """Fetch/parse robots.txt for `domain` if the cache entry is missing or
    older than ROBOTS_RECHECK_INTERVAL_DAYS. Missing robots.txt (404) means
    fully allowed; a malformed file fails safe to fully disallowed. See §7.1,
    §7.2, §11.
    """
    raise NotImplementedError("See docs/modules/04-crawl-policy.md §7.1, §7.2")


def can_fetch(domain: str, path: str) -> FetchDecision:
    """The single entry point every fetch must call. Checks robots.txt,
    daily page cap (200/domain), single-connection limit, and 3-5s randomized
    spacing. allowed=False for rate/connection reasons means 'not now, retry
    later' — only robots_disallowed is permanent for that path. See §8.
    """
    raise NotImplementedError("See docs/modules/04-crawl-policy.md §8")


def report_fetch_outcome(domain: str, status_code: int, was_challenge: bool) -> None:
    """Feeds module 02's block_rate health metric. See §7.7."""
    raise NotImplementedError("See docs/modules/04-crawl-policy.md §7.7")
