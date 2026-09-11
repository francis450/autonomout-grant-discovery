"""Feedback loop schema — module 13.

Full spec: docs/modules/13-feedback-loop.md §6.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

FEW_SHOT_CAP_PER_PROMPT = 5
RECALIBRATION_F1_IMPROVEMENT_THRESHOLD = 2.0
PRECISION_DECREMENT_REASON_CODES = {"expired", "not_a_grant"}


class FewShotExample(BaseModel):
    id: str
    grant_record_id: str
    category: str  # GrantCategory value, for diversity selection
    added_at: datetime
    source: str  # 'golden_set' | 'human_corrected'
    active: bool = False


class PrefilterRuleCandidate(BaseModel):
    id: str
    grant_record_id: str
    triggering_reason: str  # always 'not_a_grant' on a rule-passed record
    page_url: str
    page_excerpt: str
    status: str = "pending"  # 'pending' | 'accepted' | 'dismissed'
    reviewed_by: str | None = None
    created_at: datetime


class RecalibrationRun(BaseModel):
    id: str
    run_at: datetime
    triggered_by: str  # 'monthly_schedule'
    golden_set_f1: float
    new_weights_f1: float
    applied: bool
    report_url: str | None = None
