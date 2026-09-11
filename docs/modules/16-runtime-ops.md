# Module 16: Runtime & Operations

## 1. Purpose

The infrastructure every other module runs on: the scheduler, the LLM job
queue that serializes access to the single Ollama GPU host, object and
relational storage, hosting topology across the Phase 1→4 transition,
monitoring/alerting, and backups. Nothing in this design doc is "someone
else's problem" here — this module is explicitly responsible for making sure
a silent outage (the predecessor system's real failure mode) can't happen
unnoticed.

## 2. Scope

### In scope
- The runtime component diagram and how modules connect through it.
- Scheduler (cron/APScheduler) — all scheduled cadences across the platform.
- LLM job queue with GPU serialization and priority ordering.
- Postgres schema/migration ownership at the platform level (individual
  modules own their own tables; this module owns the migration tooling,
  backup, and cross-cutting `runs` table).
- Object storage (MinIO or plain directory) for snapshots and attachments.
- Hosting topology: office PC (Phase 1–3) → split office PC (inference/crawl)
  + ERPNext VPS (Postgres/review app) (Phase 4).
- Monitoring, alerting, and backups.
- Secrets and config management conventions.

### Out of scope
- The business logic of what gets scheduled — each module defines its own
  cadence requirements (e.g. module 02's nightly health job, module 03's
  daily discovery run); this module provides the scheduler and enforces
  cadences, it doesn't decide them.
- What goes in the object store's content (module 06 attachments, module
  05/11 snapshots) — this module owns the storage mechanism, not the content.

## 3. Dependencies

This module is a dependency **of** nearly every other module rather than a
dependent itself. Specifically it is consumed by:
- Module 02 (nightly health job scheduling), 03 (daily discovery, quarterly
  prospecting), 05 (crawl scheduling, object store for snapshots), 06
  (object store for attachments), 08/07 (LLM job queue), 10 (nightly
  lifecycle recompute, re-check scheduling), 12 (hosting), 13 (monthly
  recalibration schedule), 14 (Monday digest schedule, SMTP secrets).

## 4. Roadmap Phase & Exit Criteria

Phase 1: "Repo, Postgres schema ... " is foundational — this module's
skeleton (Postgres, basic scheduler) must exist before almost anything else
can be built.

Phase 4 deliverable: "monitoring/alerts, backups" explicitly, plus the
hosting split to the ERPNext VPS. Exit criterion: "alerts tested" is part of
the Phase 4 bar.

## 5. Inputs & Outputs

**Inputs**: scheduled job definitions from every module; fetch/extraction/
scoring job requests for the LLM queue; raw content for object storage.

**Outputs**: executed jobs on schedule; serialized LLM inference results;
stored snapshots/attachments retrievable by content hash; a `runs` table
summarizing every pipeline run; alerts on failure conditions; nightly
backups.

## 6. Data Model

### Component diagram (from the design doc, §11.1)

```
[Scheduler: APScheduler / cron]
     |
     v
[Crawl workers: Crawl4AI, async, per-domain limiter]  --->  [Object store: MinIO or local FS]
     |                                                            (snapshots, attachments)
     v
[Prefilter (rules)]  --->  [LLM job queue: Redis/RQ or Postgres-backed]
                                        |
                                        v  (workers = 1 per Ollama instance)
                             [Extraction pass 1 -> pass 2 -> scoring]
                                        |
                                        v
                          [Postgres: sources, records, history, decisions]
                                        |
                                        v
                   [Review app over Tailscale]   [Monday digest]   [Eval harness CLI]
```

### Postgres table `runs` (per-run summary, cross-cutting)

```
runs
  id                 uuid pk
  run_type             text        -- 'crawl' | 'discovery' | 'lifecycle_recompute' | 'recalibration' | 'digest' | ...
  started_at             timestamptz
  finished_at               timestamptz
  pages_fetched                int
  records_produced               int
  llm_calls                        int
  failures                           int
  queue_depth_at_start                 int
  status                                  text   -- 'success' | 'partial_failure' | 'failed'
```

### LLM job queue entry

```
LLMJob:
  id: str
  job_type: str          # 'pass1_extraction' | 'pass2_relevance' | 'prefilter_model_classify' | 'dual_decode_check'
  priority: int           # lower = higher priority
  payload: dict
  enqueued_at: datetime
  started_at: Optional[datetime]
  completed_at: Optional[datetime]
  status: str               # 'queued' | 'running' | 'done' | 'failed'
```

## 7. Functional Requirements

### 7.1 Scheduler

Owns execution of every module's scheduled cadence:

| Job | Cadence | Owning module |
|---|---|---|
| Listing crawls | By source cadence, default daily, priority-weighted | 05 |
| Re-checks | Nightly (2-day for CLOSING_SOON) | 10 |
| Discovery (Serper/RSS) | Daily | 03 |
| Class B prospecting | Quarterly | 03 |
| Lifecycle recompute | Nightly | 10 |
| Source health evaluation | Nightly | 02 |
| robots.txt re-check | Weekly | 04 |
| Few-shot bank rotation | Weekly | 13 |
| Weight recalibration | Monthly | 13/09 |
| Monday digest | Weekly, Monday | 14 |
| Backups | Nightly | 16 (this module) |

