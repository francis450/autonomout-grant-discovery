# Module 14: Delivery

## 1. Purpose

Gets the platform's output in front of the grants team without them having to
remember to check the review app. A weekly digest email is the primary
delivery mechanism; CSV export supports whatever downstream tooling the team
already uses. This module is intentionally thin — it does not make decisions,
it surfaces ones already made.

## 2. Scope

### In scope
- Monday digest email: new `RECOMMENDED` records, records closing within 21
  days, source-health warnings.
- CSV export of `APPROVED` records.
- SMTP delivery via the platform's own mail sending, with links into the
  review app.

### Out of scope
- ERPNext push integration — explicitly a **Phase 5 option**, deliberately
  out of the initial scope; this module should be built so adding it later
  is additive (a new export target), not a rework.
- Deciding what's `RECOMMENDED` or what counts as a source-health warning —
  modules 09 and 02 own those; this module queries their outputs.
- The review app's own UI — module 12; this module only links into it.

## 3. Dependencies

- Module 09 (Scoring Engine): source of new `RECOMMENDED` records for the
  digest.
- Module 10 (Record Lifecycle): source of records `CLOSING_SOON`/closing
  within 21 days.
- Module 02 (Source Registry): source of health warnings (`DEGRADED`,
  newly `QUARANTINED` sources).
- Module 12 (Review App): destination of the "links into the review app" in
  the digest, and source of `APPROVED` records for CSV export.
- Module 16 (Runtime & Operations): SMTP credentials/config, scheduler
  trigger for the Monday send.

## 4. Roadmap Phase & Exit Criteria

Phase 4 deliverable: "Monday digest" alongside the review app and monitoring.
No standalone numeric exit criterion, but it's the mechanism by which the
platform-wide "team using the queue weekly" exit criterion is *driven* — the
digest is what prompts weekly usage in the first place.

## 5. Inputs & Outputs

**Inputs**: `RECOMMENDED` records created since the last digest;
`CLOSING_SOON`/near-deadline records; source-health warning events (module
02); `APPROVED` records for CSV export requests.

**Outputs**: a sent email (Monday digest) and/or a generated CSV file.

## 6. Data Model

### Digest content structure

```python
class DigestContent(BaseModel):
    period_start: datetime
    period_end: datetime
    new_recommended: List[GrantRecordSummary]      # created since last digest
    closing_within_21_days: List[GrantRecordSummary]
    source_health_warnings: List[SourceHealthWarning]

class GrantRecordSummary(BaseModel):
    grant_id: str
    grant_title: str
    funder_name: str
    composite_score: int
    closing_date: Optional[date]
    review_app_link: HttpUrl

class SourceHealthWarning(BaseModel):
    source_id: str
    source_name: str
    status: str                # 'DEGRADED' | 'QUARANTINED'
    reason: str
```

### Postgres table `digest_sends` (audit trail)

```
digest_sends
  id              uuid pk
  sent_at           timestamptz
  recipient_count     int
  new_recommended_count  int
  closing_soon_count       int
  warning_count               int
  status                        text    -- 'sent' | 'failed'
  error                            text null
```

## 7. Functional Requirements

1. **Monday digest composition**: every Monday (scheduled via module 16),
   query:
   - `GrantRecord`s with `review_status = RECOMMENDED` created since the
     prior digest send.
   - `GrantRecord`s with `lifecycle_status = CLOSING_SOON` or
     `closing_date` within 21 days, regardless of when they were created
     (so a record that was recommended weeks ago but is now approaching
     deadline still surfaces).
   - Source-health warning events from module 02 since the prior send
     (new `DEGRADED`/`QUARANTINED` transitions).
2. **Email composition**: render the digest with clear sections for each of
   the three content types, each record/source linking directly into the
   relevant module 12 view (Record view for grants, Sources view for
   warnings).
3. **SMTP delivery**: send via the platform's own SMTP configuration (module
   16 owns credentials, stored in `.env`); log every send attempt in
   `digest_sends` for audit and failure alerting.
4. **CSV export**: on-demand (triggered from module 12's UI or a scheduled
   job) export of `APPROVED` records with all relevant fields, for the
   grants team to use in whatever tracking tool they prefer outside the
   platform.
5. **Failure handling**: a failed digest send must be visible — this feeds
   module 16's monitoring (a failed weekly digest is exactly the kind of
   "silent outage" the design doc calls out as a real failure mode in the
   predecessor system).

