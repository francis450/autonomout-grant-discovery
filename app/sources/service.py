"""Source Registry service layer — module 02.

Full spec: docs/modules/02-source-registry.md

Implements: seeding from the toh-grants-engine export, health-threshold
evaluation and automatic status transitions, quarantine promotion/retirement.
Not implemented yet — stubs only.
"""
from __future__ import annotations

from app.sources.schema import Source, SourceStatus


def seed_from_toh_grants_engine_export(csv_path: str) -> list[Source]:
    """One-time import: dedupe by normalized URL (reuse module 11's
    normalize_url), classify (default Class A), tag expected page type,
    set initial status (ACTIVE if historically productive else
    QUARANTINED), origin='toh-grants-engine seed'. See §7.1.
    """
    raise NotImplementedError("See docs/modules/02-source-registry.md §7.1")


def evaluate_health_thresholds(source_id: str) -> SourceStatus:
    """Nightly job: evaluate the rolling 30-day metrics against the
    yield/precision/schema-error/block-rate/staleness thresholds and return
    the resulting status. Quarantine-triggering conditions take precedence
    over degrade-triggering ones when both fire in the same run. See §8.
    """
    raise NotImplementedError("See docs/modules/02-source-registry.md §8")


def promote_from_quarantine(source_id: str, admin_user: str) -> Source:
    """Manual-only: QUARANTINED -> ACTIVE, resets the rolling metrics window
    so stale pre-quarantine data doesn't immediately re-trigger quarantine.
    See §7.4, §11.
    """
    raise NotImplementedError("See docs/modules/02-source-registry.md §7.4")


def retire_source(source_id: str, reason: str, admin_user: str) -> Source:
    """Manual-only, any state -> RETIRED. See §7.5."""
    raise NotImplementedError("See docs/modules/02-source-registry.md §7.5")


def record_rejection_feedback(source_id: str, reason_code: str) -> None:
    """Called by module 13 (Feedback Loop) on 'expired'/'not_a_grant'
    rejections — decrements the precision-ratio input feeding §8's
    thresholds.
    """
    raise NotImplementedError("See docs/modules/02-source-registry.md §3.3, §8")
