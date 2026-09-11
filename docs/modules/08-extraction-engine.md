# Module 08: Extraction Engine

## 1. Purpose

Turns a page (plus its attachment context) that survived the pre-filter into a
structured `GrantRecord` — the platform's canonical data model. This module
owns the choice of LLM, the constrained-decoding extraction procedure, and the
`GrantRecord` schema itself, which nearly every other module reads or writes
a subset of.

## 2. Scope

### In scope
- Model selection as a Phase 1 experiment (not a hardcoded constant).
- The two-pass extraction procedure (factual fields, then relevance analysis).
- Constrained decoding, retry-on-validation-failure, and `extraction_status`.
- Computed `extraction_confidence` (never self-reported by the model).
- The full `GrantRecord` Pydantic schema (canonical definition — other modules
  reference it, they do not redefine it).

### Out of scope
- The actual composite scoring formula and gates — module 09 (this module's
  pass-2 output, `RelevanceBreakdown`, is consumed and finalized by module 09;
  see the split described in §7).
- Deduplication — module 11.
- Attachment download/parsing — module 06 (this module only consumes the
  assembled context block).
- Prefiltering — module 07 (only records that pass reach this module).

## 3. Dependencies

- Module 07 (Deterministic Pre-Filter): supplies the page content and
  `record_type` for records that pass.
- Module 06 (Attachment Parsing): supplies the labelled attachment context
  block.
- Module 01 (Org Profile): pass-2 relevance analysis takes the org profile as
  input context.
- Module 15 (Evaluation Harness): the golden set and field-accuracy metrics
  drive model selection and any re-run after a model/prompt change.
- Module 16 (Runtime & Operations): the LLM job queue this module's calls run
  through, and the Ollama host.
- Module 09 (Scoring Engine) and module 11 (Deduplication) both consume
  `GrantRecord` fields this module produces.

## 4. Roadmap Phase & Exit Criteria

Phase 1: "model bake-off" is an explicit deliverable. Exit criterion: chosen
model ≥ **85% field accuracy** on `closing_date`/`geographic_scopes`/
`eligibility`; throughput ≥ **8 records/minute** on the office GPU.

Phase 3: "two-pass extraction ... computed confidence" is an explicit
deliverable, alongside attachment parsing and scoring — this is when the full
pipeline (pass 1 → pass 2 → module 09 scoring) goes live end-to-end.

## 5. Inputs & Outputs

**Inputs**: page markdown (module 05/07), attachment context block (module
06), org profile (module 01), golden-set few-shot examples (module 15, and
from Phase 4 human-corrected records via module 13).

**Outputs**: a validated `GrantRecord` (pass-1 fields populated always; pass-2
`relevance_analysis` populated when scoring runs), with `extraction_status`,
`extraction_confidence`, and `model_used` stamped.

## 6. Data Model

This is the canonical schema definition for the whole platform. All field
names below are authoritative; other modules must not rename or redefine
them.

