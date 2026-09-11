"""Review app service layer — module 12.

Full spec: docs/modules/12-review-app.md

NOTE: the frontend stack (Next.js vs FastAPI+HTMX) is an explicit open
decision (§13) — resolve with the team before building the `web/` layer.
This file only contains the stack-agnostic decision-submission logic; a
`web/` UI and an `api/` router package (FastAPI, per pyproject.toml's
existing dependency) should sit alongside this once the stack is chosen.
Not implemented yet — stubs only.
"""
from __future__ import annotations

from app.review_app.schema import REJECTION_REASONS, ReviewDecision


def submit_decision(
    record_id: str,
    reviewer: str,
    decision: str,
    reason_code: str | None = None,
    field_corrections: dict | None = None,
) -> ReviewDecision:
    """Validates reason_code is required+valid for rejections, applies field
    corrections directly to the record (no re-extraction), updates
    review_status, and inserts a review_decisions row for module 13 to
    consume. See §8.
    """
    if decision == "rejected" and reason_code not in REJECTION_REASONS:
        raise ValueError(f"reason_code must be one of {REJECTION_REASONS} for a rejection")
    raise NotImplementedError("See docs/modules/12-review-app.md §7.4, §8")


def get_queue(sort_by: str = "composite_score"):
    """RECOMMENDED + NEEDS_REVIEW records, sortable by score/closing_date.
    See §7.1.
    """
    raise NotImplementedError("See docs/modules/12-review-app.md §7.1")


def promote_source_from_quarantine(source_id: str, admin_user: str):
    """Admin-only Sources view action — delegates to
    app.sources.service.promote_from_quarantine. See §7.5.
    """
    raise NotImplementedError("See docs/modules/12-review-app.md §7.5")
