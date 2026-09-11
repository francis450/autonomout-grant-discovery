"""Discovery schema — module 03.

Full spec: docs/modules/03-discovery.md §6.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class QueryTemplate(BaseModel):
    pillar_keyword: str
    geography: str
    year: int
    template: str


class DiscoveryCandidate(BaseModel):
    id: str
    url: str
    normalized_url: str
    domain: str
    source_query: str
    discovered_at: datetime
    qualification_result: str = "pending"  # pending | opportunity | listing | rejected
    qualified_at: datetime | None = None
    promoted_source_id: str | None = None


class FunderCandidate(BaseModel):
    funder_name: str
    funder_name_normalized: str
    funder_iati_id: str | None = None
    total_grants_observed: int
    thematic_overlap_score: float
    geographic_overlap: bool
    typical_award_size_usd: tuple[float, float]
    homepage_url: str | None = None
    recommendation: str