## 8. Algorithms / Business Logic

### Digest composition

```python
def compose_monday_digest() -> DigestContent:
    last_send = digest_sends.get_last_successful()
    period_start = last_send.sent_at if last_send else (now() - timedelta(days=7))
    period_end = now()

    new_recommended = grant_records.query(review_status="RECOMMENDED", created_since=period_start)
    closing_soon = grant_records.query(
        review_status__in=["RECOMMENDED", "NEEDS_REVIEW", "APPROVED"],
        closing_date__lte=today() + timedelta(days=21),
        closing_date__gte=today(),
    )
    warnings = source_registry.query_health_events(since=period_start, statuses=["DEGRADED", "QUARANTINED"])

    return DigestContent(period_start=period_start, period_end=period_end,
                          new_recommended=[summarize(r) for r in new_recommended],
                          closing_within_21_days=[summarize(r) for r in closing_soon],
                          source_health_warnings=warnings)

def send_monday_digest():
    content = compose_monday_digest()
    try:
        smtp_client.send(to=GRANTS_TEAM_RECIPIENTS, subject=digest_subject(content), body=render_digest(content))
        digest_sends.insert(status="sent", **counts(content))
    except SMTPError as e:
        digest_sends.insert(status="failed", error=str(e), **counts(content))
        raise   # let module 16's alerting catch this
```

## 9. Configuration

| Setting | Value |
|---|---|
| Digest cadence | Weekly, Monday |
| Closing-soon window | 21 days |
| Delivery mechanism | Platform's own SMTP (`.env` credentials) |
| CSV export scope | `APPROVED` records |
| ERPNext push | Phase 5, out of initial scope |

## 10. Suggested Tech Stack & File Layout

```
app/
  delivery/
    __init__.py
    digest_composer.py       # queries + DigestContent assembly
    digest_renderer.py           # email template rendering (HTML + plaintext)
    smtp_sender.py                   # SMTP delivery + digest_sends audit logging
    csv_export.py                        # APPROVED records -> CSV
```

## 11. Error Handling & Edge Cases

- No new `RECOMMENDED` records in a given week: still send the digest (an
  empty "new recommended" section is itself informative — a silent skip
  would be indistinguishable from a failure, undermining the whole point of
  avoiding "silent outage").
- SMTP delivery failure: must raise/alert (module 16), not fail silently;
  retry policy (e.g. one retry after a short delay) is reasonable, but a
  fully failed send must be visible to the admin, not just logged and
  forgotten.
- A record appears in both `new_recommended` and `closing_within_21_days`
  (newly recommended and also urgent): fine to appear in both sections —
  don't deduplicate across sections, since they answer different questions
  ("what's new" vs "what's urgent").
- CSV export with very large `APPROVED` record counts over time: stream/
  paginate the export rather than loading the full history into memory if
  the grants team requests a full historical export.

## 12. Testing & Acceptance Criteria

- Unit tests: digest composition correctly windows by `period_start`/
  `period_end`; closing-soon query correctly uses the 21-day window
  regardless of `created_at`.
- Integration test: a full digest send against a test SMTP server (e.g.
  MailHog/local SMTP debug server) produces a correctly rendered email with
  working review-app links.
- Acceptance (Phase 4): the grants team receives a real Monday digest
  containing accurate new-recommended, closing-soon, and source-warning
  sections for 4 consecutive weeks (ties to the platform-wide Phase 4 exit
  criterion); a deliberately failed SMTP send triggers a visible alert
  (module 16).

## 13. Open Questions

- Recipient list management (who's on `GRANTS_TEAM_RECIPIENTS`, and whether
  it's admin-configurable via module 12 or a static config value) is not
  specified in the design doc — a reasonable default is a config-file list
  for Phase 4, promotable to an admin-editable list later if needed.

## 14. Implementation Checklist

- [ ] Implement digest composition query logic (new-recommended, closing-soon, health warnings).
- [ ] Implement email rendering (HTML + plaintext) with review-app links.
- [ ] Implement SMTP delivery with `digest_sends` audit logging and failure alerting.
- [ ] Implement CSV export of `APPROVED` records.
- [ ] Schedule the Monday send via module 16.
- [ ] Tests per §12.
- [ ] Phase 5 (optional): design the ERPNext push as an additive export target, not a rework of this module.