```python
from enum import Enum
from typing import List, Optional
from datetime import date, datetime
from pydantic import BaseModel, Field, HttpUrl

class GrantCategory(str, Enum):
    E_WASTE_RECYCLING = "E-Waste & Environmental ESG"
    DIGITAL_EDUCATION = "Digital Literacy & Education"
    RENEWABLE_ENERGY  = "Solar Infrastructure & Off-Grid Tech"
    CONNECTIVITY      = "Rural Connectivity"
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
    OPPORTUNITY = "opportunity"; LISTING = "listing"; FUNDER_PROFILE = "funder_profile"
    ARTICLE = "article"; TENDER = "tender"; OTHER = "other"

class LifecycleStatus(str, Enum):
    OPEN = "open"; CLOSING_SOON = "closing_soon"; CLOSED = "closed"
    UNKNOWN = "unknown"; WITHDRAWN = "withdrawn"

class ReviewStatus(str, Enum):
    RECOMMENDED = "recommended"; NEEDS_REVIEW = "needs_review"; ARCHIVED = "archived"
    APPROVED = "approved"; REJECTED = "rejected"; APPLIED = "applied"

class OrganizationalSuperfilterBlockers(BaseModel):
    min_years_operating_required: Optional[int] = None
    audited_financials_required: bool = False
    audited_financials_years_required: Optional[int] = None
    max_annual_budget_ceiling_usd: Optional[float] = None
    min_annual_budget_floor_usd: Optional[float] = None
    matching_funds_required: bool = False
    matching_funds_percent: Optional[float] = None
    local_registration_required_in: List[str] = []   # ISO country codes
    required_certifications: List[str] = []

class StandardGrantAmount(BaseModel):
    original_min: Optional[float] = None
    original_max: Optional[float] = None
    original_currency: Optional[str] = None            # ISO 4217; None if not stated
    min_amount_usd: Optional[float] = None
    max_amount_usd: Optional[float] = None
    fx_rate_used: Optional[float] = None
    fx_rate_date: Optional[date] = None

class Attachment(BaseModel):
    url: HttpUrl; filename: str; content_hash: str; text_chars: int; parsed_ok: bool

class SourceRef(BaseModel):
    source_id: str; url: HttpUrl; first_seen_at: datetime; last_seen_at: datetime

class RelevanceBreakdown(BaseModel):
    geographic_score: int = Field(..., ge=0, le=100)
    thematic_score: int = Field(..., ge=0, le=100)
    eligibility_score: int = Field(..., ge=0, le=100)
    financial_score: int = Field(..., ge=0, le=100)
    composite_score: int = Field(..., ge=0, le=100)
    gated_to_zero: bool = False
    gate_reasons: List[str] = []          # superfilter / dealbreaker reasons
    matching_pillars: List[str] = []
    summary_justification: str
    profile_version: str

class GrantRecord(BaseModel):
    grant_id: str                          # sha256 of Tier B fingerprint (module 11)
    record_type: RecordType
    grant_title: str
    funder_name: str
    funder_name_normalized: str
    funder_iati_id: Optional[str] = None
    canonical_url: HttpUrl
    sources: List[SourceRef]
    amount_details: StandardGrantAmount
    categories: List[GrantCategory]
    geographic_scopes: List[GeographicScope]
    eligible_applicants: List[ApplicantEligibility]
    eligibility_text: str                  # verbatim excerpt, <= 1500 chars
    deadline_type: DeadlineType
    opening_date: Optional[date] = None
    closing_date: Optional[date] = None
    closing_date_confidence: float = Field(..., ge=0, le=1)
    lifecycle_status: LifecycleStatus
    application_method: str
    required_attachments: List[str] = []
    attachments: List[Attachment] = []
    superfilter_blockers: OrganizationalSuperfilterBlockers
    relevance_analysis: Optional[RelevanceBreakdown] = None
    review_status: ReviewStatus
    extraction_status: str                 # OK | RETRIED_OK | FAILED
    extraction_confidence: float = Field(..., ge=0, le=1)
    model_used: str
    extracted_at: datetime
    scored_at: Optional[datetime] = None
    last_checked_at: datetime
    content_hash: str                      # sha256 of page markdown + attachment text
```

**v2 → v3 changes** (context for anyone who's seen the older schema):
`record_type`, `lifecycle_status`, `sources[]`, `attachments[]`,
`profile_version`, `extraction_status` added; self-reported confidence
replaced by computed confidence; `model_used` has no default (must always be
explicitly the model that ran).

### Postgres table `grant_records`

Mirrors the Pydantic model; nested objects (`amount_details`,
`superfilter_blockers`, `relevance_analysis`, `sources`, `attachments`) stored
as `jsonb` columns; scalar fields as native columns for indexing/filtering
(`review_status`, `lifecycle_status`, `closing_date`, `composite_score` pulled
out of `relevance_analysis` for query performance).

## 7. Functional Requirements

### 7.1 Model selection (Phase 1 experiment)

1. Candidates, all served by the existing Ollama host over Tailscale: current
   Qwen instruct models at 7B and 14B, Mistral 7B v0.3 as the baseline, plus
   one further candidate the harness makes cheap to add. (v2 wrongly fixed the
   model as `mistral:7b-instruct-v0.3-q4_K_M` — the v3 schema's five
   enumerations, multi-select region list, currency normalization, and nested
   objects mean a 2024-generation 7B q4 model will produce schema-valid but
   frequently *wrong* output, so model choice must be empirically tested.)
2. **Selection metric**: field-level extraction accuracy on the golden set
   (module 15), **weighted toward** `closing_date`, `geographic_scopes`,
   `eligible_applicants`, and `amount` fields — these matter more than, e.g.,
   `application_method` accuracy.
3. **Throughput floor**: ≥ 8 records/minute on the office GPU — a model that
   scores higher on accuracy but fails this floor is disqualified.
4. `model_used` is recorded on every record. A model change triggers a
   mandatory golden-set re-run and report (module 15) **before promotion** to
   production use.

### 7.2 Extraction procedure

1. **Constrained decoding**: use Ollama's JSON-schema `format` parameter (or
   GBNF when running llama.cpp directly), with the schema generated
   programmatically from the `GrantRecord` Pydantic model (or the relevant
   pass-1/pass-2 subset — see below) — never hand-maintain a duplicate JSON
   schema.
