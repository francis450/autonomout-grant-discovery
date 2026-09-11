"""Tiered ingestion service layer — module 05.

Full spec: docs/modules/05-tiered-ingestion.md

Implements: Tier 0 API adapters, Tier 1 Crawl4AI fetch, Tier 2
Playwright+Browser-Use agent, the Tier1->Tier2 escalation rule, and
listing/detail link extraction with dedup-gated detail fetching. Every fetch
must go through app.crawl_policy.service.can_fetch() first. Not implemented
yet — stubs only.
"""
from __future__ import annotations

from app.ingestion.schema import (
    FetchRun,
)


def fetch_tier0(source_id: str) -> list[FetchRun]:
    """Direct JSON/XML fetch against a source's published API endpoint (EU
    F&T, Grants.gov search2, GlobalGiving, IATI/360Giving for Class B). See
    §7.2.
    """
    raise NotImplementedError("See docs/modules/05-tiered-ingestion.md §7.2")


def fetch_tier1(source_id: str, url: str) -> FetchRun:
    """Crawl4AI headless fetch -> JS render -> clean markdown. Default tier
    for 85-90% of Class A sources. Must call
    app.crawl_policy.service.can_fetch() first. See §7.3.
    """
    raise NotImplementedError("See docs/modules/05-tiered-ingestion.md §7.3")


def fetch_tier2(source_id: str, url: str) -> FetchRun:
    """Playwright + Browser-Use agent, capped at 40 steps / 3 minutes, every
    step logged to Tier2RunStep. Only runs if evaluate_escalation() returned
    True and a human has enabled Tier 2 for this source. See §7.4.
    """
    raise NotImplementedError("See docs/modules/05-tiered-ingestion.md §7.4")


def evaluate_escalation(source_id: str) -> bool:
    """True only if the last ESCALATION_WINDOW_RUNS consecutive Tier 1 runs
    all satisfy: markdown < ESCALATION_TOKEN_THRESHOLD tokens OR no dated
    content; AND not blocked; AND robots.txt permits; AND Tier 2 is
    human-enabled for this source. See §8.
    """
    raise NotImplementedError("See docs/modules/05-tiered-ingestion.md §8")


def extract_listing_candidate_links(listing_markdown: str, source_id: str) -> list[str]:
    """URL patterns + lightweight link-text classifier -> candidate detail
    links only (not full records). Detail pages are fetched only if not
    already in the record store (module 11 Tier A) or content may have
    changed (module 10). See §7.5, §7.6, §8.
    """
    raise NotImplementedError("See docs/modules/05-tiered-ingestion.md §7.5, §7.6, §8")