### 7.2 LLM job queue and GPU serialization

1. **Single worker per Ollama instance**: crawl workers are async and fast;
   the Ollama host is not — **all** LLM calls (pass-1, pass-2, prefilter
   model-layer classification, dual-decode confidence checks) go through
   one queue with **exactly one worker per Ollama instance**, so the GPU is
   never asked to serve concurrent requests it can't actually parallelize.
2. **Priority ordering**: re-checks of `CLOSING_SOON` records first, then
   new detail pages, then discovery qualification — in that order. A backed-
   up queue should never starve urgent re-checks in favor of routine new-page
   extraction.
3. **Per-run token/time budget**: cap total LLM spend per scheduled run so a
   pathological run (e.g. a source dump producing thousands of candidate
   pages at once) can't monopolize the queue indefinitely.
4. **Non-blocking crawling**: crawling must never block on inference —
   crawl workers write fetched content and move on; extraction consumes it
   asynchronously via the queue.

### 7.3 Storage

1. **Postgres**: structured data and decision history, with an
   **append-only history table** pattern (used by module 10's
   `record_history`, module 01's `org_profile_versions`, module 11's
   `record_merges`, etc.) — this module owns migration tooling and schema
   evolution discipline, individual modules own their specific tables.
2. **Object store**: MinIO or a plain directory on the office PC for
   snapshots (module 05/11 Tier C) and attachments (module 06), **keyed by
   content hash** — this is the single storage backend all content-
   addressed data in the platform uses.

### 7.4 Hosting

1. **Phase 1–3**: all components run on the office PC, which already serves
   Ollama over Tailscale.
2. **Phase 4**: Postgres and the review app (module 12) move to the ERPNext
   VPS so the team can reach the queue without the office PC being on; the
   **office PC remains the inference and crawl host** (Ollama + crawl
   workers stay put — only the data/UI layer moves).

### 7.5 Monitoring and alerts

1. **Per-run summary**: every scheduled run writes to the `runs` table
   (pages, records, LLM calls, failures, queue depth).
2. **Alert conditions**:
   - A run fails.
   - The LLM queue exceeds **500 jobs**.
   - No records are produced for **48 hours**.
   - The Ollama host is unreachable.
3. **Delivery**: email/Slack. This exists specifically because **a silent
   outage was a real failure mode in the predecessor system** — alerting is
   not optional polish, it's a named requirement responding to a known past
   failure.

### 7.6 Backups

1. **Nightly `pg_dump`** plus **snapshot-directory rsync** to a second
   location.
2. **Restore tested once before go-live** — an untested backup is not a
   backup; this is an explicit pre-go-live task, not a "nice to have someday."

### 7.7 Secrets and config

1. **`.env`** for keys (Serper, SMTP) — never committed.
2. **YAML** for org profile (module 01) and crawl policy (module 04)
   parameters — version-controlled **without secrets**.

## 8. Algorithms / Business Logic

### LLM queue priority scheduling

```python
PRIORITY = {
    "recheck_closing_soon": 0,
    "new_detail_page": 1,
    "discovery_qualification": 2,
    "dual_decode_check": 1,        # same tier as new detail page extraction it supports
    "prefilter_model_classify": 1,  # short call, keep it flowing with extraction
}

def enqueue_llm_job(job_type: str, payload: dict):
    job = LLMJob(id=uuid4(), job_type=job_type, priority=PRIORITY[job_type],
                 payload=payload, enqueued_at=now(), status="queued")
    queue.push(job, priority=job.priority)   # e.g. Redis sorted set or Postgres-backed priority queue

def llm_worker_loop(ollama_instance):
    while True:
        job = queue.pop_highest_priority()    # blocks/polls if empty
        job.status = "running"; job.started_at = now()
        try:
            result = ollama_instance.run(job.payload)
            job.status = "done"; job.completed_at = now()
            deliver_result(job, result)
        except Exception as e:
            job.status = "failed"
            log_and_maybe_requeue(job, e)
```

### Alert evaluation (runs periodically, e.g. every 15 minutes)

```python
def evaluate_alerts():
    if queue.depth() > 500:
        send_alert("LLM queue depth exceeded 500 jobs")
    if runs.count(status__in=["failed"], since=last_check) > 0:
        send_alert("A scheduled run failed", details=...)
    if grant_records.count(created_since=now() - timedelta(hours=48)) == 0:
        send_alert("No records produced in 48 hours")
    if not ollama_health_check():
        send_alert("Ollama host unreachable")
```

## 9. Configuration

| Setting | Value |
|---|---|
| LLM workers | 1 per Ollama instance (hard constraint, not tunable up) |
| LLM priority order | recheck(CLOSING_SOON) > new detail pages > discovery qualification |
| Queue depth alert threshold | 500 jobs |
| No-records alert threshold | 48 hours |
| Backup cadence | Nightly `pg_dump` + snapshot rsync |
| Secrets location | `.env`, never committed |
| Config location | YAML, version-controlled, no secrets |
| Hosting (Phase 1–3) | Office PC (all components) |
| Hosting (Phase 4) | Office PC (Ollama + crawl) + ERPNext VPS (Postgres + review app) |

