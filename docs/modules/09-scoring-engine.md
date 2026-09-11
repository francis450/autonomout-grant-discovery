# Module 09: Scoring Engine

## 1. Purpose

Deterministically scores every extracted `GrantRecord` against TOH's org
profile and routes it to `RECOMMENDED`, `NEEDS_REVIEW`, or `ARCHIVED`. Unlike
extraction, scoring is **not** an LLM judgment call for the numbers — it is
gates plus weighted formulas over fields the LLM already extracted (module
08's pass-2 supplies the qualitative pillar-matching judgment; this module
turns that plus the other fields into the actual 0–100 composite score).

## 2. Scope

### In scope
- The four deterministic gates (superfilter, eligibility, geography,
  dealbreaker, lifecycle) that can force `composite_score = 0`.
- The four scoring vectors (Geographic, Thematic, Eligibility, Financial).
- The composite formula and the three-tier `review_status` thresholds.
- Weight/threshold calibration via grid search against the golden set
  (Phase 1) and monthly recalibration (Phase 4, owned jointly with module 13).

### Out of scope
- Producing the qualitative `matching_pillars` / `summary_justification` —
  module 08 pass 2 (this module consumes that output as an input to the
  Thematic vector, it does not generate it).
- The human review decision itself — module 12.
- Storing/serving weight-recalibration history — module 13 owns the feedback-
  loop process that triggers recalibration; this module owns running the grid
  search and applying the result.

## 3. Dependencies

- Module 01 (Org Profile): every gate and vector reads directly from
  `OrgProfile`.
- Module 08 (Extraction Engine): consumes the full `GrantRecord`, especially
  `superfilter_blockers`, `eligible_applicants`, `geographic_scopes`,
  `amount_details`, `categories`/`matching_pillars`, `lifecycle_status`.
- Module 15 (Evaluation Harness): golden set + "would pursue" labels drive the
  Phase 1 grid search that calibrates weights/thresholds.
- Module 13 (Feedback Loop): monthly recalibration re-runs this module's grid
  search against golden set + accumulated human decisions.
- Module 10 (Record Lifecycle): `lifecycle_status` (an input to the lifecycle
  gate) is maintained by module 10; this module reads it, does not write it.

## 4. Roadmap Phase & Exit Criteria

Phase 3 deliverable: "scoring gates and vectors, calibrated weights/
thresholds" alongside two-pass extraction and attachment parsing. Exit
criterion: **RECOMMENDED precision ≥ 60%** on the golden set — this is the
module's primary bar, directly matching the platform-wide precision success
criterion.

Phase 1 also requires the golden set and eval harness (module 15) to exist
first, since weight/threshold calibration (§8) depends on it — treat Phase 1
completion of module 15 as a hard prerequisite.

## 5. Inputs & Outputs

**Inputs**: a `GrantRecord` with pass-1 and pass-2 extraction complete; the
current `OrgProfile` (module 01).

**Outputs**: the finalized `RelevanceBreakdown` (all four vector scores,
composite, gate results) written onto `GrantRecord.relevance_analysis`, plus
`review_status` set to `RECOMMENDED` / `NEEDS_REVIEW` / `ARCHIVED`, and
`scored_at` timestamp.

## 6. Data Model

Scoring writes into the `RelevanceBreakdown` model already defined in module
08 §6 — reproduced here for reference since this module is its primary
producer:

```python
class RelevanceBreakdown(BaseModel):
    geographic_score: int = Field(..., ge=0, le=100)
    thematic_score: int = Field(..., ge=0, le=100)
    eligibility_score: int = Field(..., ge=0, le=100)
    financial_score: int = Field(..., ge=0, le=100)
    composite_score: int = Field(..., ge=0, le=100)
    gated_to_zero: bool = False
    gate_reasons: List[str] = []
    matching_pillars: List[str] = []
    summary_justification: str
    profile_version: str
```

### Postgres table `scoring_weights` (calibrated, versioned — Phase 1+)

```
scoring_weights
  id                uuid pk
  version           text unique
  geographic_weight  float
  thematic_weight     float
  eligibility_weight   float
  financial_weight      float
  recommended_threshold  int      -- default 70
  review_threshold         int    -- default 45
  calibrated_at              timestamptz
  f1_score                    float   -- against golden set at calibration time
  is_current                    boolean
```

