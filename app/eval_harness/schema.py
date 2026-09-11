"""Evaluation harness schema — module 15.

Full spec: docs/modules/15-evaluation-harness.md §6.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

GOLDEN_SET_TARGET_SIZE = (150, 200)
MIN_PDF_ATTACHMENT_COVERAGE = 30
MIN_WOULD_PURSUE_COVERAGE = 40
DATE_MATCH_TOLERANCE_DAYS = 0
AMOUNT_MATCH_TOLERANCE_PCT = 0.05
LIST_FIELD_JACCARD_THRESHOLD = 0.7  # not numerically specified in the doc — default; see module 15 §13
PREFILTER_RECALL_TARGET = 0.98
JUNK_REJECTION_TARGET = 0.70

# Weighted higher in the Phase 1 model bake-off selection metric (module 08 §7.1)
WEIGHTED_EXTRACTION_FIELDS = {
    "closing_date": 2.0,
    "geographic_scopes": 2.0,
    "eligible_applicants": 2.0,
    "amount_details": 2.0,
}


class GoldenSetPage(BaseModel):
    id: str
    url: str
    page_snapshot: str
    attachments: list = []
    labelled_by: str
    labelled_at: datetime
    ground_truth_record: dict  # full GrantRecord-shaped ground truth
    would_pursue: bool
    geography_tag: str  # 'kenya_east_africa' | 'pan_african' | 'global' | 'us_only' | 'eu'
    has_pdf_attachment: bool
    deadline_type_tag: str  # 'fixed' | 'rolling' | 'unknown'
    is_opportunity: bool


class EvalReport(BaseModel):
    id: str
    run_at: datetime
    model_used: str
    prompt_version: str
    profile_version: str
    extraction_metrics: dict
    prefilter_metrics: dict
    scoring_metrics: dict
    dedup_metrics: dict
    report_path: str | None = None
