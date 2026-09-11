"""Scoring engine schema — module 09.

Full spec: docs/modules/09-scoring-engine.md §6.

The RelevanceBreakdown result model lives in app.extraction.schema (module
08 owns it canonically since it's a GrantRecord field) — this module is its
primary producer but does not redefine it.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

# Provisional defaults — calibrated in Phase 1 via grid search (§8), never
# hardcoded as final.
DEFAULT_GEOGRAPHIC_WEIGHT = 0.30
DEFAULT_THEMATIC_WEIGHT = 0.35
DEFAULT_ELIGIBILITY_WEIGHT = 0.15
DEFAULT_FINANCIAL_WEIGHT = 0.20
DEFAULT_RECOMMENDED_THRESHOLD = 70
DEFAULT_REVIEW_THRESHOLD = 45


class ScoringWeights(BaseModel):
    id: str
    version: str
    geographic_weight: float = DEFAULT_GEOGRAPHIC_WEIGHT
    thematic_weight: float = DEFAULT_THEMATIC_WEIGHT
    eligibility_weight: float = DEFAULT_ELIGIBILITY_WEIGHT
    financial_weight: float = DEFAULT_FINANCIAL_WEIGHT
    recommended_threshold: int = DEFAULT_RECOMMENDED_THRESHOLD
    review_threshold: int = DEFAULT_REVIEW_THRESHOLD
    calibrated_at: datetime
    f1_score: float
    is_current: bool = False
