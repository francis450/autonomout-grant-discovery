# Module 10: Record Lifecycle & Re-checks

## 1. Purpose

Grants are not static once extracted — deadlines pass, pages get updated,
pages disappear, calls reopen annually. This module keeps every
`GrantRecord`'s `lifecycle_status` current and decides, per record, when it's
worth re-fetching the source page to catch changes, so the platform doesn't
show the grants team a stale or expired opportunity as if it were fresh.

## 2. Scope

### In scope
- Nightly recomputation of `lifecycle_status` from `closing_date` and
  `deadline_type`.
- The re-check cadence policy (which records get re-fetched, how often).
- Diffing key fields on content change and writing history.
- The "watch for reopening" mechanism for annually-recurring CLOSED grants.

### Out of scope
- Actually performing the re-fetch — module 05 (Tiered Ingestion) executes
  the fetch this module schedules.
- Deciding if a re-fetched page still classifies as an opportunity — module
  07 (its `record_type` output feeds the `WITHDRAWN` transition here).
- The composite score itself — module 09 (a re-extraction triggered here may
  lead to re-scoring, but this module doesn't compute scores).

## 3. Dependencies

- Module 08 (Extraction Engine): re-extraction (pass 1 only, typically) is
  triggered here when `content_hash` changes; this module reads/writes
  `GrantRecord.lifecycle_status`, `closing_date`, `content_hash`,
  `last_checked_at`.
- Module 05 (Tiered Ingestion): performs the actual re-fetch this module
  schedules.
- Module 07 (Deterministic Pre-Filter): a page that no longer classifies as
  `opportunity` on re-check contributes to the `WITHDRAWN` transition.
- Module 09 (Scoring Engine): a deadline or amount change on a queued record
  triggers a review flag, and typically a re-score.
- Module 12 (Review App): displays lifecycle status and history diffs;
  surfaces review flags this module raises.
- Module 16 (Runtime & Operations): nightly scheduler trigger.

## 4. Roadmap Phase & Exit Criteria

Phase 2 deliverable: "lifecycle recompute" alongside prefilter rules and
Tier A/C dedup. No standalone numeric exit criterion of its own in the
roadmap table, but it is required scaffolding for Phase 3's scoring gates
(the lifecycle gate in module 09 depends on accurate `lifecycle_status`) and
for the platform's 48-hour latency success criterion (re-checks must be
timely enough that `CLOSING_SOON` records get attention).

## 5. Inputs & Outputs

**Inputs**: `closing_date`, `deadline_type` on every `GrantRecord`; page-fetch
results from re-check runs (module 05); 404/410 responses; re-classification
results (module 07).

**Outputs**: updated `lifecycle_status`; a `record_history` diff entry when
content changes; review flags on deadline/amount changes; scheduled re-check
jobs at the correct cadence; "watch for reopening" reminders.

## 6. Data Model

### Lifecycle status recompute (writes `GrantRecord.lifecycle_status`)

Uses the `LifecycleStatus` enum already defined in module 08 §6:
`OPEN | CLOSING_SOON | CLOSED | UNKNOWN | WITHDRAWN`.

### Postgres table `record_history` (append-only)

```
record_history
  id                 uuid pk
  grant_record_id     uuid fk -> grant_records.id
  changed_at            timestamptz
  change_type             text        -- 'recheck_diff' | 'lifecycle_transition' | 'reopening_watch_created'
  field_name                text null   -- for recheck_diff entries, e.g. 'closing_date'
  old_value                   text null
  new_value                     text null
  triggered_review_flag           boolean
```

### Postgres table `reopening_watches`

```
reopening_watches
  id                    uuid pk
  original_record_id     uuid fk -> grant_records.id
  funder_name_normalized   text
  title_normalized           text
  closed_at                    date
  watch_due_at                   date    -- closed_at + 11 months
  status                          text    -- 'pending' | 'checked_reopened' | 'checked_not_reopened'
```

## 7. Functional Requirements

