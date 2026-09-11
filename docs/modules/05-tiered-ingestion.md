# Module 05: Tiered Ingestion

## 1. Purpose

Fetches page content at the right cost tier for each source: a cheap direct
API call where one exists, a headless-browser markdown render as the default,
and a full browser-automation agent only for the small minority of sites that
genuinely require multi-step interaction. This module is the workhorse that
turns a source's `listing_urls` into raw page content for downstream
classification and extraction.

## 2. Scope

### In scope
- Tier 0 (direct API fetch), Tier 1 (headless markdown via Crawl4AI), and
  Tier 2 (Playwright + Browser-Use agent) fetch mechanisms.
- The Tier 1 → Tier 2 escalation rule and its guardrails (step/time caps,
  logging).
- Listing-page crawling (extracting candidate detail links) versus detail-page
  fetching, and the dedup-driven decision of which detail pages actually need
  a fetch.

### Out of scope
- Attachment (PDF/DOCX) download and parsing — module 06.
- robots.txt/rate-limit enforcement — module 04 (this module calls module 04's
  gate before every fetch).
- Deciding whether fetched content is an opportunity — module 07.
- Where the fetched content is stored — module 16 owns the object store, this
  module writes to it via a storage interface.

## 3. Dependencies

- Module 02 (Source Registry): reads `listing_urls[]`, `ingest_tier`,
  `crawl_cadence_hours`, `priority`; writes `pages_fetched`, `last_success_at`,
  `last_error`.
- Module 04 (Crawl Policy): every fetch is gated through `can_fetch()`.
- Module 11 (Deduplication): Tier A URL-dedup determines whether a detail link
  needs fetching at all (module 08 §content_hash change also feeds this).
- Module 16 (Runtime & Operations): object store for raw snapshots; scheduler
  triggers ingestion runs.
- Feeds module 07 (Deterministic Pre-Filter) and module 08 (Extraction Engine)
  with fetched page content.

## 4. Roadmap Phase & Exit Criteria

Phase 1: "Tier 1 fetch for 10 sources" is an explicit deliverable; exit
criteria require the chosen extraction model to hit accuracy/throughput
targets on content this module supplies, so Tier 1 must be reliable by end of
Phase 1.

Phase 5: "EU F&T and other API connectors" (Tier 0) and "Playwright/
Browser-Use fallback for enabled sources" (Tier 2) are explicit Phase 5
deliverables. Exit criterion: "Tier 2 covers its enabled sources within caps;
no regression on eval report." Tier 2 is expected to cover fewer than 10
sources.

## 5. Inputs & Outputs

**Inputs**: a `Source` record (module 02) due for a crawl per its cadence.

**Outputs**: raw page content (markdown for Tier 1/2, structured JSON for Tier
0) written to the object store with a content hash, plus a list of candidate
detail-page URLs (from listing crawls) queued for module 07's classifier.

## 6. Data Model

### Tier definitions

| Tier | Mechanism | Used for | Trigger |
|---|---|---|---|
| 0 — API | Direct JSON/XML fetch | EU Funding & Tenders search endpoint, Grants.gov search2, GlobalGiving, IATI/360Giving (Class B only) | Source has a published endpoint |
| 1 — Headless markdown | Crawl4AI fetch → JS render → clean markdown | 85–90% of Class A sources | Default |
| 2 — Browser agent | Playwright + Browser-Use | Multi-step search forms, sites where the listing is only reachable through interaction | Tier 1 escalation rule (§8) |

### Postgres table `fetch_runs`

```
fetch_runs
  id               uuid pk
  source_id        uuid fk -> sources.id
  url              text
  tier_used        smallint
  fetched_at       timestamptz
  status_code      int null
  content_hash     text            -- sha256 of fetched content, see module 08 §8
  token_count      int null          -- for tier-1 markdown, used by escalation rule
  had_dated_content boolean null
  blocked          boolean
  error            text null
  duration_ms      int
```

### Tier 2 step log

