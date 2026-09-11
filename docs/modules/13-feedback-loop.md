# Module 13: Feedback Loop

## 1. Purpose

Closes the loop from human review decisions (module 12) back into the
platform's own accuracy: better few-shot examples, recalibrated scoring
weights, decaying source precision, and candidate prefilter rules. Without
this module, every correction a reviewer makes is a one-off fix that the
platform never learns from.

## 2. Scope

### In scope
- The few-shot bank: turning approved/corrected records into extraction
  prompt examples.
- Monthly scoring-weight recalibration trigger (delegates the actual grid
  search to module 09).
- Source precision decrementing from rejection reasons.
- Prefilter rule-candidate queuing from "not a grant" rejections on
  rule-passed records.

### Out of scope
- Capturing the review decision itself — module 12 (this module consumes
  `review_decisions` rows, it doesn't create them).
- Running the grid search — module 09 owns the calibration algorithm; this
  module owns *triggering* it monthly and applying the ≥ 2-point F1
  improvement gate.
- Computing the source health thresholds/transitions — module 02 owns that;
  this module only decrements the precision-ratio *input* to module 02's
  computation.
- Actually adding a new prefilter rule — an admin does that manually per the
  design's explicit "rules are added by the admin, never automatically."
  This module only queues the candidate.

## 3. Dependencies

- Module 12 (Review App): source of every `review_decisions` event this
  module reacts to.
- Module 08 (Extraction Engine): consumer of the few-shot bank this module
  maintains.
- Module 09 (Scoring Engine): owns and executes the grid search this module
  triggers monthly.
- Module 02 (Source Registry): consumer of the precision-ratio decrements
  this module writes.
- Module 07 (Deterministic Pre-Filter): destination (conceptually) of the
  rule-candidates this module queues — an admin reviewing module 07's rules
  is the actual consumer.
- Module 15 (Evaluation Harness): golden set is combined with accumulated
  human decisions for the monthly recalibration re-run.

## 4. Roadmap Phase & Exit Criteria

Phase 4 deliverable: "few-shot bank" is explicit; monthly weight
recalibration, source precision feedback, and prefilter rule-candidate
queuing are all described under "9.3 Feedback loop (concrete mechanisms)" in
the design doc, which the roadmap situates in Phase 4 alongside the review
app itself (this module has no meaningful input before the review app
exists and is producing decisions).

## 5. Inputs & Outputs

**Inputs**: `review_decisions` rows (module 12) — approvals with corrections,
rejections with reason codes.

**Outputs**: an updated few-shot bank (consumed by module 08); a monthly
scoring-weight recalibration (delegated to module 09, applied only if it
clears the F1 bar); source precision-ratio decrements (consumed by module
02); queued prefilter rule candidates (surfaced to the admin).

## 6. Data Model

### Postgres table `few_shot_bank`

```
few_shot_bank
  id                  uuid pk
  grant_record_id       uuid fk -> grant_records.id
  category                text        -- GrantCategory value, for diversity selection
  added_at                  timestamptz
  source                       text    -- 'golden_set' | 'human_corrected'
  active                          boolean   -- rotated in/out weekly
```

### Postgres table `prefilter_rule_candidates`

```
prefilter_rule_candidates
  id                 uuid pk
  grant_record_id      uuid fk -> grant_records.id
  triggering_reason      text      -- always 'not_a_grant' rejection on a rule-passed record
  page_url                  text
  page_excerpt                 text     -- for admin review, not full page
  status                          text  -- 'pending' | 'accepted' | 'dismissed'
  reviewed_by                       text null
  created_at                           timestamptz
```

### Recalibration run log (extends module 09's `scoring_weights` history)

```
recalibration_runs
  id                  uuid pk
  run_at                timestamptz
  triggered_by            text        -- 'monthly_schedule'
  golden_set_f1              float
  new_weights_f1                float
  applied                          boolean   -- true only if improvement >= 2 points
  report_url                          text     -- link to module 15's generated report
```

## 7. Functional Requirements

### 7.1 Few-shot bank

1. **Population**: when a review decision is `approved` **and** includes
   `field_corrections`, add the corrected record to `few_shot_bank` with
   `source = 'human_corrected'`.
2. **Rotation**: weekly job selects active examples for module 08's prompts,
   **capped at 5 per prompt**, **selected by category diversity** (i.e.
   don't let 5 examples all be `E_WASTE_RECYCLING` — sample across
   represented `GrantCategory` values).
3. **Combination with golden set**: golden-set examples (module 15) remain
   available as a fallback/baseline source; human-corrected examples are
   preferred once enough accumulate, per the diversity selection rule.

### 7.2 Weight recalibration (monthly)

1. **Trigger**: monthly schedule (module 16's scheduler) invokes module 09's
   grid search (§8 in module 09) over the golden set **plus all human
   decisions** accumulated since the platform went live.
2. **Application gate**: a new weight set is applied **only if F1 improves
   by ≥ 2 points** versus the currently active weights, and this must be
   **reported** (via module 15's report mechanism) regardless of whether it
   was applied — a "no improvement found" run is itself a useful reported
   outcome, not a silent no-op.
3. **Non-application**: if the ≥ 2-point bar isn't cleared, the current
   `scoring_weights.is_current` row stays unchanged; log the attempt in
   `recalibration_runs` with `applied = false`.

### 7.3 Source precision feedback

1. Every `review_decisions` row with `decision = 'rejected'` and
   `reason_code` in `{'expired', 'not_a_grant'}` decrements the originating
   source's precision-ratio input (identify the source via the record's
   `sources[]` — if multiple sources contributed, decrement the one
   currently marked canonical/primary, or all contributing sources if
   ambiguous — see §11 for the tie-break rule).
2. This decrement feeds directly into module 02's rolling precision-ratio
   metric and its `< 10% over 100 records → QUARANTINED` threshold — this
   module does not itself quarantine anything, it only supplies the signal.

### 7.4 Prefilter rule candidates

1. Every `review_decisions` row with `decision = 'rejected'`,
   `reason_code = 'not_a_grant'`, **where the record's `record_type` was
   decided by the rule layer as `passed = true`** (i.e. the prefilter's rule
   layer let it through, but a human determined it isn't actually a grant):
   queue a `prefilter_rule_candidates` row with the page excerpt for admin
   review.
2. **Rules are added by the admin, never automatically** — this module's
   job ends at queuing the candidate; a human decides whether to actually
   add a new rule to module 07's rule layer.

## 8. Algorithms / Business Logic

### Few-shot rotation (weekly)

```python
def rotate_few_shot_bank():
    active_by_category = defaultdict(list)
    candidates = few_shot_bank.query(source="human_corrected", order_by="added_at desc")
    for c in candidates:
        if len(active_by_category[c.category]) < PER_CATEGORY_CAP:
            active_by_category[c.category].append(c)
    selected = flatten(active_by_category.values())[:5]   # cap 5 total, diversity-first
    if len(selected) < 5:
        selected += golden_set_fallback_examples(needed=5 - len(selected))
    few_shot_bank.set_active(selected)
```

### Monthly recalibration

```python
def monthly_recalibration():
    current_weights = scoring_weights.get_current()
    human_decisions = review_decisions.query(since=current_weights.calibrated_at)
    result = scoring_engine.calibrate_weights(golden_set, human_decisions)   # module 09
    improvement = result.f1 - current_weights.f1_score
    applied = improvement >= 2.0
    if applied:
        scoring_weights.insert_new_version(result, is_current=True)
    recalibration_runs.insert(triggered_by="monthly_schedule", golden_set_f1=current_weights.f1_score,
                               new_weights_f1=result.f1, applied=applied,
                               report_url=evaluation_harness.generate_report(result))
```

### Source precision decrement

```python
def on_rejection(decision: ReviewDecision, record: GrantRecord):
    if decision.reason_code in ("expired", "not_a_grant"):
        contributing_sources = record.sources  # SourceRef list
        canonical_source = pick_canonical(contributing_sources)  # most recent first_seen, or primary flag
        source_registry.record_rejection(canonical_source.source_id, decision.reason_code)

    if decision.reason_code == "not_a_grant" and record.record_type_decided_by == "rule" and record.record_type_passed:
        prefilter_rule_candidates.insert(record.grant_id, triggering_reason="not_a_grant",
                                          page_url=record.canonical_url, page_excerpt=excerpt(record))
```

## 9. Configuration

| Setting | Value |
|---|---|
| Few-shot cap per prompt | 5 |
| Few-shot rotation cadence | Weekly |
| Recalibration cadence | Monthly |
| Recalibration application threshold | ≥ 2 F1 points improvement |
| Precision-decrement trigger reasons | `expired`, `not_a_grant` |
| Rule-candidate trigger | `not_a_grant` rejection on a rule-passed record |

## 10. Suggested Tech Stack & File Layout

```
app/
  feedback_loop/
    __init__.py
    few_shot_bank.py          # population + weekly rotation with category diversity
    recalibration.py             # monthly trigger, delegates to module 09, applies F1 gate
    source_precision.py             # rejection -> module 02 precision decrement
    rule_candidates.py                 # not_a_grant + rule-passed -> queued candidate
    event_listener.py                     # subscribes to / polls review_decisions inserts
```

## 11. Error Handling & Edge Cases

- A rejected record with multiple contributing `sources[]` (post-Tier-B
  merge) — precision decrement tie-break: decrement the source with the
  **earliest `first_seen_at`** (treat it as the "originating" source for
  precision purposes) rather than an arbitrary or most-recent choice; this
  should be documented as the explicit rule in code, not left ambiguous.
- A `field_corrections` entry that corrects a field to an *invalid* value
  somehow reaching this module (shouldn't happen if module 12 validates
  enum fields, but defensively): skip that record for few-shot bank
  inclusion rather than poisoning the prompt bank with a bad example.
- Recalibration run coincides with an org-profile edit (module 01) mid-run:
  use the org profile version that was current when the recalibration
  **started**, consistent with module 09's own "load fresh, stamp version"
  behavior — do not let a concurrent edit produce an inconsistent
  calibration result.
- Monthly recalibration finding a *worse* F1 than current (regression in the
  candidate weights): never apply — the ≥ 2-point-improvement gate already
  protects against this, but explicitly test the negative-improvement case.

## 12. Testing & Acceptance Criteria

- Unit tests: few-shot rotation correctly enforces the 5-item cap and
  category diversity; source precision decrement correctly picks the
  earliest-`first_seen_at` contributing source; rule-candidate queuing
  correctly filters to `not_a_grant` + rule-passed records only (not model-
  decided ones).
- Integration test: a full monthly recalibration cycle against a synthetic
  golden set + decisions, verifying the ≥ 2-point gate is enforced both ways
  (applies on clear improvement, doesn't apply on marginal/negative change).
- Acceptance (Phase 4): after several weeks of real review activity, the
  few-shot bank contains human-corrected examples visibly improving
  extraction accuracy (measured via module 15); at least one monthly
  recalibration report has been generated (applied or not); source
  precision decrements are visibly affecting module 02's health metrics.

## 13. Open Questions

None specific to this module beyond the tie-break rule in §11 (earliest
`first_seen_at` as canonical source for precision decrement), which the
design doc doesn't specify explicitly and this document resolves with a
documented default — confirm with the team if a different rule (e.g.
decrement all contributing sources proportionally) is preferred before
building.

## 14. Implementation Checklist

- [ ] Implement `review_decisions` event consumption (subscription or polling).
- [ ] Implement few-shot bank population from approved+corrected decisions.
- [ ] Implement weekly rotation with 5-item cap and category diversity.
- [ ] Implement monthly recalibration trigger delegating to module 09, with the ≥2-point F1 gate.
- [ ] Implement source precision decrement with documented tie-break rule.
- [ ] Implement prefilter rule-candidate queuing, filtered to rule-passed `not_a_grant` rejections.
- [ ] Tests per §12.
