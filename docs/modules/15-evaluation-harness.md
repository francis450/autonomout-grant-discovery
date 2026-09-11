# Module 15: Evaluation Harness

## 1. Purpose

The platform's mechanism for proving any change (model, prompt, weight,
threshold, prefilter rule) actually helps rather than quietly regressing
quality. Nothing changes in production without a golden-set run backing it up
— this module is what makes that discipline enforceable rather than
aspirational.

## 2. Scope

### In scope
- The golden set: collection, labelling UI/process, and its composition
  requirements.
- Extraction metrics (per-field accuracy, schema-valid rate, retry rate,
  throughput).
- Prefilter metrics (recall, junk rejection rate).
- Scoring metrics (precision/recall of RECOMMENDED, score-distribution
  separation, F1).
- Dedup metrics (duplicate pairs found/seeded, false merges).
- The one-command harness runner and its dated report output.

### Out of scope
- The extraction/scoring/prefilter/dedup logic being measured — modules 07,
  08, 09, 11 own their own logic; this module only measures it.
- Labelling UI hosting — reuses module 12's review app infrastructure ("not a
  spreadsheet" is explicit in the design doc) rather than building a separate
  tool.

## 3. Dependencies

- Module 12 (Review App): hosts the golden-set labelling UI.
- Module 07 (Deterministic Pre-Filter): subject of prefilter metrics.
- Module 08 (Extraction Engine): subject of extraction metrics; consumes
  golden-set few-shot examples and drives the Phase 1 model bake-off.
- Module 09 (Scoring Engine): subject of scoring metrics; consumes the golden
  set for weight/threshold grid-search calibration.
- Module 11 (Deduplication): subject of dedup metrics.
- Module 13 (Feedback Loop): triggers monthly recalibration runs through this
  module's report mechanism.

## 4. Roadmap Phase & Exit Criteria

Phase 1 deliverable: "golden set collection and labelling UI (minimal), eval
harness, model bake-off." Exit criterion: **golden set ≥ 150 labelled**;
chosen model ≥ 85% field accuracy on `closing_date`/`geographic_scopes`/
`eligibility`; throughput ≥ 8 records/min. This module must exist and be
populated **before** modules 07, 08, 09 can be validated against their own
Phase 2/3 exit criteria — treat it as a true prerequisite, not a
parallel-track deliverable.

## 5. Inputs & Outputs

**Inputs**: real pages labelled by the grants team (150–200 target); a named
model + prompt version + profile version to evaluate.

**Outputs**: a dated report (per run) covering extraction, prefilter,
scoring, and dedup metrics, required before any model/prompt/weight/
threshold change is promoted.

## 6. Data Model

### Golden set composition requirements (150–200 real pages)

Coverage required across:
- Geography: Kenya/East Africa, pan-African, global, US-only, and EU sources.
- Page type: opportunity vs non-opportunity pages.
- Deadline type: fixed, rolling, and unknown deadlines.
- At least **30** with PDF attachments.
- At least **40** that the team marks **"would pursue"**.

Labels include **ground-truth field values**, not just a yes/no — i.e. every
labelled page has a full hand-verified `GrantRecord`-shaped label, not merely
an opportunity/non-opportunity tag.

### Postgres table `golden_set_pages`

```
golden_set_pages
  id                 uuid pk
  url                  text
  page_snapshot          text          -- raw markdown at labelling time
  attachments               jsonb        -- attachment snapshots at labelling time
  labelled_by                 text
  labelled_at                   timestamptz
  ground_truth_record             jsonb   -- full GrantRecord-shaped ground truth
  would_pursue                      boolean
  geography_tag                       text  -- 'kenya_east_africa' | 'pan_african' | 'global' | 'us_only' | 'eu'
  has_pdf_attachment                    boolean
  deadline_type_tag                       text -- fixed | rolling | unknown
  is_opportunity                            boolean
```

### Postgres table `eval_reports`

```
eval_reports
  id                    uuid pk
  run_at                  timestamptz
  model_used                text
  prompt_version               text
  profile_version                  text
  extraction_metrics                  jsonb
  prefilter_metrics                     jsonb
  scoring_metrics                         jsonb
  dedup_metrics                             jsonb
  report_path                                 text   -- generated report file location
```

## 7. Functional Requirements

