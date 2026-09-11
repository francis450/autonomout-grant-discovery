"""Review app schema — module 12.

Full spec: docs/modules/12-review-app.md §6.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

# Fixed reason codes — drive module 02 precision metrics and module 13 rule
# mining. Do not extend without updating those consumers. See §6.
REJECTION_REASONS = [
    "expired", "not_a_grant", "geography", "eligibility",
    "too_small_or_large", "duplicate", "other",
]


class ReviewDecision(BaseModel):
    id: str
    grant_record_id: str
    reviewer: str
    decision: str  # 'approved' | 'rejected' | 'applied'
    reason_code: str | None = None  # required if decision == 'rejected'
    field_corrections: dict | None = None  # {field_name: {old, new}}
    decided_at: datetime
