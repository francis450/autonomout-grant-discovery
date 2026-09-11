"""Canonical GrantRecord schema — module 08 (Extraction Engine).

Full spec: docs/modules/08-extraction-engine.md §6.

This is the platform's single source of truth for the GrantRecord shape.
Every other module reads or writes a subset of these fields; they import
from here rather than redefining anything. v2 -> v3 changes: record_type,
lifecycle_status, sources[], attachments[], profile_version,
extraction_status added; self-reported confidence replaced by computed
confidence; model_used has no default.
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field, HttpUrl


class GrantCategory(str, Enum):
    E_WASTE_RECYCLING = "E-Waste & Environmental ESG"
    DIGITAL_EDUCATION = "Digital Literacy & Education"
    RENEWABLE_ENERGY = "Solar Infrastructure & Off-Grid Tech"
    CONNECTIVITY = "Rural Connectivity"
    CAPACITY_BUILDING = "Non-Profit Capacity & Hardware Logistics"
    GENERAL_TECHNOLOGY = "General Technology Access"


class GeographicScope(str, Enum):
    KENYA = "Kenya"
    EAST_AFRICA = "East Africa"
    SUB_SAHARAN_AFRICA = "Sub-Saharan Africa"
    AFRICA = "Africa (continental)"
    GLOBAL_DEVELOPING = "Global Developing Nations"
    NORTH_AMERICA_ONLY = "North America / US Domestic Only"
    EUROPE_ONLY = "Europe / UK Only"
    OTHER_REGION_ONLY = "Other specific region only"
    UNRESTRICTED = "Unrestricted / Global"


class DeadlineType(str, Enum):
    FIXED_DATE = "Fixed Date"
    ROLLING = "Rolling / Continuous"
    UNKNOWN_UNSPECIFIED = "Unknown / Unspecified"


class ApplicantEligibility(str, Enum):
    NGO_501C3 = "US 501(c)(3) Public Charity"
    EQUIVALENCY_NGO = "Foreign NGO / Equivalent Charity"
    INCORPORATED_AFRICA = "Locally Registered African NGO"
    FOR_PROFIT = "For-Profit / Social Enterprise"
    ACADEMIC_ONLY = "Universities / Research Institutions Only"
    GOVERNMENT_ONLY = "Government / Public Bodies Only"
    INDIVIDUALS_ONLY = "Individuals Only"
    UNRESTRICTED = "Any Eligible Entity"


class RecordType(str, Enum):
    OPPORTUNITY = "opportunity"
    LISTING = "listing"
    FUNDER_PROFILE = "funder_profile"
    ARTICLE = "article"
    TENDER = "tender"
    OTHER = "other"


class LifecycleStatus(str, Enum):
    OPEN = "open"
    CLOSING_SOON = "closing_soon"
    CLOSED = "closed"
    UNKNOWN = "unknown"
    WITHDRAWN = "withdrawn"


class ReviewStatus(str, Enum):
    RECOMMENDED = "recommended"
    NEEDS_REVIEW = "needs_review"
    ARCHIVED = "archived"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"


class OrganizationalSuperfilterBlockers(BaseModel):
    min_years_operating_required: int | None = None
    audited_financials_required: bool = False
    audited_financials_years_required: int | None = None
    max_annual_budget_ceiling_usd: float | None = None
    min_annual_budget_floor_usd: float | None = None
    matching_funds_required: bool = False
    matching_funds_percent: float | None = None
    local_registration_required_in: list[str] = []  # ISO country codes
    required_certifications: list[str] = []


class StandardGrantAmount(BaseModel):
    original_min: float | None = None
    original_max: float | None = None
    original_currency: str | None = None  # ISO 4217; None if not stated
    min_amount_usd: float | None = None
    max_amount_usd: float | None = None
    fx_rate_used: float | None = None
    fx_rate_date: date | None = None


class Attachment(BaseModel):
    url: HttpUrl
    filename: str
    content_hash: str
    text_chars: int
    parsed_ok: bool


class SourceRef(BaseModel):
    source_id: str
    url: HttpUrl
    first_seen_at: datetime
    last_seen_at: datetime


class DealbreakerClaim(BaseModel):
    """Pass-2 output supporting the scoring engine's dealbreaker gate.

    See docs/modules/09-scoring-engine.md §8 — a dealbreaker only counts as
    a gate if cited_phrase is found verbatim in eligibility_text; otherwise
    it is downgraded to a review flag, never a gate.
    """

    reason: str
    cited_phrase: str


class RelevanceBreakdown(BaseModel):
    geographic_score: int = Field(..., ge=0, le=100)
    thematic_score: int = Field(..., ge=0, le=100)
    eligibility_score: int = Field(..., ge=0, le=100)
    financial_score: int = Field(..., ge=0, le=100)
    composite_score: int = Field(..., ge=0, le=100)
    gated_to_zero: bool = False
    gate_reasons: list[str] = []
    matching_pillars: list[str] = []
    dealbreaker_claims: list[DealbreakerClaim] = []
    summary_justification: str
    profile_version: str


class GrantRecord(BaseModel):
    grant_id: str  # sha256 of Tier B fingerprint (module 11)
    record_type: RecordType
    record_type_decided_by: str | None = None  # 'rule' | 'model' (module 07)
    grant_title: str
    funder_name: str
    funder_name_normalized: str
    funder_iati_id: str | None = None
    canonical_url: HttpUrl
    sources: list[SourceRef]
    amount_details: StandardGrantAmount
    categories: list[GrantCategory]
    geographic_scopes: list[GeographicScope]
    eligible_applicants: list[ApplicantEligibility]
    eligibility_text: str  # verbatim excerpt, <= 1500 chars
    deadline_type: DeadlineType
    opening_date: date | None = None
    closing_date: date | None = None
    closing_date_confidence: float = Field(..., ge=0, le=1)
    lifecycle_status: LifecycleStatus
    application_method: str
    required_attachments: list[str] = []
    attachments: list[Attachment] = []
    superfilter_blockers: OrganizationalSuperfilterBlockers
    relevance_analysis: RelevanceBreakdown | None = None
    review_status: ReviewStatus
    extraction_status: str  # OK | RETRIED_OK | FAILED
    extraction_confidence: float = Field(..., ge=0, le=1)
    model_used: str
    extracted_at: datetime
    scored_at: datetime | None = None
    last_checked_at: datetime
    content_hash: str  # sha256 of page markdown + attachment text
