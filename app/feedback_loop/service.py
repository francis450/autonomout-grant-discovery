"""Feedback loop service layer — module 13.

Full spec: docs/modules/13-feedback-loop.md

Implements: few-shot bank population/rotation, monthly recalibration
trigger (delegates the grid search to app.scoring.service.calibrate_weights),
source precision decrementing, and prefilter rule-candidate queuing. Not
implemented yet — stubs only; each reacts to app.review_app review_decisions
events.
"""
from __future__ import annotations

from app.feedback_loop.schema import (
    FewShotExample,
    PrefilterRuleCandidate,
    RecalibrationRun,
)
from app.review_app.schema import ReviewDecision


def on_review_decision(decision: ReviewDecision, record) -> None:
    """Dispatch: approved+corrections -> few-shot bank; rejected with
    expired/not_a_grant -> source precision decrement; rejected
    not_a_grant on a rule-passed record -> prefilter rule candidate.
    See §7.
    """
    raise NotImplementedError("See docs/modules/13-feedback-loop.md §7")


def rotate_few_shot_bank() -> list[FewShotExample]:
    """Weekly: select active examples capped at FEW_SHOT_CAP_PER_PROMPT,
    by category diversity, preferring human_corrected over golden_set.
    See §7.1, §8.
    """
    raise NotImplementedError("See docs/modules/13-feedback-loop.md §7.1, §8")


def run_monthly_recalibration() -> RecalibrationRun:
    """Delegates to app.scoring.service.calibrate_weights over golden set +
    accumulated human decisions; applies only if F1 improves by >=
    RECALIBRATION_F1_IMPROVEMENT_THRESHOLD; always logs a RecalibrationRun
    and report regardless of outcome. See §7.2, §8.
    """
    raise NotImplementedError("See docs/modules/13-feedback-loop.md §7.2, §8")


def decrement_source_precision(decision: ReviewDecision, record) -> None:
    """On expired/not_a_grant rejections: decrement the source with the
    earliest first_seen_at among record.sources (documented tie-break —
    see §11). Delegates to app.sources.service.record_rejection_feedback.
    See §7.3, §8.
    """
    raise NotImplementedError("See docs/modules/13-feedback-loop.md §7.3, §8, §11")


def queue_prefilter_rule_candidate(decision: ReviewDecision, record) -> PrefilterRuleCandidate:
    """Only for not_a_grant rejections where record_type_decided_by=='rule'
    and the rule had passed=True. Never auto-adds a rule — admin reviews
    the queue. See §7.4, §8.
    """
    raise NotImplementedError("See docs/modules/13-feedback-loop.md §7.4, §8")
