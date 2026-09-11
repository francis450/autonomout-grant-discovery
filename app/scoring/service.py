"""Scoring engine service layer — module 09.

Full spec: docs/modules/09-scoring-engine.md

Gates, vectors, and the composite formula are pure, deterministic functions
fully specified by the design doc — implemented for real below (§7, §8).
Calibration (grid search against the golden set) and weight persistence
require module 15/16 infrastructure — stubbed.
"""
from __future__ import annotations

from datetime import date, datetime

from app.extraction.schema import (
    ApplicantEligibility,
    DealbreakerClaim,
    GeographicScope,
    GrantRecord,
    LifecycleStatus,
    RelevanceBreakdown,
    ReviewStatus,
)
from app.org_profile.schema import OrgProfile
from app.scoring.schema import ScoringWeights

# --- Gates (§7.1) ----------------------------------------------------------

_ELIGIBLE_SET = {
    ApplicantEligibility.NGO_501C3,
    ApplicantEligibility.EQUIVALENCY_NGO,
    ApplicantEligibility.INCORPORATED_AFRICA,
    ApplicantEligibility.UNRESTRICTED,
}
_EXCLUSIONARY_GEO = {
    GeographicScope.NORTH_AMERICA_ONLY,
    GeographicScope.EUROPE_ONLY,
    GeographicScope.OTHER_REGION_ONLY,
}


def superfilter_gate(record: GrantRecord, profile: OrgProfile, as_of: date | None = None) -> bool:
    as_of = as_of or datetime.now().astimezone().date()
    blockers = record.superfilter_blockers
    years_operating = as_of.year - profile.operating_since

    if (blockers.min_years_operating_required is not None
            and blockers.min_years_operating_required > years_operating):
        return True
    if (blockers.audited_financials_years_required is not None
            and blockers.audited_financials_years_required > profile.audited_financials_available_years):
        return True
    budget = profile.annual_budget_usd
    if blockers.max_annual_budget_ceiling_usd is not None and budget > blockers.max_annual_budget_ceiling_usd:
        return True
    if blockers.min_annual_budget_floor_usd is not None and budget < blockers.min_annual_budget_floor_usd:
        return True
    if blockers.matching_funds_required and not profile.can_provide_matching_funds:
        return True
    if blockers.local_registration_required_in:
        toh_jurisdictions = {e.jurisdiction for e in profile.legal_entities}
        if any(country not in toh_jurisdictions for country in blockers.local_registration_required_in):
            return True
    return bool(
        blockers.required_certifications
        and not set(blockers.required_certifications).issubset(set(profile.certifications))
    )


def eligibility_gate(record: GrantRecord) -> bool:
    return not (_ELIGIBLE_SET & set(record.eligible_applicants))


def geography_gate(record: GrantRecord) -> bool:
    scopes = set(record.geographic_scopes)
    return bool(scopes) and scopes.issubset(_EXCLUSIONARY_GEO)


def dealbreaker_gate(record: GrantRecord) -> str | None:
    """Only counts as a gate if the claim's cited_phrase is found verbatim
    in eligibility_text; otherwise it's a review flag, never a gate (§7.1).
    Uncited claims are returned separately by the caller for flagging —
    this function returns only the gate reason string, or None.
    """
    if not record.relevance_analysis:
        return None
    for claim in record.relevance_analysis.dealbreaker_claims:
        if claim.cited_phrase and claim.cited_phrase in record.eligibility_text:
            return f"dealbreaker: {claim.reason}"
    return None


def uncited_dealbreaker_claims(record: GrantRecord) -> list[DealbreakerClaim]:
    """Claims that failed the verbatim-citation check — route to a review
    flag (module 12), never to a gate. See §7.1.
    """
    if not record.relevance_analysis:
        return []
    return [
        c for c in record.relevance_analysis.dealbreaker_claims
        if not (c.cited_phrase and c.cited_phrase in record.eligibility_text)
    ]


def lifecycle_gate(record: GrantRecord) -> bool:
    return record.lifecycle_status in (LifecycleStatus.CLOSED, LifecycleStatus.WITHDRAWN)


# --- Vectors (§7.2) ---------------------------------------------------------

def geographic_score(scopes: list[GeographicScope]) -> int:
    scope_set = set(scopes)
    if {GeographicScope.KENYA, GeographicScope.EAST_AFRICA} & scope_set:
        return 100
    if {GeographicScope.SUB_SAHARAN_AFRICA, GeographicScope.AFRICA} & scope_set:
        return 90
    if {GeographicScope.GLOBAL_DEVELOPING, GeographicScope.UNRESTRICTED} & scope_set:
        return 75
    return 0  # defensive default — geography_gate should already exclude this path


