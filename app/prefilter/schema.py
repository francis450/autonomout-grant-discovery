"""Deterministic pre-filter schema — module 07.

Full spec: docs/modules/07-deterministic-prefilter.md §6.
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from app.extraction.schema import DeadlineType, RecordType

EXPIRY_GRACE_PERIOD_DAYS = 14
MODEL_LAYER_SUMMARY_TOKENS = 200
DEADLINE_KEYWORDS = ["deadline", "closes", "submit by", "applications due"]


class PrefilterResult(BaseModel):
    record_type: RecordType
    record_type_decided_by: str  # 'rule' | 'model'
    record_type_rule_matched: str | None = None
    passed: bool
    reject_reason: str | None = None
    deadline_type: DeadlineType
    deadline_found: date | None = None
    deadline_confidence: float = 0.0
