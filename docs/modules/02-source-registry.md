# Module 02: Source Registry & Health Lifecycle

## 1. Purpose

Every page the platform ever fetches comes from a registered source. This
module owns the catalogue of sources (websites, feeds, APIs), their
classification, their crawl configuration, and the automated health lifecycle
that promotes, degrades, quarantines, or retires them based on observed yield
and precision. It is the platform's memory of "where do we look and how well
is each place performing."

## 2. Scope

### In scope
- Source classification into three classes (A/B/C) — correcting the v2 design's
  mistaken treatment of IATI/360Giving/Grants.gov as opportunity feeds.
- The `Source` record schema and its status state machine.
- Seeding the registry from the one-time `toh-grants-engine` source-list export.
- Rolling 30-day health metrics and the automated thresholds that change a
  source's status.
- The admin action of promoting a `QUARANTINED` source back to `ACTIVE`.

### Out of scope
- How candidate new sources are found (module 03, Discovery, feeds new
  candidates into `PENDING_QUALIFICATION`).
- How a source is actually crawled (modules 04 Crawl Policy, 05 Tiered
  Ingestion).
- Whether a given crawled page turns into a `GrantRecord` (module 07/08) —
  this module only tracks source-level aggregate metrics, not record-level
  decisions, though it consumes record-level rejection reasons as input to the
  precision-ratio metric (see module 13, Feedback Loop, §"Source precision").

## 3. Dependencies

- Module 03 (Discovery) writes new candidate sources into this registry with
  status `PENDING_QUALIFICATION`.
- Module 04 (Crawl Policy) reads `robots_allowed`, `user_agent_policy`, and
  writes back the weekly robots.txt re-check result.
- Module 05 (Tiered Ingestion) reads `ingest_tier`, `crawl_cadence_hours`,
  `listing_urls[]`, `priority` to schedule fetches, and writes back
  `pages_fetched`, `last_success_at`, `last_error`.
- Module 13 (Feedback Loop) writes rejection-driven precision decrements.
- Module 12 (Review App) provides the human UI for the "Sources" view
  (registry, health, quarantine promotion actions) — this module supplies the
  data and the promotion API that view calls.

## 4. Roadmap Phase & Exit Criteria

Phase 1: registry seeded from the `toh-grants-engine` source list, classified,
tagged with expected page type, crawl tier, and cadence. Sources from the old
list that were never productive are imported as `QUARANTINED`, not `ACTIVE`.

Phase 4: full automated health lifecycle live, "source health lifecycle" and
"full source list active" are explicit Phase 4 deliverables; exit criterion
includes the platform sustaining ≥ 20 recommended/week, which structurally
requires enough `ACTIVE` sources to be running.

## 5. Inputs & Outputs

**Inputs**:
- One-time: `toh-grants-engine` source list export (URL, name, category, notes).
- Ongoing: candidate URLs from module 03; crawl results and record outcomes
  from modules 05, 07/08, and rejection reasons from module 13.

**Outputs**:
- The authoritative, queryable list of sources with current status, for module
  05's scheduler to consume each run.