2. **Retry policy**: one retry on validation failure, with the validation
   errors appended to the prompt so the model can self-correct. A second
   failure sets `extraction_status = FAILED`, stores the raw snapshot for
   human review, and does **not** produce a usable `GrantRecord` for scoring.
   A first-try success is `extraction_status = OK`; a retry success is
   `RETRIED_OK`.
3. **Two-pass extraction**:
   - **Pass 1** extracts factual fields only: `grant_title`, `funder_name`,
     dates, `amount_details`, `eligibility_text`, `geographic_scopes`,
     `attachments` references, `application_method`, `required_attachments`,
     `superfilter_blockers`. No org-profile context is needed for pass 1.
   - **Pass 2** takes the validated pass-1 record **plus the org profile**
     (module 01) and produces `relevance_analysis` (the `RelevanceBreakdown`
     object) — specifically the `summary_justification`, `matching_pillars`,
     and gate-reason narrative; the *numeric* scoring itself (composite,
     per-vector scores, gate firing) is computed deterministically by module
     09, not by the LLM. Keep this split precise: pass 2's LLM role is
     producing the qualitative relevance read and pillar-matching judgment
     that feeds module 09's thematic vector, not computing final scores.
   - Rationale for the split: shorter prompts per pass, and scoring
     (module 09) can be re-run (e.g. after a profile edit or weight
     recalibration) without re-extracting from the source page.
4. **Few-shot prompting**: 3–5 examples drawn from the golden set (module 15)
   and, from Phase 4, from human-corrected records (module 13's few-shot
   bank — rotated weekly, capped at 5 per prompt, selected by category
   diversity).
5. **Computed `extraction_confidence`** (never asked of the model):
   `1.0` minus penalties for:
   - Fields the model left null that the rule layer (module 07) found.
   - Disagreement between two decoding runs at different temperatures on key
     fields — run this dual-decode check **only** for records that land in
     the scoring review band (i.e. don't double LLM cost on every record,
     only borderline ones).
   - Dates that fall outside plausible ranges (e.g. a closing date in the
     past by more than the prefilter's grace period, or more than several
     years in the future).

## 8. Algorithms / Business Logic

### Content hash (used for dedup Tier C and re-check change detection, module 10/11)

```
content_hash = sha256(page_markdown + attachment_text)
```

### Extraction confidence computation

```python
def compute_extraction_confidence(record, rule_layer_findings, dual_decode_result=None) -> float:
    confidence = 1.0
    for field in KEY_FIELDS:
        if getattr(record, field) is None and rule_layer_findings.get(field) is not None:
            confidence -= FIELD_NULL_PENALTY
    if dual_decode_result is not None:
        disagreement_ratio = compare_key_fields(dual_decode_result.run_a, dual_decode_result.run_b)
        confidence -= disagreement_ratio * DISAGREEMENT_PENALTY
    if record.closing_date and not is_plausible_date(record.closing_date):
        confidence -= IMPLAUSIBLE_DATE_PENALTY
    return max(0.0, min(1.0, confidence))
```

### Two-pass flow

