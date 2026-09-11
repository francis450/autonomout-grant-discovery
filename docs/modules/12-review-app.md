# Module 12: Review App

## 1. Purpose

The human-facing surface of the whole platform. The grants team works the
review queue here — this is where a `RECOMMENDED`/`NEEDS_REVIEW` record
becomes a decision (Approved/Rejected/Applied), where the platform admin
manages sources and quarantine, and where field corrections flow back into
the extraction/scoring feedback loop (module 13).

## 2. Scope

### In scope
- Three views: Queue, Record, Sources.
- Role-based access: Grants team (reviewers) vs Platform admin.
- Decision capture: Approve/Reject (with fixed reason codes)/mark Applied,
  plus field-level correction.
- Org profile edit UI (Phase 4, per module 01's DB-backed promotion).
- Source registry admin actions: quarantine promotion, retirement.

### Out of scope
- The actual decision *logic* for what lands in the queue — module 09
  (scoring) puts records there; this module only displays and captures human
  action on them.
- Computing source health metrics — module 02 computes them; this module
  displays them and exposes the promotion/retirement actions.
- Sending the digest email — module 14 (though this module's queue links are
  what the digest points to).
- Turning a rejection into a precision decrement or a prefilter rule
  candidate — module 13 consumes this module's captured decisions.

## 3. Dependencies

- Module 08/09: reads `GrantRecord` (all fields) and `RelevanceBreakdown` for
  the Record view.
- Module 02: reads/writes source registry state for the Sources view
  (quarantine promotion, retirement).
- Module 01: Phase 4 — reads/writes org profile via its versioned-record
  interface.
- Module 13: every decision captured here (approve/reject/correct) is an
  input event to the feedback loop.
- Module 16: hosted over Tailscale; runs on the office PC (Phase 1–3) or the
  ERPNext VPS (Phase 4).

## 4. Roadmap Phase & Exit Criteria

Phase 4 deliverable: "Review app on VPS, decision capture." Exit criterion:
"Team using the queue weekly for 4 weeks; ≥ 20 recommended/week; alerts
tested" — this module is the primary interface through which that exit
criterion is observed (weekly usage is literally measured by activity in this
app).

## 5. Inputs & Outputs

**Inputs**: `GrantRecord`s with `review_status` in `RECOMMENDED`/
`NEEDS_REVIEW`; source registry state; org profile (Phase 4).

**Outputs**: `review_status` transitions to `APPROVED`/`REJECTED`/`APPLIED`
with a reason code; field corrections written back to the record (feeding
module 13's few-shot bank); source quarantine-promotion/retirement actions;
org profile edits (Phase 4).

## 6. Data Model

### Roles

| Role | Capabilities |
|---|---|
| Grants team (reviewers) | Work the queue; mark Approved/Rejected with reason code; correct fields; mark Applied |
| Platform admin (Njoro) | Source registry; quarantine promotions; model and prompt changes; eval reports |

### Fixed rejection reason codes

```
REJECTION_REASONS = [
    "expired", "not_a_grant", "geography", "eligibility",
    "too_small_or_large", "duplicate", "other"
]
```

These specific codes exist to **drive metrics** — module 02's precision-ratio
health metric and module 13's prefilter rule-candidate mining both key off
them, so the code list must not be extended casually without updating those
consumers.

### Postgres table `review_decisions`

```
review_decisions
  id                 uuid pk
  grant_record_id     uuid fk -> grant_records.id
  reviewer               text
  decision                 text          -- 'approved' | 'rejected' | 'applied'
  reason_code                 text null   -- required if decision = 'rejected'
  field_corrections             jsonb null  -- {field_name: {old, new}}
  decided_at                       timestamptz
```

### Three views

1. **Queue**: `RECOMMENDED` and `NEEDS_REVIEW` records, sortable by
   `composite_score` and `closing_date`.
2. **Record**: extracted fields displayed beside the rendered markdown
   snapshot and attachment text, with field-level edit capability.
3. **Sources**: registry listing, health metrics, quarantine
   promotion/retirement actions.

## 7. Functional Requirements

1. **Queue view**: list records with `review_status` in
   `{RECOMMENDED, NEEDS_REVIEW}`, default sort by `composite_score` desc,
   with a secondary sort/filter by `closing_date` asc (surfacing urgent
   deadlines). Visually distinguish `RECOMMENDED` (flagged as strong) from
   `NEEDS_REVIEW`.
2. **Record view**: side-by-side layout — extracted structured fields (all
   `GrantRecord` fields, editable) next to the rendered raw markdown snapshot
   (module 05/11's Tier C snapshot) and the assembled attachment text (module
   06). A reviewer must be able to see the source text that produced any
   extracted field, to judge correctness without leaving the app.
3. **Field-level edit**: any field can be corrected inline; corrections are
   captured in `review_decisions.field_corrections` and, separately, applied
   to the live `GrantRecord` so the corrected value is what's shown/exported
   going forward.
4. **Decision actions**:
   - **Approve**: `review_status → APPROVED`.
   - **Reject**: requires selecting one of the fixed reason codes;
     `review_status → REJECTED`.
   - **Mark Applied**: `review_status → APPLIED` (used after the grants team
     has actually submitted an application, for pipeline tracking).
5. **Sources view**: list all sources with `status`, rolling 30-day metrics
   (module 02), and admin-only actions: promote `QUARANTINED → ACTIVE`
   (resets metrics window per module 02 §11), retire any source (manual-only,
   any state → `RETIRED`).
6. **Org profile edit (Phase 4)**: admin-only form that writes a new
   versioned row via module 01's Phase 4 DB interface — never mutates a prior
   version.
7. **Access control**: reviewer role can access Queue and Record views and
   the decision actions; admin-only actions (Sources view mutations, org
   profile edits, model/prompt changes) are gated to the admin role.

## 8. Algorithms / Business Logic

No novel algorithms live in this module — it is primarily a CRUD/display
layer over other modules' data. The one piece of logic worth being explicit
about is the **decision → downstream propagation** sequence, since it's the
seam between this module and module 13:

```python
def submit_decision(record_id, reviewer, decision, reason_code=None, field_corrections=None):
    if decision == "rejected" and reason_code is None:
        raise ValidationError("reason_code required for rejection")

    review_decisions.insert(record_id, reviewer, decision, reason_code, field_corrections, now())

    if field_corrections:
        apply_corrections_to_record(record_id, field_corrections)
        # do NOT re-run extraction — corrections are direct overwrites, feeding module 13's
        # few-shot bank as ground truth, not triggering a new LLM pass

    grant_records.update_review_status(record_id, decision_to_status(decision))

    # module 13 subscribes to review_decisions inserts (or polls them) to:
    #  - decrement source precision on 'expired'/'not_a_grant' rejections
    #  - queue prefilter rule candidates on 'not_a_grant' rejections of rule-passed records
    #  - add corrected records to the few-shot bank
```

## 9. Configuration

| Setting | Value |
|---|---|
| Rejection reason codes | Fixed list, see §6 — not user-extensible without updating downstream consumers |
| Access | Over Tailscale only, no public internet exposure |
| Hosting (Phase 1–3) | Office PC |
| Hosting (Phase 4) | ERPNext VPS |

## 10. Suggested Tech Stack & File Layout

Stack choice (Next.js vs FastAPI+HTMX) is an **explicit open decision** (§13)
— pick based on what the team will actually maintain, not preference. The
layout below is stack-agnostic at the module-boundary level:

```
app/
  review_app/
    api/
      queue.py            # GET records where review_status in (RECOMMENDED, NEEDS_REVIEW)
      record.py               # GET/PATCH single record incl. field corrections
      decisions.py                # POST review decision
      sources.py                     # GET sources + POST quarantine-promote/retire
      org_profile.py                    # Phase 4: GET/POST profile edits
    web/                                    # UI — Next.js pages or FastAPI+HTMX templates
      queue_view.*
      record_view.*
      sources_view.*
    auth.py                                    # role-based access (reviewer vs admin)
```

## 11. Error Handling & Edge Cases

- A record is edited by a reviewer while a background re-check (module 10)
  is simultaneously re-extracting it: use optimistic concurrency (a version/
  updated_at check) so a reviewer's in-progress edit isn't silently
  clobbered by an automated re-extraction, and vice versa — surface a
  conflict rather than losing either change.
- Rejecting a record with reason `duplicate`: should link to the record it's
  a duplicate of, if known — if module 11's dedup should have caught this
  but didn't, that's valuable signal (log it distinctly from a routine
  duplicate rejection so it can be reviewed as a possible dedup-tuning
  input).
- Admin quarantine-promotion action on a source with genuinely no recent
  crawl history — should still succeed (it resets the metrics window per
  module 02), but the UI should warn if promoting a source that was
  quarantined very recently (e.g. < 24h ago) since that's likely an
  accidental double-click rather than a considered decision.
- Field corrections on enum-typed fields (e.g. `geographic_scopes`) must be
  constrained to valid enum values in the UI, not free text, to keep
  `field_corrections` structurally valid for module 13's few-shot bank use.

## 12. Testing & Acceptance Criteria

- Unit/integration tests: decision submission correctly requires a reason
  code for rejections; field corrections apply without triggering
  re-extraction; role-based access correctly blocks reviewer-role users from
  admin-only actions.
- UI test (manual or automated): a reviewer can go from Queue → Record →
  Approve/Reject in a small number of clicks, with the source snapshot
  visibly correlated to the extracted fields.
- Acceptance (Phase 4): the grants team uses the Queue view weekly for 4
  consecutive weeks, producing ≥ 20 recommended/week with real decisions
  captured; admin can promote a quarantined source and see it return to
  `ACTIVE` scheduling.

## 13. Open Questions

- **Stack choice**: Next.js vs FastAPI + HTMX — explicitly deferred to "what
  the team will maintain, not preference." Resolve this before starting
  Phase 4 implementation; it affects the file layout above materially.
- Whether the review app needs any offline/low-connectivity affordances
  given it may be used by a Kenya-based team over Tailscale — not addressed
  in the design doc; worth a quick check with the grants team during Phase 4
  planning.

## 14. Implementation Checklist

- [ ] Resolve stack choice (Next.js vs FastAPI+HTMX) with the team.
- [ ] Implement Queue view (list, sort by score/closing date, RECOMMENDED vs NEEDS_REVIEW distinction).
- [ ] Implement Record view (structured fields + snapshot + attachment text, field-level edit).
- [ ] Implement decision capture (approve/reject-with-reason/applied) writing to `review_decisions`.
- [ ] Implement Sources view (registry, health metrics, quarantine-promote, retire).
- [ ] Implement role-based access control (reviewer vs admin).
- [ ] Phase 4: implement org profile edit UI wired to module 01's versioned DB interface.
- [ ] Deploy over Tailscale; Phase 4 migrate hosting to ERPNext VPS.
- [ ] Tests per §12.