1. **Nightly lifecycle recompute**, applied to every record with a
   non-`ARCHIVED`... actually applied to **all** records, computed as:
   - `OPEN`: `closing_date` in the future by more than 21 days, or
     `deadline_type = ROLLING`.
   - `CLOSING_SOON`: `closing_date` within 21 days (inclusive) of today.
   - `CLOSED`: the day after `closing_date` passes.
   - `UNKNOWN`: `deadline_type = UNKNOWN_UNSPECIFIED`.
   - `WITHDRAWN`: the canonical page returns 404/410 **twice** (i.e. confirmed
     on a second consecutive check, not a single transient failure), or the
     re-fetched content no longer classifies as an opportunity per module 07.
2. **Re-check cadence** (which records get re-fetched, how often):
   - `RECOMMENDED` / `NEEDS_REVIEW` / `APPROVED` records with a live page:
     every **7 days**; every **2 days** when `CLOSING_SOON`.
   - `UNKNOWN`-deadline records: every **14 days**.
   - `ARCHIVED` records: **not re-fetched** at all.
3. **Content-change re-extraction**: on re-fetch, if `content_hash` (module
   08 §8) changed, trigger pass-1 re-extraction (not pass 2/scoring
   automatically — see edge case in §11 for when re-scoring should also
   fire), and write the diff of key fields (`closing_date`, `amount_details`,
   `eligibility_text`) to `record_history`.
4. **Review flag on deadline change**: if a re-check changes `closing_date`
   on a record currently in the review queue (`RECOMMENDED`/`NEEDS_REVIEW`),
   raise a review flag (surfaced in module 12) rather than silently updating
   it — a reviewer should see that the date moved.
5. **CLOSED record retention**: `CLOSED` records stay in the store
   permanently for the funder-history view and recurrence measurement — they
   are never deleted.
6. **Reopening watch**: when a record with `deadline_type = FIXED_DATE`
   transitions to `CLOSED`, create a `reopening_watches` row with
   `watch_due_at = closed_at + 11 months` (many calls repeat annually). When
   `watch_due_at` arrives, re-check the funder's listing pages for a
   recurrence and notify (via module 14's digest or a dedicated flag).

## 8. Algorithms / Business Logic

### Lifecycle recompute (nightly)

```python
def recompute_lifecycle(record: GrantRecord) -> LifecycleStatus:
    if record.deadline_type == DeadlineType.UNKNOWN_UNSPECIFIED:
        return LifecycleStatus.UNKNOWN
    if record.deadline_type == DeadlineType.ROLLING:
        return LifecycleStatus.OPEN
    if record.withdrawn_signal:   # set by re-check 404/410-twice or reclassification
        return LifecycleStatus.WITHDRAWN
    days_to_close = (record.closing_date - today()).days
    if days_to_close < 0:
        return LifecycleStatus.CLOSED
    if days_to_close <= 21:
        return LifecycleStatus.CLOSING_SOON
    return LifecycleStatus.OPEN
```

### Re-check scheduling

```python
def next_recheck_due(record: GrantRecord) -> Optional[date]:
    if record.review_status == ReviewStatus.ARCHIVED:
        return None   # never re-fetched
    if record.lifecycle_status == LifecycleStatus.CLOSING_SOON:
        return record.last_checked_at.date() + timedelta(days=2)
    if record.lifecycle_status == LifecycleStatus.UNKNOWN:
        return record.last_checked_at.date() + timedelta(days=14)
    return record.last_checked_at.date() + timedelta(days=7)
```

### WITHDRAWN detection

```python
def check_withdrawn(fetch_result) -> bool:
    if fetch_result.status_code in (404, 410):
        prior = get_last_fetch_result(fetch_result.grant_record_id)
        return prior is not None and prior.status_code in (404, 410)   # two consecutive
    if fetch_result.status_code == 200:
        classification = prefilter.classify_record_type(fetch_result.content)  # module 07
        return classification.record_type != RecordType.OPPORTUNITY
    return False
```

### Reopening watch creation

```python
def on_lifecycle_transition_to_closed(record: GrantRecord):
    if record.deadline_type == DeadlineType.FIXED_DATE:
        create_reopening_watch(
            original_record_id=record.grant_id,
            funder_name_normalized=record.funder_name_normalized,
            title_normalized=normalize_title(record.grant_title),
            closed_at=record.closing_date,
            watch_due_at=record.closing_date + relativedelta(months=11),
        )
```

## 9. Configuration

| Setting | Value |
|---|---|
| CLOSING_SOON window | 21 days before closing_date |
| Re-check cadence (active/live) | 7 days |
| Re-check cadence (CLOSING_SOON) | 2 days |
| Re-check cadence (UNKNOWN deadline) | 14 days |
| Re-check cadence (ARCHIVED) | Never |
| WITHDRAWN via 404/410 | 2 consecutive checks |
| Reopening watch delay | 11 months after closing |
| Lifecycle recompute cadence | Nightly |

## 10. Suggested Tech Stack & File Layout

```
app/
  lifecycle/
    __init__.py
    recompute.py           # nightly lifecycle_status recompute job
    recheck_scheduler.py       # next_recheck_due() + enqueues fetches via module 05
    diff_history.py                # record_history diffing on content_hash change
    withdrawn_detection.py            # 404/410-twice and reclassification logic
    reopening_watch.py                   # creation + due-date checking
```

## 11. Error Handling & Edge Cases

- A content-hash change that only affects boilerplate (e.g. a "last updated"
  footer timestamp) but no substantive field: the diff on `closing_date` /
  `amount_details` / `eligibility_text` will correctly show no change even
  though `content_hash` differs — the re-extraction still runs (it's cheap,
  pass-1 only), but no review flag fires since no *tracked* field changed.
- Re-extraction on content change should trigger re-scoring (module 09) when
  a *scored* field actually changed (closing date, amount, eligibility text,
  superfilter blockers) — clarify this explicitly since §7.3 only mentions
  writing the diff; if the change could plausibly move the composite score,
  queue a re-score, not just a re-extract.
- A record's `closing_date` moves *earlier* (rare but possible — an
  application window shortened): still just a review flag per the spec, not
  a special case, but worth surfacing prominently in module 12 since it's
  more urgent than a typical change.