## 7. Functional Requirements

### 7.1 Gates (evaluated first, deterministic, before any vector math)

A gate that fires sets `composite_score = 0`, `gated_to_zero = true`, records
the reason in `gate_reasons`, and routes the record to `review_status =
ARCHIVED`. **Gates are not also subtracted inside the vectors** — this is an
explicit correction from v2, which double-counted eligibility, superfilter,
and dealbreaker penalties both as gates and inside vector math.

1. **Superfilter gate** — fires if any blocker in `superfilter_blockers`
   exceeds the org profile:
   - `min_years_operating_required > (current_year − operating_since)`
   - `audited_financials_years_required > audited_financials_available_years`
   - `annual_budget_usd` outside `[min_annual_budget_floor_usd, max_annual_budget_ceiling_usd]`
   - `matching_funds_required` is true and `org_profile.can_provide_matching_funds` is false
   - `local_registration_required_in` contains a country where TOH has no
     `legal_entities` entry
   - `required_certifications` is not a subset of `org_profile.certifications`
2. **Eligibility gate** — fires if `eligible_applicants` contains **none** of
   `{NGO_501C3, EQUIVALENCY_NGO, INCORPORATED_AFRICA, UNRESTRICTED}`.
3. **Geography gate** — fires if `geographic_scopes` contains **only**
   exclusionary values (`NORTH_AMERICA_ONLY`, `EUROPE_ONLY`,
   `OTHER_REGION_ONLY`).
4. **Dealbreaker gate** — fires if pass-2 extraction lists an explicit
   exclusion naming TOH's situation (e.g. "foreign NGOs excluded," "US-based
   organisations excluded," "individuals only"). **Each dealbreaker must cite
   a verbatim phrase from `eligibility_text`**; a dealbreaker without a
   citation is **downgraded to a review flag, not a gate** — this citation
   requirement is a precision safeguard against the LLM hallucinating
   exclusions.
5. **Lifecycle gate** — fires if `lifecycle_status` is `CLOSED` or
   `WITHDRAWN`.

### 7.2 Vectors (only computed for records that survive all gates)

1. **Geographic (G)**: 100 if `geographic_scopes` includes `KENYA` or
   `EAST_AFRICA`; 90 if `SUB_SAHARAN_AFRICA` or `AFRICA`; 75 if
   `GLOBAL_DEVELOPING` or `UNRESTRICTED`; 0 otherwise (this last case is
   already excluded by the geography gate, so 0 should not occur in practice
   for a gate-surviving record — treat it as a defensive default, not a live
   path).
2. **Thematic (T)**: `T = 100 × max(pillar_weight for matched pillars) + 10 ×
   (count of additional matched pillars beyond the top one)`, capped at 100.
   A perfect single-pillar match (weight 1.0) scores 100 outright — this is
   an explicit correction from v2, whose mean-of-indicators approach wrongly
   penalized a perfect single-pillar match down to 25.
3. **Eligibility (E)**: 100 if `NGO_501C3` or `EQUIVALENCY_NGO` is listed
   explicitly; 85 if only `INCORPORATED_AFRICA` is listed (the Kenyan entity
   applies); 60 if only `UNRESTRICTED` (eligibility is vague, needs human
   confirmation).
4. **Financial (F)**: using `max_amount_usd` when present, else
   `min_amount_usd`: 100 inside `[ideal_min, ideal_max]`; 70 between
   `ideal_max` and `hard_max`; 50 between $2,000 and `ideal_min`; 30 below
   $2,000 or above `hard_max`; 60 when no amount is stated at all.

### 7.3 Composite and thresholds

```
composite = round(0.30*G + 0.35*T + 0.15*E + 0.20*F)      # weights sum to 1.0
if any gate fired: composite = 0

composite >= 70            -> review_status = RECOMMENDED   (queue, flagged as strong)
45 <= composite < 70       -> review_status = NEEDS_REVIEW  (queue)
composite < 45             -> review_status = ARCHIVED      (searchable, not shown)
```

**These weights (0.30/0.35/0.15/0.20) and thresholds (70/45) are
provisional defaults**, not final values — Phase 1 calibrates them (§8).
Regardless of calibration outcome: **nothing is auto-approved**.
`RECOMMENDED` still passes through a human (module 12) before it counts as a
lead — this module never writes `review_status = APPROVED` itself.