```
pass1_record = extract_pass1(page_markdown, attachment_context, few_shot_examples)
validate_or_retry(pass1_record)   # constrained decoding + 1 retry
if pass1_record.extraction_status == "FAILED":
    store_failed(pass1_record, raw_snapshot); return

relevance = extract_pass2(pass1_record, org_profile, few_shot_examples)  # qualitative only
grant_record = merge(pass1_record, relevance_draft=relevance)
grant_record.extraction_confidence = compute_extraction_confidence(...)
grant_record.model_used = MODEL_ID
grant_record.extracted_at = now()
# hand off to module 09 for deterministic scoring, which finalizes relevance_analysis
```

## 9. Configuration

| Setting | Value |
|---|---|
| Retry attempts | 1 (2 total attempts) |
| Few-shot count | 3–5 examples |
| Few-shot rotation (Phase 4+) | Weekly, capped at 5 per prompt, category-diverse |
| Throughput floor | ≥ 8 records/minute |
| Field accuracy target | ≥ 85% on closing_date / geographic_scopes / eligibility |
| Dual-decode confidence check | Review-band records only |

## 10. Suggested Tech Stack & File Layout

```
app/
  extraction/
    __init__.py
    schema.py                # canonical GrantRecord and all sub-models (source of truth)
    ollama_client.py            # constrained decoding wrapper (JSON-schema format param)
    pass1_factual.py               # pass-1 prompt + extraction
    pass2_relevance.py                # pass-2 prompt + extraction (qualitative only)
    confidence.py                       # computed extraction_confidence
    few_shot_bank.py                       # golden-set + human-corrected example selection
    model_baking_off.py                       # Phase 1 model comparison harness hook (calls module 15)
    content_hash.py                              # sha256(markdown + attachment text)
```

## 11. Error Handling & Edge Cases

- Ollama host unreachable: this is a platform-wide alert condition (module
  16), not something this module should retry indefinitely — fail the job,
  requeue per the LLM job queue's policy, and surface via monitoring.
- A model change mid-flight (admin promotes a new model while jobs are
  queued): in-flight jobs finish with the model they started with;
  `model_used` must reflect the actual model that ran, never the currently-
  configured one if they diverge.
- Pass-2 extraction producing a `matching_pillars` list referencing a pillar
  key not present in the current org profile (e.g. profile was edited between
  pass-1 queueing and pass-2 running): validate against the profile version
  loaded at the start of *this specific run*, not a stale cached one.
- Attachment context block empty (module 06 found no attachments, or all
  failed parsing): pass 1 must still run on page content alone — do not block
  extraction on attachment presence.

## 12. Testing & Acceptance Criteria

- Unit tests: constrained decoding correctly rejects and retries on schema
  validation failure; confidence computation matches expected values for
  synthetic penalty scenarios.
- Model bake-off (Phase 1): run all candidate models against the golden set,
  produce a comparison report (module 15), select and document the winner.
- Acceptance (Phase 1): chosen model achieves ≥ 85% field accuracy on the
  three weighted fields and ≥ 8 records/minute throughput.
- Acceptance (Phase 3): two-pass extraction live end-to-end, `extraction_status`
  and computed `extraction_confidence` populated correctly on real records,
  attachment context materially used in pass 1.
- Regression: any prompt, model, or few-shot-bank change re-runs the golden
  set (module 15) before being promoted to production.

## 13. Open Questions

- The "one further candidate the harness makes cheap to add" beyond Qwen
  7B/14B and Mistral 7B v0.3 is unspecified — the harness (module 15) should
  be built so adding a new candidate model is a config change, not a code
  change, regardless of which specific model is chosen later.
- VRAM on the office PC bounds whether the 14B Qwen candidate is even viable
  in the bake-off (platform-wide open question, see README and module 16).

## 14. Implementation Checklist

- [ ] Define canonical `GrantRecord` schema and all sub-models exactly as specified.
- [ ] Implement Ollama constrained-decoding client with JSON-schema `format` param.
- [ ] Implement pass-1 factual extraction with retry-on-validation-failure.
- [ ] Implement pass-2 relevance extraction (qualitative fields only, not numeric scoring).
- [ ] Implement computed `extraction_confidence` with the three penalty sources.
- [ ] Implement few-shot bank (golden-set based initially; human-corrected rotation from Phase 4).
- [ ] Run Phase 1 model bake-off against golden set; select and document winning model.
- [ ] Implement content hashing for dedup/re-check use.
- [ ] Tests per §12.