```
tier2_run_steps
  fetch_run_id     uuid fk -> fetch_runs.id
  step_number      int
  action           text        -- e.g. 'click', 'fill', 'navigate'
  target           text
  timestamp        timestamptz
```

## 7. Functional Requirements

1. **Scheduling input**: for each `ACTIVE` source due per `crawl_cadence_hours`,
   enqueue a listing-crawl job at the tier indicated by `ingest_tier`.
2. **Tier 0 fetch**: call the source's documented API/endpoint directly,
   parse the structured response (JSON/XML) into the same downstream shape
   listing/detail crawls produce (candidate URLs + content), skipping markdown
   rendering entirely.
3. **Tier 1 fetch**: use Crawl4AI to render JS and produce clean markdown.
   This is the default for any source without a Tier 0 endpoint and not
   flagged for Tier 2.
4. **Tier 2 fetch**: use Playwright driven by a Browser-Use agent to navigate
   multi-step interactions (e.g. filling a search form, paging through
   results) that a static/Tier-1 fetch cannot reach. Hard caps: **40 steps**
   and **3 minutes** per source per run; every step is logged
   (`tier2_run_steps`).
5. **Listing vs detail separation**: a listing-page crawl extracts *candidate
   detail links only* (via URL patterns plus a lightweight link-text
   classifier) — it does not attempt full record extraction at the listing
   level.
6. **Detail-page fetch gating**: a detail page is fetched only if (a) its
   normalized URL is not already in the record store (module 11 Tier A dedup),
   or (b) it is already known but its content hash may have changed (re-check
   logic, module 10). This keeps LLM-adjacent work proportional to *new*
   opportunities, not to total page count.
7. **All fetches gated by module 04**: no HTTP request of any kind bypasses
   `crawl_policy.can_fetch()`.
8. **Escalation bookkeeping**: for Tier 1 sources, track per-run whether the
   markdown was under 400 tokens or contained no dated content, and whether
   the fetch was blocked — feed this into the escalation rule (§8).

## 8. Algorithms / Business Logic

### Tier 1 → Tier 2 escalation rule (§4.1 of the design doc)

A source escalates to Tier 2 only when **all** of the following hold on
**three consecutive runs**:

```
(a) tier1_markdown_tokens < 400 OR has_no_dated_content
(b) NOT blocked (no 403/429/challenge)
(c) robots.txt permits the path (module 04)
(d) a human has enabled Tier 2 for this source in the registry (module 02)
```

```python
def evaluate_escalation(source_id: str) -> bool:
    last_three = get_last_n_tier1_runs(source_id, n=3)
    if len(last_three) < 3:
        return False
    if not source_registry.tier2_enabled(source_id):
        return False
    for run in last_three:
        if run.blocked:
            return False
        if not robots_permits(source_id):
            return False
        if not (run.token_count < 400 or not run.had_dated_content):
            return False
    return True   # escalate to Tier 2 on next run
```

Tier 2 runs are capped at 40 steps / 3 minutes; if a run hits either cap
without completing, it terminates, logs partial results, and is treated as a
failed Tier 2 attempt (does not retry immediately — waits for the next
scheduled cadence).

### Listing → detail link extraction

```
candidate_links = extract_links(listing_markdown, url_patterns_for_source)
candidate_links = classify_link_text(candidate_links)   # lightweight heuristic, not full LLM classification
new_or_changed = [l for l in candidate_links if not in_record_store(normalize(l.url)) or content_may_have_changed(l.url)]
enqueue_detail_fetch(new_or_changed)
```

## 9. Configuration

| Setting | Value |
|---|---|
| Tier 2 step cap | 40 steps |
| Tier 2 time cap | 3 minutes |
| Escalation window | 3 consecutive Tier 1 runs |
| Escalation token threshold | < 400 tokens |
| Tier 2 enablement | Manual, per-source flag in registry |

## 10. Suggested Tech Stack & File Layout