## 10. Suggested Tech Stack & File Layout

```
app/
  runtime/
    scheduler.py              # APScheduler/cron job registration for all modules' cadences
    llm_queue/
      queue_backend.py           # Redis/RQ or Postgres-backed priority queue
      worker.py                     # single-worker-per-Ollama-instance loop
      priority.py                      # PRIORITY map, enqueue helpers
    storage/
      object_store.py               # MinIO or filesystem interface, content-hash keyed
      postgres_migrations/             # schema migration tooling (e.g. Alembic)
    runs_repository.py                    # `runs` table writes/queries
    monitoring/
      alert_rules.py                        # threshold evaluation
      alert_sender.py                          # email/Slack delivery
    backups/
      pg_dump_job.py                              # nightly dump
      snapshot_rsync_job.py                          # nightly rsync
      restore_test.py                                  # pre-go-live restore verification script
    secrets.py                                            # .env loading, validation
```

## 11. Error Handling & Edge Cases

- Ollama host restart/unavailability mid-queue: jobs `status = 'running'`
  when the host drops should be detected (e.g. a heartbeat/timeout) and
  requeued as `'queued'` rather than left permanently stuck in `'running'`.
- Object store disk-full on the office PC: this should itself be an alert
  condition (extend §7.5's alert list in practice, even though the design
  doc's four conditions don't explicitly name it) — a full disk silently
  breaks snapshot/attachment writes across multiple modules at once.
- Phase 4 hosting split: network partition between the office PC (inference/
  crawl) and the VPS (Postgres/review app) — crawl/extraction workers must
  handle a temporarily unreachable Postgres by buffering/retrying rather than
  dropping results, since the office PC side has no local durable store for
  in-flight `GrantRecord`s otherwise.
- Backup restore test failing before go-live: this is a go/no-go gate for
  launch, not a background task — treat a failed restore test as blocking,
  not advisory.
- Multiple scheduled jobs colliding (e.g. nightly lifecycle recompute and
  nightly health evaluation both wanting to run at midnight): stagger
  cadences slightly (e.g. lifecycle recompute at 00:00, health eval at
  00:30) so they don't contend for the same DB write load simultaneously.

## 12. Testing & Acceptance Criteria

- Unit tests: priority queue correctly orders jobs per the priority map;
  alert rules correctly fire at each threshold boundary.
- Integration test: simulate an Ollama outage mid-job, verify the job is
  requeued rather than lost.
- Restore drill: perform a full backup → restore cycle against a test
  environment, verify data integrity, **before go-live** — this is a
  required, not optional, acceptance step per the design doc.
- Acceptance (Phase 1): Postgres schema + basic scheduler operational,
  supporting Phase 1's other module deliverables.
- Acceptance (Phase 4): monitoring/alerts live and demonstrably tested (a
  deliberately triggered failure produces a real alert); nightly backups
  running with a verified restore; hosting split to the VPS complete with no
  loss of crawl/inference capability on the office PC.

## 13. Open Questions

- VRAM on the office PC — bounds not only module 08's 14B model bake-off
  candidate but also whether Tier 2 (module 05) browser automation can run
  concurrently with inference without resource contention. This is a
  platform-wide open question requiring a concrete hardware inventory check
  early in Phase 1.
- Choice between Redis/RQ and a Postgres-backed queue for the LLM job queue
  is left open by the design doc ("Redis/RQ or Postgres-backed") — Redis is
  also useful for module 04's rate-limiter state, so there's a reasonable
  argument for standardizing on Redis if it's going to be a dependency
  anyway; worth deciding once during Phase 1 setup rather than per-module.
- MinIO vs plain filesystem for object storage is similarly left open —
  plain filesystem is simpler for the Phase 1–3 single-office-PC deployment;
  MinIO becomes more attractive once the Phase 4 hosting split happens and
  multiple hosts need to reach the same object store, unless snapshots stay
  physically colocated with the crawl workers regardless (crawl stays on the
  office PC in Phase 4, so filesystem may remain sufficient — confirm this
  reasoning during Phase 4 planning).

## 14. Implementation Checklist

- [ ] Stand up Postgres and migration tooling (Phase 1 priority).
- [ ] Implement scheduler and register all modules' cadences per §7.1's table.
- [ ] Implement LLM job queue with single-worker-per-Ollama-instance and priority ordering.
- [ ] Implement object store interface (decide MinIO vs filesystem) keyed by content hash.
- [ ] Implement `runs` table and per-run summary writes.
- [ ] Implement monitoring/alert evaluation and email/Slack delivery.
- [ ] Implement nightly backup jobs (`pg_dump` + snapshot rsync).
- [ ] Run and pass a full restore drill before go-live.
- [ ] Implement `.env`/YAML secrets and config conventions; verify no secrets in version control.
- [ ] Execute the Phase 4 hosting split (Postgres + review app to VPS, inference/crawl stays on office PC).
- [ ] Tests per §12.