## 8. Algorithms / Business Logic

### Scoring pipeline

```python
def score_record(record: GrantRecord, profile: OrgProfile, weights: ScoringWeights) -> RelevanceBreakdown:
    gate_reasons = []
    if superfilter_gate(record, profile): gate_reasons.append("superfilter")
    if eligibility_gate(record): gate_reasons.append("eligibility")
    if geography_gate(record): gate_reasons.append("geography")
    dealbreaker_reason = dealbreaker_gate(record)   # only counts if citation is verbatim-verified
    if dealbreaker_reason: gate_reasons.append(dealbreaker_reason)
    if lifecycle_gate(record): gate_reasons.append("lifecycle")

    if gate_reasons:
        return RelevanceBreakdown(geographic_score=0, thematic_score=0, eligibility_score=0,
                                   financial_score=0, composite_score=0, gated_to_zero=True,
                                   gate_reasons=gate_reasons, matching_pillars=record.relevance_analysis.matching_pillars,
                                   summary_justification=record.relevance_analysis.summary_justification,
                                   profile_version=profile.profile_version)

    g = geographic_score(record.geographic_scopes)
    t = thematic_score(record.categories, record.relevance_analysis.matching_pillars, profile.pillars)
    e = eligibility_score(record.eligible_applicants)
    f = financial_score(record.amount_details, profile.award_range_usd)
    composite = round(weights.geographic_weight*g + weights.thematic_weight*t +
                       weights.eligibility_weight*e + weights.financial_weight*f)

    return RelevanceBreakdown(geographic_score=g, thematic_score=t, eligibility_score=e,
                               financial_score=f, composite_score=composite, gated_to_zero=False,
                               gate_reasons=[], matching_pillars=record.relevance_analysis.matching_pillars,
                               summary_justification=record.relevance_analysis.summary_justification,
                               profile_version=profile.profile_version)

def route_review_status(composite: int, gated: bool) -> ReviewStatus:
    if gated: return ReviewStatus.ARCHIVED
    if composite >= weights.recommended_threshold: return ReviewStatus.RECOMMENDED
    if composite >= weights.review_threshold: return ReviewStatus.NEEDS_REVIEW
    return ReviewStatus.ARCHIVED
```

### Dealbreaker citation verification

```python
def dealbreaker_gate(record: GrantRecord) -> Optional[str]:
    for claimed_exclusion in record.relevance_analysis.dealbreaker_claims:  # from pass-2 output
        if claimed_exclusion.cited_phrase in record.eligibility_text:
            return f"dealbreaker: {claimed_exclusion.reason}"
    # citation not found verbatim -> downgrade to review flag, not a gate
    flag_for_review(record, reason="uncited_dealbreaker_claim")
    return None
```

Note: `dealbreaker_claims` with `cited_phrase` is a pass-2 (module 08) output
field supporting this gate — ensure module 08's pass-2 schema includes it even
though it's not enumerated in the top-level `RelevanceBreakdown` fields listed
in §6 (the design doc's gate description implies this structure; implement it
as an internal pass-2 output consumed here, not necessarily persisted
separately).

### Weight/threshold calibration (Phase 1, and monthly from Phase 4)

Grid search over weights (step 0.05, constrained to sum to 1.0) and
thresholds (step 5), maximizing **F1** against the golden set's "would
pursue" label (module 15). Phase 4 monthly recalibration re-runs this same
search over golden set **plus all accumulated human decisions**; a change is
applied only if F1 improves by **≥ 2 points**, and the result is reported
(module 13 owns triggering this cadence; this module owns the search itself).

```python
def calibrate_weights(golden_set, human_decisions=None) -> ScoringWeights:
    labeled_set = golden_set + (human_decisions or [])
    best = None
    for weights in grid(step=0.05, sum_to=1.0, dims=4):
        for rec_thresh, rev_thresh in grid_thresholds(step=5):
            predictions = [route_review_status(score_record(r, profile, weights).composite_score, ...) for r in labeled_set]
            f1 = compute_f1(predictions, labels=[r.would_pursue for r in labeled_set])
            if best is None or f1 > best.f1:
                best = CalibrationResult(weights, rec_thresh, rev_thresh, f1)
    return best
```

## 9. Configuration