1. **Golden set collection**: the grants team labels real pages **in the
   review app** (module 12), not a spreadsheet — reuse module 12's Record
   view UI pattern for labelling (structured fields beside rendered page
   content), extended with a "this is ground truth" mode.
2. **Coverage tracking**: the labelling UI/process must track progress
   against each coverage dimension (§6) so labellers know what's still
   under-represented (e.g. "need 8 more EU-source pages," "need 12 more
   PDF-attachment pages") rather than labelling arbitrarily until hitting
   150.
3. **Extraction metrics**:
   - Per-field exact/near match: dates ±0 days, amounts ±5%, enums exact,
     lists by Jaccard similarity.
   - Schema-valid rate (fraction of extractions that validate against the
     Pydantic schema, first-try or after retry).
   - Retry rate (fraction requiring the one retry).
   - Throughput (records/minute).
4. **Prefilter metrics**:
   - Recall on live opportunities (target ≥ 98%) — fraction of golden-set
     records labelled `is_opportunity=true` that the prefilter did not
     reject.
   - Rejection rate on junk (target ≥ 70%) — fraction of golden-set records
     labelled `is_opportunity=false` that the prefilter correctly rejected.
5. **Scoring metrics**:
   - Precision and recall of `RECOMMENDED` against the `would_pursue` label.
   - Separation of score distributions between pursued and rejected records
     (e.g. report the distribution overlap/statistical separation, not just
     a single number — this is what tells you whether the scoring formula
     is discriminative at all).
   - F1 at the chosen thresholds.
6. **Dedup metrics**:
   - Duplicate pairs found / duplicate pairs deliberately seeded into a test
     set (recall of the dedup mechanism).
   - False merges — **target 0**, matching module 11's hard acceptance bar.
7. **One-command harness**: a single command runs the **whole set** against
   a named `model + prompt_version + profile_version` and writes a **dated
   report**. This report is **required** for any model, prompt, weight, or
   threshold change before it is promoted to production — this is a process
   gate the harness enforces by being the only sanctioned way to produce
   that report.

## 8. Algorithms / Business Logic

### Field-level accuracy scoring

```python
def field_match(field_name: str, predicted, ground_truth) -> bool:
    if field_name in DATE_FIELDS:
        return predicted == ground_truth   # ±0 days = exact
    if field_name in AMOUNT_FIELDS:
        if ground_truth is None: return predicted is None
        return abs(predicted - ground_truth) / max(ground_truth, 1) <= 0.05   # ±5%
    if field_name in ENUM_FIELDS:
        return predicted == ground_truth
    if field_name in LIST_FIELDS:
        return jaccard_similarity(set(predicted), set(ground_truth)) >= JACCARD_MATCH_THRESHOLD
    return predicted == ground_truth

def extraction_accuracy_report(model, prompt_version, golden_set) -> dict:
    results = defaultdict(list)
    for page in golden_set:
        predicted = extraction_engine.extract(page, model=model, prompt_version=prompt_version)
        for field in TRACKED_FIELDS:
            results[field].append(field_match(field, getattr(predicted, field), page.ground_truth_record[field]))
    return {field: mean(matches) for field, matches in results.items()}
```

### Weighted accuracy for model bake-off (module 08's selection metric)

```python
WEIGHTED_FIELDS = {"closing_date": 2.0, "geographic_scopes": 2.0, "eligible_applicants": 2.0, "amount_details": 2.0}

def weighted_score(field_accuracies: dict) -> float:
    total_weight = sum(WEIGHTED_FIELDS.get(f, 1.0) for f in field_accuracies)
    return sum(acc * WEIGHTED_FIELDS.get(f, 1.0) for f, acc in field_accuracies.items()) / total_weight
```

### Full harness run

```python
def run_eval_harness(model, prompt_version, profile_version) -> EvalReport:
    golden_set = golden_set_pages.query_all()
    extraction = extraction_accuracy_report(model, prompt_version, golden_set)
    prefilter = prefilter_metrics(golden_set)
    scoring = scoring_metrics(golden_set, profile_version)
    dedup = dedup_metrics(seeded_duplicate_test_set())
    report = EvalReport(run_at=now(), model_used=model, prompt_version=prompt_version,
                         profile_version=profile_version, extraction_metrics=extraction,
                         prefilter_metrics=prefilter, scoring_metrics=scoring, dedup_metrics=dedup)
    write_dated_report(report)
    eval_reports.insert(report)
    return report
```

## 9. Configuration

| Setting | Value |
|---|---|
| Golden set target size | 150–200 pages |
| Minimum PDF-attachment coverage | 30 pages |
| Minimum "would pursue" coverage | 40 pages |
| Date match tolerance | ±0 days |
| Amount match tolerance | ±5% |
| Prefilter recall target | ≥ 98% |
| Junk rejection target | ≥ 70% |
| Dedup false-merge target | 0 |

## 10. Suggested Tech Stack & File Layout

```
app/
  eval_harness/
    __init__.py
    golden_set_repository.py    # storage + coverage-gap tracking
    extraction_metrics.py           # field-level accuracy, schema-valid rate, throughput
    prefilter_metrics.py               # recall / junk rejection against labels
    scoring_metrics.py                    # precision/recall/F1/distribution separation
    dedup_metrics.py                         # seeded-duplicate recall + false-merge count
    report_generator.py                         # dated report writer
    cli.py                                          # single-command entry point
```

## 11. Error Handling & Edge Cases

- A golden-set page whose ground truth has since become stale relative to
  the live page (e.g. the real grant's deadline actually passed since
  labelling): golden-set pages are **frozen snapshots** (`page_snapshot`
  stored at labelling time) — the harness always evaluates against the
  frozen snapshot and its ground truth, never the live page, so results stay
  reproducible over time regardless of what happens to the source URL later.
- Running the harness against a model/prompt combination that produces
  systematically `FAILED` extractions (e.g. a broken prompt): the harness
  must still produce a report (with a very low schema-valid rate / accuracy)
  rather than crashing — a harness that can't measure a bad change is
  useless exactly when it's needed most.
- Coverage gaps that are hard to fill (e.g. finding 30+ real PDF-attachment
  pages across the required geography spread): track and report gaps
  honestly rather than padding the golden set with low-quality or redundant
  labels just to hit the 150 count.
- Jaccard threshold for list-field "near match" is not numerically specified
  in the design doc — pick a reasonable default (e.g. ≥ 0.7) and document it
  as a tunable constant, not a hardcoded magic number buried in logic.

## 12. Testing & Acceptance Criteria

- Unit tests: field-match functions correctly apply each tolerance rule
  (date exact, amount ±5%, enum exact, list Jaccard) on synthetic
  predicted/ground-truth pairs.
- Meta-test: running the harness twice against the same frozen golden set
  and same model/prompt/profile version produces identical metrics
  (determinism check — critical since this module is the source of truth
  for "did this change help").
- Acceptance (Phase 1): golden set reaches ≥ 150 labelled pages meeting all
  coverage requirements; harness runs end-to-end and produces a dated report
  usable for the model bake-off.
- Acceptance (ongoing): every subsequent model/prompt/weight/threshold
  change in the codebase has a corresponding dated report in `eval_reports`
  — this should be checked as part of the team's own change-review process,
  not just this module's own tests.

## 13. Open Questions

- Exact Jaccard similarity threshold for list-field "near match" scoring —
  not specified in the design doc; propose ≥ 0.7 as a starting default,
  tune based on early Phase 1 results.
- Process enforcement: the design doc says a report is "required" for any
  model/prompt/weight/threshold change, but doesn't specify a technical
  enforcement mechanism (e.g. a CI check, a PR template checklist) — worth
  deciding whether this is a cultural/process rule or something the codebase
  should actually gate on.

## 14. Implementation Checklist

- [ ] Design and build golden-set labelling UI within module 12's review app.
- [ ] Implement coverage-gap tracking against the 6 coverage dimensions.
- [ ] Collect and label 150–200 real pages meeting all coverage minimums.
- [ ] Implement extraction metrics (field accuracy, schema-valid rate, retry rate, throughput).
- [ ] Implement prefilter metrics (recall, junk rejection).
- [ ] Implement scoring metrics (precision/recall/F1, distribution separation).
- [ ] Implement dedup metrics (seeded-duplicate recall, false-merge count).
- [ ] Implement one-command harness runner + dated report generator.
- [ ] Run Phase 1 model bake-off using this harness.
- [ ] Tests per §12, including the determinism meta-test.
