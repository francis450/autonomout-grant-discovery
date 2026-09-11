# Module 07: Deterministic Pre-Filter

## 1. Purpose

Rejects obvious junk cheaply, before any LLM call, so the extraction engine
(module 08) only spends inference budget on plausible opportunities. Because a
false rejection here is invisible to the grants team (they never see what
this module throws away), **the prefilter is tuned for recall**: when unsure,
pass the record through rather than reject it.

## 2. Scope

### In scope
- Record-type classification (opportunity / listing / funder_profile /
  article / tender / other) via a rule layer first, model layer only when
  rules are inconclusive.
- Expiry filtering based on parsed deadline dates.
- Feeding module 03's discovery qualification (this module's classifier is
  reused there).

### Out of scope
- Full field extraction — module 08.
- Scoring/relevance — module 09.
- The eval harness's recall/rejection-rate measurement — module 15 consumes
  this module's decisions but owns the metric computation itself.

## 3. Dependencies

- Module 05 (Tiered Ingestion): supplies fetched page markdown.
- Module 03 (Discovery): calls this module's record-type classifier during
  qualification.
- Module 08 (Extraction Engine): only receives records this module passes
  through; writes `record_type` onto the eventual `GrantRecord`.
- Module 15 (Evaluation Harness): measures this module's recall/rejection-rate
  against the golden set.
- Module 02 (Source Registry): a "not a grant" rejection on a record the rule
  layer *passed* becomes a candidate new rule, fed back via module 13
  (Feedback Loop), which also feeds source precision metrics.

## 4. Roadmap Phase & Exit Criteria

Phase 2 deliverable: "record-type rules and classifier, expiry filter,
lifecycle recompute, Tier A/C dedup, snapshot store." Exit criteria: **prefilter
recall ≥ 98%** on live grants, **junk rejection ≥ 70%**. These two numbers are
the module's primary acceptance bar and must be measured via module 15's
harness before Phase 2 is considered done.

## 5. Inputs & Outputs

**Inputs**: fetched page markdown/content (module 05), URL, page title.

**Outputs**: `record_type` classification + the rule/model that decided it;
a pass/reject decision with `deadline_type` set; rejected pages are logged
(not silently dropped) so recall can be audited against the golden set.

## 6. Data Model

### Output fields (written onto the eventual record, or logged if rejected pre-record)

```python
class PrefilterResult(BaseModel):
    record_type: RecordType            # opportunity | listing | funder_profile | article | tender | other
    record_type_decided_by: str        # 'rule' | 'model'
    record_type_rule_matched: Optional[str] = None   # which rule fired, if rule-decided
    passed: bool
    reject_reason: Optional[str] = None    # e.g. 'expired', 'press_release', 'procurement_tender'
    deadline_type: DeadlineType            # FIXED_DATE | ROLLING | UNKNOWN_UNSPECIFIED
    deadline_found: Optional[date] = None
    deadline_confidence: float             # 0-1, from date-proximity-to-keyword heuristic
```

### Postgres table `prefilter_log`

```
prefilter_log
  id                uuid pk
  fetch_run_id       uuid fk -> fetch_runs.id (module 05)
  url                 text
  record_type          text
  decided_by            text
  passed                 boolean
  reject_reason            text null
  deadline_type              text
  deadline_found               date null
  deadline_confidence            float
  evaluated_at                    timestamptz
```

Logging **every** decision, pass or reject, is required — this is what makes
recall measurable (module 15) and what surfaces "not a grant" rejections for
rule-candidate mining (module 13).

## 7. Functional Requirements

### 7.1 Record-type classifier

1. **Rule layer** (runs first, always): URL patterns, page-title patterns, and
   keyword density reject:
   - Press releases and news articles.
   - Research papers.
   - Procurement/vendor tenders.
   - "How to write a grant" generic advice content.
   - Aggregator index pages containing no application details.
2. **Model layer** (only when rules are inconclusive, i.e. no rule confidently
   classifies the page): a single short classification call using a **200-
   token summary** of the page (not the full markdown) to classify as one of
   `opportunity / listing / funder_profile / article / tender / other`.
3. **Output**: `record_type` stored with which layer (`rule` or `model`)
   decided it, and if a rule, which specific rule matched — required for
   debugging false rejections and for module 13's rule-candidate feedback.

### 7.2 Expiry filter

1. **Date parsing**: use `dateparser` over the page markdown to find candidate
   dates.
2. **Deadline proximity ranking**: rank candidate dates by proximity to
   deadline-related keywords (`"deadline"`, `"closes"`, `"submit by"`,
   `"applications due"`) — the date nearest such a keyword is the deadline
   candidate.
3. **Rejection rule**: reject **only** when a deadline is found with **high
   confidence** and is **more than 14 days in the past**. This 14-day grace
   period exists specifically to cover extended deadlines and late page
   updates.
4. **Ambiguous/missing dates pass through**: set `deadline_type = UNKNOWN` and
   let it proceed — module 08's LLM extraction and module 06's attachment
   parsing are the authority on ambiguous dates, not this rule layer.
5. **Logging for recall measurement**: every rejection here is logged so
   prefilter recall can be measured against the golden set; target ≥ 98%
   recall on live grants (i.e. at most 2% of genuinely live grants are
   wrongly rejected as expired).

## 8. Algorithms / Business Logic

### Record-type rule layer (illustrative structure — exact rule set to be built and tuned against the golden set)