| Setting | Default (provisional) | Notes |
|---|---|---|
| Geographic weight | 0.30 | Calibrated in Phase 1 |
| Thematic weight | 0.35 | Calibrated in Phase 1 |
| Eligibility weight | 0.15 | Calibrated in Phase 1 |
| Financial weight | 0.20 | Calibrated in Phase 1 |
| RECOMMENDED threshold | 70 | Calibrated in Phase 1 |
| NEEDS_REVIEW threshold | 45 | Calibrated in Phase 1 |
| Recalibration cadence (Phase 4+) | Monthly | Apply only if F1 improves ≥ 2 points |

## 10. Suggested Tech Stack & File Layout

```
app/
  scoring/
    __init__.py
    gates.py              # superfilter, eligibility, geography, dealbreaker, lifecycle
    vectors.py               # geographic_score, thematic_score, eligibility_score, financial_score
    composite.py                # weighted sum + threshold routing
    calibration.py                 # grid search over weights/thresholds against golden set
    weights_repository.py             # scoring_weights table CRUD, versioning
    schema.py                            # (references module 08's RelevanceBreakdown)
```

## 11. Error Handling & Edge Cases

- A record with `amount_details.min_amount_usd` and `max_amount_usd` both
  null and no original currency stated at all: Financial vector uses the
  "no amount stated" branch (score 60) — do not error or default to 0.
- Multiple gates fire simultaneously: record **all** reasons in
  `gate_reasons`, not just the first one found — this matters for module 13's
  feedback analysis (which gate is most commonly responsible for archiving).
- A profile edit lands between pass-2 extraction and scoring: always load the
  org profile fresh at scoring time and stamp its `profile_version` onto the
  result — scoring must reflect the profile version active *at scoring time*,
  not extraction time.
- Thematic vector when `matching_pillars` is empty (pass-2 found no thematic
  match at all): `T = 0`; this is a legitimate low score, not an error — the
  eligibility/geography gates don't necessarily catch a thematically
  irrelevant grant.
- Grid search cost: a full 4-dimension weight grid at 0.05 steps plus 2
  threshold dimensions at step-5 is a non-trivial search space — ensure the
  scoring function used inside the grid search is fast (pure arithmetic, no
  LLM calls) so calibration runs in reasonable time against a 150–200 record
  golden set.

## 12. Testing & Acceptance Criteria

- Unit tests: each gate fires/doesn't fire correctly at its exact boundary
  conditions (e.g. `min_years_operating_required` exactly equal to years
  operating should NOT fire); each vector's score brackets match the spec
  exactly (e.g. Thematic vector single-pillar-weight-1.0 match scores exactly
  100, not 90 or 110).
- Composite formula test: verify `composite = round(0.30G + 0.35T + 0.15E +
  0.20F)` matches hand-computed examples; verify any fired gate forces
  `composite = 0` regardless of vector scores.
- Calibration test: grid search on a small synthetic labeled set converges to
  known-good weights for a constructed scenario.
- Acceptance (Phase 3): RECOMMENDED precision ≥ 60% on the golden set,
  measured via module 15; zero double-counting of gate penalties inside
  vector math (a specific regression check against the v2 bug it corrects).

## 13. Open Questions

- Whether the Kenyan entity should score `INCORPORATED_AFRICA` eligibility
  at 85 for Kenya-only calls under its own name — this is the same open
  decision flagged in module 01 §13; it directly determines the Eligibility
  vector's behavior for a meaningful slice of Kenya-only opportunities.
- Exact grid-search step sizes (0.05 weight, 5 threshold) are specified, but
  the search's computational feasibility against the actual golden-set size
  should be validated early in Phase 1 — if too slow, consider a coarser
  first pass followed by a fine pass around the best region.

## 14. Implementation Checklist

- [ ] Implement all five gates exactly per §7.1, with `gate_reasons` capturing every fired gate, not just the first.
- [ ] Implement dealbreaker citation verification (uncited claims downgrade to review flag, never gate).
- [ ] Implement all four vectors exactly per §7.2 score brackets.
- [ ] Implement composite formula + threshold routing with provisional defaults.
- [ ] Implement grid-search calibration against the golden set (module 15).
- [ ] Implement versioned `scoring_weights` storage with `is_current` flag.
- [ ] Wire monthly recalibration trigger from module 13 (Phase 4).
- [ ] Tests per §12, including explicit regression test against the v2 double-counting bug.