- `reopening_watches` funder/title matching for recurrence detection should
  reuse module 11's Tier B entity-matching logic (trigram similarity ≥ 0.85
  on normalized title within the same normalized funder) rather than
  reimplementing a separate matcher.
- Two consecutive 404s spanning a very long gap (e.g. first check, then next
  check 3 months later due to a scheduling gap) — still counts as "twice,"
  but consider whether a stale gap should reset the counter; the design doc
  doesn't specify a time bound between the two checks, so implement the
  literal "two consecutive checks" rule and flag this as a possible future
  refinement, not a blocker.

## 12. Testing & Acceptance Criteria

- Unit tests: lifecycle recompute correctly assigns each status at exact
  boundary conditions (`days_to_close` = 21 vs 22; `closing_date` = today
  vs yesterday).
- Unit tests: re-check cadence function returns correct next-due dates for
  each `lifecycle_status`/`review_status` combination, including `None` for
  `ARCHIVED`.
- Integration test: simulate a content-hash change on a queued record,
  verify `record_history` gets a diff entry and a review flag fires when a
  tracked field changed.
- Integration test: simulate two consecutive 404 responses, verify
  `WITHDRAWN` transition.
- Acceptance (Phase 2): nightly recompute job runs against the full record
  store without errors; re-check scheduling correctly prioritizes
  `CLOSING_SOON` records at the 2-day cadence.

## 13. Open Questions

None specific to this module beyond the re-scoring-trigger clarification
noted in §11, which should be resolved by the implementing team as "re-score
whenever a scored field's value actually changes on re-extraction."

## 14. Implementation Checklist

- [ ] Implement nightly `lifecycle_status` recompute job.
- [ ] Implement re-check due-date scheduling per the cadence table.
- [ ] Wire re-check fetch execution through module 05.
- [ ] Implement content-hash-change diffing into `record_history`.
- [ ] Implement review-flag raising on tracked-field changes for queued records.
- [ ] Implement WITHDRAWN detection (two-consecutive-404/410 and reclassification).
- [ ] Implement reopening-watch creation and due-date checking (11 months).
- [ ] Decide and implement the re-score trigger on scored-field changes (see §11).
- [ ] Tests per §12.
