"""Discovery service layer — module 03.

Full spec: docs/modules/03-discovery.md

Implements: Serper query generation, RSS ingestion, qualification (Tier 1
fetch + module 07 classifier), the 3-page promotion rule, and quarterly
Class B prospecting. Not implemented yet — stubs only.
"""
from __future__ import annotations

from app.discovery.schema import DiscoveryCandidate, FunderCandidate, QueryTemplate
from app.org_profile.schema import OrgProfile

DAILY_QUERY_COUNT = (15, 25)
PROMOTION_THRESHOLD_QUALIFIED_PAGES = 3


def generate_query_templates(profile: OrgProfile, current_year: int) -> list[QueryTemplate]:
    """Cross product of pillar keywords x target_regions/operating_countries
    x a fixed set of query patterns, sampled down to 15-25/day (rotate
    through the full set over a week). See §7.1, §8.
    """
    raise NotImplementedError("See docs/modules/03-discovery.md §7.1, §8")


def run_daily_serper_discovery() -> list[DiscoveryCandidate]:
    """Execute the day's queries against Serper, normalize + dedup result
    URLs against the registry/record store (app.dedup.service.normalize_url),
    insert new discovery_candidates rows. See §7.1, §7.2.
    """
    raise NotImplementedError("See docs/modules/03-discovery.md §7.1, §7.2")


def poll_rss_feeds() -> list[DiscoveryCandidate]:
    """Poll RSS feeds of ACTIVE Class A sources daily. See §7.3."""
    raise NotImplementedError("See docs/modules/03-discovery.md §7.3")


def qualify_candidate(candidate: DiscoveryCandidate) -> DiscoveryCandidate:
    """Tier 1 fetch (module 05) + record-type classify (module 07). On
    'opportunity'/'listing', increments the domain's qualified-page count;
    at PROMOTION_THRESHOLD_QUALIFIED_PAGES, promotes the domain to ACTIVE
    via module 02 (unless already QUARANTINED — manual gate stays
    authoritative). See §7.5, §7.6, §8, §11.
    """
    raise NotImplementedError("See docs/modules/03-discovery.md §7.5, §7.6, §8")


def run_quarterly_class_b_prospecting() -> list[FunderCandidate]:
    """IATI Datastore / 360Giving GrantNav / Candid export -> ranked funder
    shortlist for grants-team review. Never auto-promotes to Class A — a
    human decision is required. See §7.7.
    """
    raise NotImplementedError("See docs/modules/03-discovery.md §7.7")