```
app/
  ingestion/
    __init__.py
    tier0_api.py           # per-source API adapters (EU F&T, Grants.gov, GlobalGiving, IATI/360Giving)
    tier1_crawl4ai.py         # headless markdown fetch
    tier2_browser_agent.py      # Playwright + Browser-Use, step-capped
    escalation.py                  # tier1->tier2 rule evaluation
    listing_parser.py                # candidate detail link extraction
    scheduler_adapter.py               # reads due sources, enqueues fetch jobs
    schema.py                            # FetchRun, Tier2RunStep
```

Tier 0 adapters are inherently source-specific — plan for one small adapter
module per API (EU F&T, Grants.gov search2, GlobalGiving, IATI, 360Giving)
implementing a common `TierZeroAdapter` interface (`fetch() -> List[RawRecord]`).

## 11. Error Handling & Edge Cases

- Tier 0 API schema changes/deprecations: adapters should validate response
  shape and raise a distinguishable error so it surfaces as a monitoring alert
  (module 16), not a silent empty result.
- Tier 1 JS-heavy pages that render empty markdown even after JS execution:
  counts toward the escalation rule's "< 400 tokens" condition rather than
  being treated as a crawl failure.
- Tier 2 agent gets stuck in a loop (e.g. repeatedly clicking a cookie banner):
  the 40-step cap is the safety net — ensure step logging makes this
  diagnosable after the fact.
- A source flips from Tier 1 to Tier 2 eligibility but a human hasn't enabled
  it yet: stays on Tier 1 indefinitely (condition (d) is a hard gate) — log
  this as a candidate for admin attention (module 02/12), don't auto-enable.
- Listing pages that paginate: the link-text classifier and URL-pattern
  extraction must handle "next page" navigation within Tier 1's capabilities;
  pagination requiring form interaction is itself a Tier 2 signal.

## 12. Testing & Acceptance Criteria

- Unit tests: escalation rule correctly requires all four conditions across
  exactly 3 consecutive runs (test boundary cases: 2 runs, 3 runs with one
  blocked, 3 runs with Tier 2 not enabled).
- Integration test: Tier 1 fetch against a real or fixture site produces clean
  markdown; Tier 2 agent completes a scripted multi-step scenario within caps.
- Golden-set-adjacent test: for the 10 Phase 1 sources, verify Tier 1 fetch
  succeeds and produces content sufficient for module 08's accuracy targets.
- Acceptance (Phase 1): 10 sources reliably fetched via Tier 1 on schedule,
  content stored with correct hashes, feeding the extraction pipeline.
- Acceptance (Phase 5): at least one Tier 0 adapter live against a real API;
  Tier 2 covers its enabled sources within step/time caps with no regression
  in the eval report (module 15).

## 13. Open Questions

- Exact list of which ~10 sources get Tier 2 enabled (design doc estimates
  "fewer than 10 sources") — depends on Phase 1–4 observation of which
  sources repeatedly fail the Tier 1 escalation conditions.
- VRAM/compute headroom on the office PC affects whether Tier 2's Playwright
  browser instances can run concurrently with Tier 1 crawls and Ollama
  inference without contention — ties to the platform-wide VRAM open question
  (see module 16 and the README's open-decisions list).

## 14. Implementation Checklist

- [ ] Implement Tier 1 Crawl4AI fetch path (Phase 1 priority).
- [ ] Implement listing vs detail link extraction and dedup-gated detail fetching.
- [ ] Wire every fetch through module 04's `can_fetch()`.
- [ ] Implement `fetch_runs` storage with content hashing.
- [ ] Implement escalation-rule tracking and evaluation (Phase 1–4, even if Tier 2 itself ships Phase 5).
- [ ] Phase 5: implement Tier 0 adapters (EU F&T, Grants.gov, GlobalGiving, IATI, 360Giving).
- [ ] Phase 5: implement Tier 2 Playwright + Browser-Use agent with step/time caps and step logging.
- [ ] Tests per §12.
