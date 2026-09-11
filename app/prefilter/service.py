"""Deterministic pre-filter service layer — module 07.

Full spec: docs/modules/07-deterministic-prefilter.md

Implements: record-type rule layer + model-layer fallback, and the
dateparser-based expiry filter. Tuned for RECALL — any rule/model
uncertainty must default to passed=True; only confident rejections count.
Reused by module 03's discovery qualification. Not implemented yet — stubs
only.
"""
from __future__ import annotations

from app.prefilter.schema import PrefilterResult


def classify_record_type(page) -> PrefilterResult:
    """Rule layer first (URL/title/keyword patterns reject press releases,
    research papers, procurement tenders, how-to-write-a-grant content,
    aggregator indexes with no application details). Model layer only when
    rules are inconclusive — single call on a 200-token summary. Records
    which rule or model decided it. See §7.1, §8.
    """
    raise NotImplementedError("See docs/modules/07-deterministic-prefilter.md §7.1, §8")


def check_expiry(page_markdown: str) -> PrefilterResult:
    """dateparser candidates ranked by proximity to DEADLINE_KEYWORDS.
    Reject only when a deadline is found with high confidence and is more
    than EXPIRY_GRACE_PERIOD_DAYS in the past. Ambiguous/missing dates pass
    through with deadline_type=UNKNOWN. See §7.2, §8.
    """
    raise NotImplementedError("See docs/modules/07-deterministic-prefilter.md §7.2, §8")