- Health/quarantine events (for alerting, module 16) and admin-facing summaries
  (for module 12's Sources view).

## 6. Data Model

### Source classes

| Class | What it yields | Examples | Pipeline use |
|---|---|---|---|
| A. Opportunity sources | Open calls, RFPs, application windows | EU Funding & Tenders Portal; DevelopmentAid; fundsforNGOs; UN agency calls (UNICEF, UNDP); embassy small-grant schemes (US Ambassador's Self-Help, Japan GGP, Canada Fund for Local Initiatives); corporate CSR (Cisco, Dell, HP, Microsoft, Google.org); Kenyan/pan-African funders (HCI, NRF Kenya, Tony Elumelu Foundation, Mastercard Foundation); GlobalGiving; Grants.gov (low priority — mostly US-domestic) | Crawled on a schedule; records enter the extraction pipeline |
| B. Funder-prospecting datasets | Who funds e-waste/edtech/off-grid energy in East Africa, at what size, how often | IATI (IATI Datastore / iati.cloud), 360Giving GrantNav, Candid/Foundation Directory (manual) | Quarterly job (module 03) produces a ranked funder list; approved funders become Class A sources |
| C. Discovery feeds | Fresh pages that might be opportunities or new portals | Serper query feeds, RSS from Class A sources, funder newsletters (manual forward) | Feed the `PENDING_QUALIFICATION` queue |

**Critical correction from v2**: IATI, 360Giving, and Grants.gov are *not*
interchangeable opportunity feeds. IATI publishes aid activities already
funded; 360Giving publishes grants already awarded. Neither publishes open
calls — they are Class B (funder prospecting), not Class A, except
Grants.gov which does publish real open calls (Class A, low priority).

### Postgres table `sources`

```
sources
  id                   uuid pk
  name                 text
  homepage_url         text
  listing_urls         text[]
  source_class         text        -- 'A' | 'B' | 'C'
  ingest_tier          smallint    -- 0 | 1 | 2
  crawl_cadence_hours  int
  priority             smallint    -- 1-5
  robots_allowed       boolean
  robots_checked_at    timestamptz
  user_agent_policy    text
  status               text        -- see state machine below
  last_success_at      timestamptz
  last_error           text
  notes                text
  origin               text        -- 'toh-grants-engine seed' | 'discovery' | 'manual'
  created_at           timestamptz
  updated_at           timestamptz
```

### Postgres table `source_metrics_daily` (rolling 30d aggregates computed from this)

```
source_metrics_daily
  source_id            uuid fk -> sources.id
  day                  date
  pages_fetched        int
  records_extracted    int
  records_recommended  int
  schema_errors        int
  blocked_responses    int
  total_responses      int
  pk (source_id, day)
```

Rolling 30-day metrics (`precision_ratio`, `schema_error_rate`, `block_rate`,
`yield`) are computed as views/queries over this table rather than stored as
mutable running totals, so historical recomputation and the eval harness stay
consistent.

### Status state machine

```
PENDING_QUALIFICATION --(3 qualified pages from domain, module 03)--> ACTIVE
ACTIVE --(health threshold breach)--> DEGRADED
ACTIVE --(health threshold breach)--> QUARANTINED
DEGRADED --(sustained breach)--> QUARANTINED
DEGRADED --(recovers)--> ACTIVE   [automatic]
QUARANTINED --(human click in admin view, module 12)--> ACTIVE   [manual only]
any state --(human decision)--> RETIRED   [manual only]
```

## 7. Functional Requirements

1. **Seeding**: a one-time import script reads the `toh-grants-engine` export
   (URL, name, category, notes), deduplicates by normalized URL, classifies
   each as Class A (default) unless it matches a known Class B dataset, tags
   `expected page type` (listing/detail/PDF), and sets initial `status`:
   `ACTIVE` if the source was historically productive in the old system,
   `QUARANTINED` otherwise. `origin = 'toh-grants-engine seed'`.
2. **Registry API**: CRUD for sources, filterable by `status`, `source_class`,
   `ingest_tier`. Module 05's scheduler calls "list sources where status =
   ACTIVE order by priority" every scheduling cycle.
3. **Metric computation**: nightly job aggregates the day's crawl/extraction/
   review outcomes into `source_metrics_daily`, then evaluates the health
   thresholds table (§8) against the trailing 30-day window and applies any
   automatic status transition.
4. **Quarantine promotion**: admin-only API/UI action moves `QUARANTINED` →
   `ACTIVE`, resets the rolling metrics window (so old failures don't
   immediately re-quarantine it), and logs who/when/why.
5. **Retirement**: manual-only action, any state → `RETIRED`; retired sources
   are excluded from all scheduling but retained for history/audit.
6. **robots.txt re-check**: weekly job re-fetches and re-parses robots.txt per
   domain, updates `robots_allowed`; if a previously-allowed source becomes
   disallowed, transition it toward `RETIRED` with reason `"robots"` (this
   overlaps module 04's crawl policy — module 04 owns the *fetching and
   parsing* of robots.txt, this module owns *storing the result and reacting
   to it* at the source-status level).

## 8. Algorithms / Business Logic

### Health thresholds (evaluated nightly, rolling 30-day / trailing-N-run windows)

| Metric | Definition | Action |
|---|---|---|
| Yield | New unique records per run | 0 for 5 consecutive runs → `QUARANTINED`; inspect |
| Precision ratio | Share of extracted records with composite score ≥ review threshold | < 10% over 100 records → `QUARANTINED` |
| Schema error rate | Extractions failing schema validation after retry | > 25% over a run → `DEGRADED`; likely site redesign |
| Block rate | 4xx/5xx/challenge responses | > 20% → `DEGRADED`, cadence halved; > 50% for 3 runs → `QUARANTINED`. No proxy escalation. |
| Staleness | No new record in 90 days on an `ACTIVE` source | Cadence reduced to weekly |

Evaluation order matters: check quarantine-triggering conditions (yield,
precision, sustained block rate) before degrade-triggering conditions, since a
quarantine supersedes a degrade in the same run.

### Promotion to ACTIVE from PENDING_QUALIFICATION

Owned procedurally by module 03 (it performs the qualifying fetch/classify),
but the *state transition and storage* belongs here: when module 03 reports
the 3rd qualified page from a domain still in `PENDING_QUALIFICATION`, flip
`status = ACTIVE`.

## 9. Configuration

| Setting | Value | Notes |
|---|---|---|
| Metric window | 30 days rolling | Except "5 consecutive runs" (yield) and "3 consecutive runs" (block rate), which are run-count based, not day-based — track both a day-window and a run-count window per source |
| Quarantine → Active | Manual only | Admin view, module 12 |
| Any → Retired | Manual only | — |
| robots re-check cadence | Weekly | Module 04 performs the fetch |

## 10. Suggested Tech Stack & File Layout

```
app/
  sources/
    __init__.py
    schema.py           # Source, SourceStatus enum, SourceClass enum
    repository.py        # CRUD + filtered queries against `sources` table
    metrics.py            # rolling window computation over source_metrics_daily
    health.py              # threshold evaluation + automatic transitions (nightly job)
    seed_import.py           # one-time toh-grants-engine list importer
    quarantine.py             # admin promote/retire actions + audit log
```

## 11. Error Handling & Edge Cases

- A source with zero crawl history yet (freshly seeded) must not be evaluated
  against health thresholds until it has at least one full run — guard the
  nightly job against div-by-zero / premature quarantine on `records_extracted
  = 0` with no runs yet.
- Two automatic transitions could fire in the same nightly run (e.g. yield
  breach and block-rate breach simultaneously) — quarantine wins over degrade;
  log both reasons in `last_error`/notes even though only one status applies.
- Reactivating a `QUARANTINED` source must reset its rolling window rather
  than immediately re-evaluating against stale pre-quarantine data, or it will
  flap back to `QUARANTINED` on the next nightly run before it has a chance to
  prove itself.
- Duplicate seed rows (same URL appearing twice in the `toh-grants-engine`
  export under different names) — dedupe by normalized homepage URL at import
  time (reuse the URL-normalization rule from module 11, Tier A dedup, for
  consistency).

## 12. Testing & Acceptance Criteria

- Unit tests: each health threshold rule fires correctly at its boundary
  (e.g. exactly 10% precision does not quarantine, 9.99% does).
- Seed import test: run against a sample export CSV, verify classification,
  dedup, and initial status assignment match expectations.
- Integration test: simulate 5 consecutive zero-yield runs for a source,
  assert it transitions to `QUARANTINED`; simulate an admin promotion, assert
  it returns to `ACTIVE` with a reset metrics window.
- Acceptance (Phase 1): registry is seeded from the real `toh-grants-engine`
  export; every source has a `source_class`, `ingest_tier`, and initial
  `status`; previously unproductive sources are `QUARANTINED`, not `ACTIVE`.
- Acceptance (Phase 4): a full nightly run against live 30-day data correctly
  produces status transitions matching the threshold table, visible in module
  12's Sources view, with quarantine promotion working end-to-end.

## 13. Open Questions

- Which paywalled aggregators (Candid, Instrumentl, DevelopmentAid premium)
  TOH actually holds licences for, and whether their exports can be ingested —
  affects how those specific sources are classified and whether they're
  seeded as `ACTIVE` Class A sources or excluded pending a licensing decision.
  See also module 04 §13 (crawl policy also touches this for the "never scrape
  behind a paywall" rule).

## 14. Implementation Checklist

- [ ] Define `sources` and `source_metrics_daily` schema + migrations.
- [ ] Implement `Source`/`SourceStatus`/`SourceClass` models.
- [ ] Build seed importer for the `toh-grants-engine` export; run it once against real data.
- [ ] Implement rolling-metric computation job.
- [ ] Implement health-threshold evaluation + automatic transitions.
- [ ] Implement admin quarantine-promotion and retirement actions with audit logging.
- [ ] Wire weekly robots.txt re-check result storage (fetch logic lives in module 04).
- [ ] Tests per §12.