```python
REJECT_RULES = [
    ("press_release", lambda page: url_matches(page.url, PRESS_RELEASE_PATTERNS) or title_matches(page.title, PRESS_TITLE_PATTERNS)),
    ("research_paper", lambda page: keyword_density(page.text, RESEARCH_KEYWORDS) > THRESHOLD),
    ("procurement_tender", lambda page: keyword_density(page.text, PROCUREMENT_KEYWORDS) > THRESHOLD and "grant" not in page.text.lower()),
    ("how_to_write_grant", lambda page: title_matches(page.title, HOWTO_PATTERNS)),
    ("aggregator_index_no_details", lambda page: is_index_page(page) and not has_application_details(page)),
]

def classify_record_type(page) -> PrefilterResult:
    for reason, rule in REJECT_RULES:
        if rule(page):
            return PrefilterResult(record_type=map_reason_to_type(reason), record_type_decided_by="rule",
                                    record_type_rule_matched=reason, passed=(map_reason_to_type(reason)=="opportunity"))
    # inconclusive -> model layer
    summary = summarize(page, max_tokens=200)
    record_type = llm_classify(summary)  # single short call
    return PrefilterResult(record_type=record_type, decided_by="model",
                            passed=record_type in ("opportunity", "listing"))
```

**Recall-first tie-break**: any rule or model uncertainty defaults to
`passed=True`. Only confident rejections count as rejections — this is the
explicit design principle, not an implementation detail to optimize away.

### Expiry filter

```python
def check_expiry(page_markdown: str) -> tuple[DeadlineType, Optional[date], float, bool]:
    candidates = dateparser_search(page_markdown)
    deadline_candidate, confidence = rank_by_keyword_proximity(candidates, DEADLINE_KEYWORDS)
    if deadline_candidate is None or confidence < HIGH_CONFIDENCE_THRESHOLD:
        return DeadlineType.UNKNOWN_UNSPECIFIED, None, confidence, True   # pass through
    days_past = (today() - deadline_candidate).days
    if days_past > 14:
        return DeadlineType.FIXED_DATE, deadline_candidate, confidence, False   # reject
    return DeadlineType.FIXED_DATE, deadline_candidate, confidence, True
```

## 9. Configuration

| Setting | Value |
|---|---|
| Model-layer summary length | 200 tokens |
| Expiry grace period | 14 days past deadline |
| Prefilter recall target | ≥ 98% on live grants |
| Junk rejection target | ≥ 70% |
| High-confidence date threshold | Tunable; calibrate against golden set (module 15) |

## 10. Suggested Tech Stack & File Layout

```
app/
  prefilter/
    __init__.py
    record_type_rules.py     # URL/title/keyword rule layer
    record_type_model.py        # 200-token-summary LLM classification fallback
    expiry_filter.py               # dateparser + keyword-proximity ranking
    schema.py                        # PrefilterResult
    log_repository.py                  # prefilter_log writes/queries
```

`dateparser` for date parsing; reuse module 08's LLM client/queue for the
model-layer classification call (it should go through the same GPU-serialized
job queue as extraction, module 16, since it's still an inference call,
just a short one — prioritize it appropriately in the queue).

## 11. Error Handling & Edge Cases

- A page with multiple conflicting deadline-like dates (e.g. "published
  2024-01-01... deadline 2026-12-01... last updated 2026-09-01"): keyword-
  proximity ranking must correctly favor the date nearest deadline keywords,
  not the most recent or most prominent date on the page.
- Rolling/continuous deadlines ("applications accepted on a rolling basis"):
  must classify as `deadline_type = ROLLING`, not trigger the expiry
  rejection path at all.
- Model layer failures (LLM unreachable/timeout): fail open (pass the record
  through with `record_type = other`, `decided_by = model`, flagged) rather
  than blocking the pipeline — consistent with the recall-first principle.
- A rule fires with low actual precision in practice (discovered via module
  13's "not a grant rejection on a rule-passed record" feedback signal, which
  is the *opposite* problem — a rule that under-rejects). Track rule-level
  precision/recall over time so admins can tune or retire rules.

## 12. Testing & Acceptance Criteria

- Unit tests: each rule in the rule layer correctly fires on representative
  positive/negative examples; expiry filter correctly handles the 14-day
  boundary (exactly 14 days passes, 15 days rejects).
- Golden-set evaluation (via module 15): recall ≥ 98% on live grants,
  rejection rate ≥ 70% on junk — this is the module's binding acceptance
  criterion, not just a nice-to-have metric.
- Regression test: any change to rules or the model-layer prompt must be
  re-validated against the full golden set before merge (this is what module
  15's harness enforces platform-wide).
- Acceptance (Phase 2): prefilter live in the pipeline ahead of module 08,
  measured recall/rejection rates meet targets, all decisions logged and
  auditable.

## 13. Open Questions

None specific beyond the general need to build and iteratively tune the exact
rule set (`REJECT_RULES`, keyword lists, thresholds) against real pages and
the golden set — the design doc specifies the *mechanism* precisely but not
the literal rule contents, which are a Phase 1–2 engineering/tuning task.

## 14. Implementation Checklist

- [ ] Implement record-type rule layer with initial rule set for the 5 junk categories.
- [ ] Implement 200-token page summarizer and model-layer classification fallback.
- [ ] Implement `dateparser`-based expiry filter with keyword-proximity ranking and 14-day grace.
- [ ] Implement `prefilter_log` storage for every decision (pass and reject).
- [ ] Wire recall-first tie-break (uncertain → pass) throughout.
- [ ] Reuse classifier in module 03's discovery qualification path.
- [ ] Validate against golden set via module 15; tune until ≥ 98% recall / ≥ 70% junk rejection.
- [ ] Tests per §12.
