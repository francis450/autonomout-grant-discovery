"""Smoke test: every module package imports cleanly and its schema models
instantiate. This is the baseline the skeleton must satisfy before any
module's real implementation work begins.
"""
import importlib
from datetime import UTC

import pytest

MODULES = [
    "org_profile", "sources", "discovery", "crawl_policy", "ingestion",
    "attachments", "prefilter", "extraction", "scoring", "lifecycle",
    "dedup", "review_app", "feedback_loop", "delivery", "eval_harness",
    "runtime",
]


@pytest.mark.parametrize("module_name", MODULES)
def test_schema_module_imports(module_name):
    importlib.import_module(f"app.{module_name}.schema")


@pytest.mark.parametrize("module_name", MODULES)
def test_service_module_imports(module_name):
    importlib.import_module(f"app.{module_name}.service")


def test_grant_record_schema_round_trips():
    from datetime import datetime

    from app.extraction.schema import (
        DeadlineType,
        GrantRecord,
        LifecycleStatus,
        OrganizationalSuperfilterBlockers,
        RecordType,
        ReviewStatus,
        StandardGrantAmount,
    )

    now = datetime.now(UTC)
    record = GrantRecord(
        grant_id="abc123",
        record_type=RecordType.OPPORTUNITY,
        grant_title="Test Grant",
        funder_name="Test Funder",
        funder_name_normalized="test funder",
        canonical_url="https://example.org/grant",
        sources=[],
        amount_details=StandardGrantAmount(),
        categories=[],
        geographic_scopes=[],
        eligible_applicants=[],
        eligibility_text="",
        deadline_type=DeadlineType.UNKNOWN_UNSPECIFIED,
        closing_date_confidence=0.0,
        lifecycle_status=LifecycleStatus.UNKNOWN,
        application_method="online form",
        superfilter_blockers=OrganizationalSuperfilterBlockers(),
        review_status=ReviewStatus.NEEDS_REVIEW,
        extraction_status="OK",
        extraction_confidence=0.9,
        model_used="test-model",
        extracted_at=now,
        last_checked_at=now,
        content_hash="deadbeef",
    )
    assert record.grant_title == "Test Grant"


def test_url_normalization_is_idempotent():
    from app.dedup.service import normalize_url

    url = "https://www.example.org/grants/2026/?utm_source=newsletter&ref=abc#top"
    normalized = normalize_url(url)
    assert "utm_source" not in normalized
    assert "ref=" not in normalized
    assert normalized == normalize_url(normalized)


def test_scoring_gates_and_vectors():
    from datetime import date, datetime

    from app.extraction.schema import (
        ApplicantEligibility,
        DeadlineType,
        GeographicScope,
        GrantRecord,
        LifecycleStatus,
        OrganizationalSuperfilterBlockers,
        RecordType,
        RelevanceBreakdown,
        ReviewStatus,
        StandardGrantAmount,
    )
    from app.org_profile.schema import AwardRange, LegalEntity, OrgProfile, PillarWeight
    from app.scoring.schema import ScoringWeights
    from app.scoring.service import route_review_status, score_record

    profile = OrgProfile(
        profile_version="test",
        legal_entities=[LegalEntity(name="TOH", jurisdiction="KE", status="NGO", registered_since=2015)],
        operating_since=2015,
        audited_financials_available_years=5,
        annual_budget_usd=500_000,
        operating_countries=["KE"],
        target_regions=["East Africa"],
        pillars={"digital_education": PillarWeight(weight=1.0)},
        award_range_usd=AwardRange(ideal_min=15000, ideal_max=250000, hard_max=2000000),
        can_provide_matching_funds=False,
    )
    weights = ScoringWeights(
        id="1", version="v1", calibrated_at=datetime.now(UTC), f1_score=0.0, is_current=True
    )

    record = GrantRecord(
        grant_id="abc123",
        record_type=RecordType.OPPORTUNITY,
        grant_title="Digital Literacy Grant",
        funder_name="Test Funder",
        funder_name_normalized="test funder",
        canonical_url="https://example.org/grant",
        sources=[],
        amount_details=StandardGrantAmount(max_amount_usd=50000),
        categories=[],
        geographic_scopes=[GeographicScope.KENYA],
        eligible_applicants=[ApplicantEligibility.NGO_501C3],
        eligibility_text="Open to 501(c)(3) organisations.",
        deadline_type=DeadlineType.ROLLING,
        closing_date_confidence=0.0,
        lifecycle_status=LifecycleStatus.OPEN,
        application_method="online form",
        superfilter_blockers=OrganizationalSuperfilterBlockers(),
        relevance_analysis=RelevanceBreakdown(
            geographic_score=0, thematic_score=0, eligibility_score=0, financial_score=0,
            composite_score=0, matching_pillars=["digital_education"],
            summary_justification="Strong match.", profile_version="test",
        ),
        review_status=ReviewStatus.NEEDS_REVIEW,
        extraction_status="OK",
        extraction_confidence=0.9,
        model_used="test-model",
        extracted_at=datetime.now(UTC),
        last_checked_at=datetime.now(UTC),
        content_hash="deadbeef",
    )

    breakdown = score_record(record, profile, weights, as_of=date(2026, 1, 1))
    assert breakdown.gated_to_zero is False
    assert breakdown.geographic_score == 100
    assert breakdown.thematic_score == 100
    assert breakdown.eligibility_score == 100
    assert breakdown.composite_score > 0
    assert route_review_status(breakdown, weights) in (
        ReviewStatus.RECOMMENDED, ReviewStatus.NEEDS_REVIEW,
    )
