# Module Index — Autonomous Grant Discovery Platform

Source of truth: `Grant_Discovery_Platform_Design_v3.docx` (11 Sept 2026). This index and
the 16 module specs in this folder decompose that design into independently
implementable units. Hand a single module file to an agent (or a developer) and
it should contain everything needed to build that module without re-reading the
full design doc — schemas, algorithms, config, acceptance criteria, and explicit
dependency boundaries.

## Project context (applies to every module)

- **Product**: discovers open funding opportunities relevant to Tech On Hand (TOH),
  extracts them into a structured record, scores them against TOH's org profile,
  and delivers a reviewed shortlist to the grants team weekly.
- **Boundary**: this is a new, separate codebase from `toh-grants-engine`. No shared
  code, DB, scoring, or ERPNext integration. The only carryover is a one-time export
  of the source list (URL, name, category, notes) used to seed module 02 (Source
  Registry).
- **Success criteria** (platform-wide, not any one module's alone):
  - Yield: ≥ 20 reviewed-and-recommended opportunities/week within 8 weeks of go-live.
  - Precision: ≥ 60% of "Recommended" records confirmed worth pursuing by the grants team.
  - Junk rate: < 10% of queued records are expired/non-grant/aggregator pages.
  - Latency: a newly published opportunity appears in the queue within 48 hours.

## The 16 modules

| # | Module | File | Roadmap phase |
|---|--------|------|----------------|
| 01 | Org Profile | [01-org-profile.md](01-org-profile.md) | 1 |
| 02 | Source Registry & Health Lifecycle | [02-source-registry.md](02-source-registry.md) | 1, 4 |
| 03 | Discovery | [03-discovery.md](03-discovery.md) | 4 |
| 04 | Crawl Policy | [04-crawl-policy.md](04-crawl-policy.md) | 1 |
| 05 | Tiered Ingestion | [05-tiered-ingestion.md](05-tiered-ingestion.md) | 1, 5 |
| 06 | Attachment Parsing | [06-attachment-parsing.md](06-attachment-parsing.md) | 3 |
| 07 | Deterministic Pre-Filter | [07-deterministic-prefilter.md](07-deterministic-prefilter.md) | 2 |
| 08 | Extraction Engine | [08-extraction-engine.md](08-extraction-engine.md) | 1, 3 |
| 09 | Scoring Engine | [09-scoring-engine.md](09-scoring-engine.md) | 3 |
| 10 | Record Lifecycle & Re-checks | [10-record-lifecycle.md](10-record-lifecycle.md) | 2 |
| 11 | Deduplication | [11-deduplication.md](11-deduplication.md) | 2, 3 |
| 12 | Review App | [12-review-app.md](12-review-app.md) | 4 |
| 13 | Feedback Loop | [13-feedback-loop.md](13-feedback-loop.md) | 4 |
| 14 | Delivery | [14-delivery.md](14-delivery.md) | 4 |
| 15 | Evaluation Harness | [15-evaluation-harness.md](15-evaluation-harness.md) | 1 |
| 16 | Runtime & Operations | [16-runtime-ops.md](16-runtime-ops.md) | 1, 4 |

## Dependency graph (build order)

```
01 Org Profile ─────────────┐
02 Source Registry ──┬──────┼──> 09 Scoring Engine ──> 10 Lifecycle ──> 13 Feedback Loop
03 Discovery ─────────┤     │                                  │
04 Crawl Policy ───────┼──> 05 Tiered Ingestion ─┐              │
                        │                         │              │
                        │    06 Attachment Parsing ┤              │
                        │                         v              │
                        └──────────────────> 07 Prefilter         │
                                                    │              │
                                                    v              │
                                             08 Extraction Engine  │
                                                    │              │
                                                    v              v
                                             11 Deduplication ──> 12 Review App ──> 14 Delivery
                                                                       │
15 Evaluation Harness (cuts across 07/08/09 — needed before any of them ships)
16 Runtime & Operations (cuts across everything — scheduler, queue, storage, monitoring)
```

Practical build order matches the roadmap phases:
1. **Phase 1**: 01, 02 (seed only), 04, 05 (Tier 1 only), 15, skeleton of 16 (Postgres + scheduler)
2. **Phase 2**: 07, 10 (lifecycle recompute only), 11 (Tier A/C only)
3. **Phase 3**: 08, 06, 09, 11 (Tier B)
4. **Phase 4**: 12, 13, 14, 02 (health lifecycle automation), 03, 16 (full monitoring/backups/VPS split)
5. **Phase 5**: 05 (Tier 0 + Tier 2), optional ERPNext export in 14

## Cross-cutting artifacts referenced by multiple modules

- **`GrantRecord` Pydantic schema** — canonical definition lives in
  [08-extraction-engine.md](08-extraction-engine.md) §6. Modules 07, 09, 10, 11, 12
  read/write subsets of it; they reference field names rather than redefining them.
- **`org_profile.yaml`** — canonical definition in [01-org-profile.md](01-org-profile.md).
  Read (never written) by 07 and 09.
- **Postgres schema** — each module lists the tables/columns it owns under its own
  "Data Model" section; [16-runtime-ops.md](16-runtime-ops.md) owns cross-table
  concerns (migrations, backups, the `runs` table).

## Open decisions (platform-wide, not owned by any single module)

These block full implementation and need an answer from TOH before or during the
listed module's build:

1. Org profile values (registration years, audit years available, annual budget) — blocks 01 and the scoring calibration in 09.
2. Which paywalled aggregators TOH holds licences for, and whether exports can be ingested — blocks 02/03 source classification.
3. Review app stack, Next.js vs FastAPI+HTMX — decide in 12 based on team maintenance capability.
4. Whether the Kenyan entity applies to Kenya-only calls under its own name — affects `INCORPORATED_AFRICA` eligibility scoring in 09.
5. VRAM on the office PC — bounds the 14B model option in the 08 model bake-off.

Each module file repeats the decisions relevant to it under its own "Open Questions" section.