def thematic_score(matching_pillars: list[str], profile: OrgProfile) -> int:
    """T = 100 * max(pillar_weight for matched pillars) + 10 * (count of
    additional matched pillars beyond the top one), capped at 100.
    """
    weights = [profile.pillars[p].weight for p in matching_pillars if p in profile.pillars]
    if not weights:
        return 0
    weights.sort(reverse=True)
    score = 100 * weights[0] + 10 * (len(weights) - 1)
    return int(min(100, round(score)))


def eligibility_score(eligible_applicants: list[ApplicantEligibility]) -> int:
    applicants = set(eligible_applicants)
    if {ApplicantEligibility.NGO_501C3, ApplicantEligibility.EQUIVALENCY_NGO} & applicants:
        return 100
    if applicants == {ApplicantEligibility.INCORPORATED_AFRICA}:
        return 85
    if applicants == {ApplicantEligibility.UNRESTRICTED}:
        return 60
    return 0  # not in the gate-surviving allow-list — defensive default


def financial_score(amount_usd: float | None, award_range) -> int:
    if amount_usd is None:
        return 60
    if award_range.ideal_min <= amount_usd <= award_range.ideal_max:
        return 100
    if award_range.ideal_max < amount_usd <= award_range.hard_max:
        return 70
    if 2000 <= amount_usd < award_range.ideal_min:
        return 50
    return 30  # below 2,000 or above hard_max


# --- Composite (§7.3) -------------------------------------------------------

def score_record(record: GrantRecord, profile: OrgProfile, weights: ScoringWeights,
                  as_of: date | None = None) -> RelevanceBreakdown:
    gate_reasons: list[str] = []
    if superfilter_gate(record, profile, as_of):
        gate_reasons.append("superfilter")
    if eligibility_gate(record):
        gate_reasons.append("eligibility")
    if geography_gate(record):
        gate_reasons.append("geography")
    dealbreaker_reason = dealbreaker_gate(record)
    if dealbreaker_reason:
        gate_reasons.append(dealbreaker_reason)
    if lifecycle_gate(record):
        gate_reasons.append("lifecycle")

    matching_pillars = record.relevance_analysis.matching_pillars if record.relevance_analysis else []
    justification = record.relevance_analysis.summary_justification if record.relevance_analysis else ""

    if gate_reasons:
        return RelevanceBreakdown(
            geographic_score=0, thematic_score=0, eligibility_score=0, financial_score=0,
            composite_score=0, gated_to_zero=True, gate_reasons=gate_reasons,
            matching_pillars=matching_pillars, summary_justification=justification,
            profile_version=profile.profile_version,
        )

    g = geographic_score(record.geographic_scopes)
    t = thematic_score(matching_pillars, profile)
    e = eligibility_score(record.eligible_applicants)
    amount = record.amount_details.max_amount_usd or record.amount_details.min_amount_usd
    f = financial_score(amount, profile.award_range_usd)

    composite = round(
        weights.geographic_weight * g + weights.thematic_weight * t
        + weights.eligibility_weight * e + weights.financial_weight * f
    )

    return RelevanceBreakdown(
        geographic_score=g, thematic_score=t, eligibility_score=e, financial_score=f,
        composite_score=composite, gated_to_zero=False, gate_reasons=[],
        matching_pillars=matching_pillars, summary_justification=justification,
        profile_version=profile.profile_version,
    )


def route_review_status(breakdown: RelevanceBreakdown, weights: ScoringWeights) -> ReviewStatus:
    if breakdown.gated_to_zero:
        return ReviewStatus.ARCHIVED
    if breakdown.composite_score >= weights.recommended_threshold:
        return ReviewStatus.RECOMMENDED
    if breakdown.composite_score >= weights.review_threshold:
        return ReviewStatus.NEEDS_REVIEW
    return ReviewStatus.ARCHIVED


# --- Calibration (§8, Phase 1 + monthly via module 13) ---------------------

def calibrate_weights(golden_set, human_decisions: list | None = None) -> ScoringWeights:
    """Grid search over weights (step 0.05, sum to 1.0) and thresholds (step
    5), maximizing F1 against the golden set's 'would pursue' label (+
    accumulated human decisions for monthly recalibration). See §8.
    Requires module 15's golden set access — not yet wired.
    """
    raise NotImplementedError("See docs/modules/09-scoring-engine.md §8")
