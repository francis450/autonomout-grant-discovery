"""Evaluation harness service layer — module 15.

Full spec: docs/modules/15-evaluation-harness.md

field_match() implements the fully-specified per-field tolerance rules
(§7.3, §8) for real. Metric aggregation across a golden set and the
one-command harness runner require DB/model access — stubbed.
"""
from __future__ import annotations

from typing import Any

from app.eval_harness.schema import (
    AMOUNT_MATCH_TOLERANCE_PCT,
    LIST_FIELD_JACCARD_THRESHOLD,
)

DATE_FIELDS = {"opening_date", "closing_date"}
AMOUNT_FIELDS = {"min_amount_usd", "max_amount_usd", "original_min", "original_max"}
ENUM_FIELDS = {"deadline_type", "record_type", "lifecycle_status", "review_status"}
LIST_FIELDS = {"geographic_scopes", "eligible_applicants", "categories"}


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 1.0
    return len(a & b) / len(union)


def field_match(field_name: str, predicted: Any, ground_truth: Any) -> bool:
    """Dates: exact (±0 days). Amounts: ±5%. Enums: exact. Lists: Jaccard >=
    LIST_FIELD_JACCARD_THRESHOLD. See §7.3, §8.
    """
    if field_name in DATE_FIELDS:
        return predicted == ground_truth
    if field_name in AMOUNT_FIELDS:
        if ground_truth is None:
            return predicted is None
        if predicted is None:
            return False
        return abs(predicted - ground_truth) / max(abs(ground_truth), 1) <= AMOUNT_MATCH_TOLERANCE_PCT
    if field_name in ENUM_FIELDS:
        return predicted == ground_truth
    if field_name in LIST_FIELDS:
        return _jaccard(set(predicted or []), set(ground_truth or [])) >= LIST_FIELD_JACCARD_THRESHOLD
    return predicted == ground_truth


def extraction_accuracy_report(model: str, prompt_version: str, golden_set) -> dict:
    """Per-field accuracy across the golden set, using field_match(). See §8."""
    raise NotImplementedError("See docs/modules/15-evaluation-harness.md §7.3, §8")


def prefilter_metrics(golden_set) -> dict:
    """Recall on is_opportunity=True pages; rejection rate on
    is_opportunity=False pages. See §7.4, §8.
    """
    raise NotImplementedError("See docs/modules/15-evaluation-harness.md §7.4, §8")


def scoring_metrics(golden_set, profile_version: str) -> dict:
    """Precision/recall of RECOMMENDED against would_pursue; score
    distribution separation; F1 at chosen thresholds. See §7.5, §8.
    """
    raise NotImplementedError("See docs/modules/15-evaluation-harness.md §7.5, §8")


def dedup_metrics(seeded_duplicate_test_set) -> dict:
    """Duplicate pairs found/seeded; false merges (target 0). See §7.6, §8."""
    raise NotImplementedError("See docs/modules/15-evaluation-harness.md §7.6, §8")


def run_eval_harness(model: str, prompt_version: str, profile_version: str):
    """One-command runner: full golden set -> extraction + prefilter +
    scoring + dedup metrics -> dated report. Required before promoting any
    model/prompt/weight/threshold change. See §7.7, §8.
    """
    raise NotImplementedError("See docs/modules/15-evaluation-harness.md §7.7, §8")
