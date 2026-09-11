"""Org profile schema — module 01.

Full spec: docs/modules/01-org-profile.md §6.

Mirrors config/org_profile.yaml. No org-identity fact may be hardcoded
anywhere else in the codebase — always go through OrgProfile.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class LegalEntity(BaseModel):
    name: str
    jurisdiction: str  # ISO 3166-1 alpha-2
    status: str
    registered_since: int


class PillarWeight(BaseModel):
    weight: float = Field(..., ge=0.0, le=1.0)


class AwardRange(BaseModel):
    ideal_min: float
    ideal_max: float
    hard_max: float


class OrgProfile(BaseModel):
    profile_version: str  # content-hash (Phase 1-3) or DB row version (Phase 4)
    legal_entities: list[LegalEntity]
    operating_since: int
    audited_financials_available_years: int
    annual_budget_usd: float
    operating_countries: list[str]  # ISO 3166-1 alpha-2
    target_regions: list[str]
    pillars: dict[str, PillarWeight]
    award_range_usd: AwardRange
    can_provide_matching_funds: bool
    certifications: list[str] = []
