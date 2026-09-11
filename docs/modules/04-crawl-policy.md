# Module 04: Crawl Policy

## 1. Purpose

Encodes TOH's ethical-scraping principle as enforceable code: honour
robots.txt, rate-limit per domain, identify the bot truthfully, and never
evade blocks. This module is small but load-bearing — every other module that
fetches a page (05 Tiered Ingestion, 03 Discovery's qualification fetch) must
route through it rather than making raw HTTP requests. It explicitly replaces
v2's stealth/proxy-rotation plan, which conflicted with TOH's principles.

## 2. Scope

### In scope
- robots.txt fetching, parsing, and per-domain caching with weekly re-check.
- Per-domain rate limiting (request spacing, daily page cap, connection limit).
- Bot identification (User-Agent string).
- The policy decision of what happens when a source blocks the bot (quarantine
  + notify, not evade).
- The rule that paywalled content is never scraped behind the paywall.

### Out of scope
- Actually rendering/parsing page content (module 05).
- Marking a source `QUARANTINED`/`RETIRED` in the registry (module 02 owns
  that state; this module supplies the trigger signal — e.g. "robots
  disallows everything" or "block rate exceeded").
- Licensed/paid access to paywalled aggregators (a source-registry/business
  decision, module 02 §13) — this module only enforces "don't scrape around
  a paywall," not how legitimate licensed access is implemented.

## 3. Dependencies

- Module 02 (Source Registry): reads `robots_allowed`, writes weekly re-check
  results; emits the "retire with reason robots" and "quarantine — block rate"
  signals that module 02 acts on.
- Consumed by module 05 (Tiered Ingestion) and module 03 (Discovery) — both
  must call this module's fetch gate before any HTTP request.

## 4. Roadmap Phase & Exit Criteria

Phase 1 deliverable (implicit, required for "Tier 1 fetch for 10 sources" to
be meaningful and ethical from day one). No explicit exit criteria of its own;
it is a correctness gate other modules' exit criteria depend on.

## 5. Inputs & Outputs

**Inputs**: a domain/URL to fetch, on behalf of module 05 or 03.

**Outputs**: either a green light to fetch (with the required delay already
applied) or a refusal (disallowed path, daily cap reached, block-rate
threshold breached) — plus the observations (response code, was it a
challenge page) that module 02 uses for health scoring.

## 6. Data Model

### Postgres table `robots_cache`

```
robots_cache
  domain            text pk
  fetched_at        timestamptz
  rules_raw         text            -- raw robots.txt content
  disallowed_paths  text[]          -- parsed disallow rules for the configured user-agent
  crawl_delay       float null      -- if robots.txt specifies one
  allowed           boolean          -- overall: is anything craw lable
```

### In-memory / Redis per-domain rate state

```
DomainRateState:
  domain: str
  last_request_at: datetime
  requests_today: int
  day: date                 # for daily counter reset
  active_connections: int   # enforce single connection per domain
```

## 7. Functional Requirements

1. **robots.txt fetch & honour**: before crawling any domain for the first
   time, and weekly thereafter, fetch `https://{domain}/robots.txt`, parse
   disallow rules for the platform's user-agent (falling back to `*` if no
   specific entry), and cache the result. Disallowed paths are never crawled,
   full stop — no override mechanism.
2. **Full-disallow handling**: if robots.txt disallows the entire site for the
   platform's user-agent, signal module 02 to mark the source `RETIRED` with
   reason `"robots"`.
3. **Bot identification**: every request sets
   `User-Agent: TechOnHandGrantBot/1.0 (+https://techonhand.org/bot; grants@techonhand.org)`.
   This is not configurable per-request — it is a fixed, honest identification
   string.
4. **Rate limiting**: enforce, per domain:
   - 1 request per 3–5 seconds (randomized within range to avoid a
     suspiciously exact cadence, which is about politeness/predictability, not
     evasion).
   - Max 200 pages per domain per day.
   - Single concurrent connection per domain.
5. **No evasion**: explicitly, the module must never implement or allow proxy
   rotation, CAPTCHA solving, or login-wall bypass. If a fetch returns a
   challenge page (CAPTCHA, Cloudflare interstitial) or a 4xx/5xx, record it
   as a block observation and stop — do not retry with different
   headers/IPs/user-agents to get around it.
6. **Paywall rule**: sources known to be paywalled aggregators (Candid,
   Instrumentl, DevelopmentAid premium pages) must be excluded from this
   module's normal fetch gate entirely — they are only accessed via licensed
   account/export mechanisms outside this module's scope, never via the
   scraping path.
7. **Block signal to registry**: every fetch attempt's outcome (success,
   4xx, 5xx, challenge) is reported back so module 02 can compute the
   `block_rate` health metric and act on the thresholds it owns (> 20% →
   `DEGRADED`, cadence halved; > 50% for 3 runs → `QUARANTINED`).

## 8. Algorithms / Business Logic

### Fetch gate (called by module 05 before every request)

```
def can_fetch(domain: str, path: str) -> FetchDecision:
    robots = get_or_refresh_robots(domain)   # weekly TTL
    if not robots.allowed or path in robots.disallowed_paths:
        return FetchDecision(allowed=False, reason="robots_disallowed")

    state = get_rate_state(domain)
    if state.day != today():
        state.requests_today = 0
        state.day = today()
    if state.requests_today >= 200:
        return FetchDecision(allowed=False, reason="daily_cap_reached")
    if state.active_connections >= 1:
        return FetchDecision(allowed=False, reason="connection_in_use")

    delay = max(robots.crawl_delay or 0, random.uniform(3, 5))
    wait_until = state.last_request_at + delay
    if now() < wait_until:
        return FetchDecision(allowed=False, reason="rate_limited", retry_after=wait_until)

    return FetchDecision(allowed=True)
```

Callers must treat `allowed=False` as "not now" (re-queue for later within the
same run or next scheduled run), not as a permanent failure, except for
`robots_disallowed` which is permanent for that path.

## 9. Configuration

| Setting | Value |
|---|---|
| User-Agent | `TechOnHandGrantBot/1.0 (+https://techonhand.org/bot; grants@techonhand.org)` |
| Request spacing | 3–5 seconds per domain, randomized |
| Daily page cap | 200 per domain |
| Concurrent connections | 1 per domain |
| robots.txt re-check | Weekly |
| Proxy rotation | Never |
| CAPTCHA solving | Never |
| Login-wall bypass | Never |

## 10. Suggested Tech Stack & File Layout

```
app/
  crawl_policy/
    __init__.py
    robots.py          # fetch, parse, cache robots.txt
    rate_limiter.py       # per-domain rate state (Redis-backed for multi-worker safety)
    fetch_gate.py           # can_fetch() — the single entry point other modules call
    user_agent.py             # constant string, single source of truth
    schema.py                   # FetchDecision, DomainRateState
```

Use Redis (already planned for the LLM job queue in module 16) to back
`DomainRateState` so rate limits hold correctly across multiple async crawl
workers, not just within one process.

## 11. Error Handling & Edge Cases

- robots.txt itself 404s or is unreachable: per standard convention, treat as
  "everything allowed" but log it — do not treat a missing robots.txt as a
  block signal.
- robots.txt parse errors (malformed file): fail safe — treat as fully
  disallowed for that domain and flag for manual inspection, rather than
  guessing.
- A source's `crawl_cadence_hours` (module 02) combined with the 200-pages/day
  cap could still exceed politeness on a small site — the daily cap and
  per-request spacing both apply simultaneously; the more restrictive one
  wins at any moment.
- Clock skew / long-running processes: recompute `today()` per check, don't
  cache a stale day boundary across a long-running worker process.

## 12. Testing & Acceptance Criteria

- Unit tests: robots.txt parsing correctly resolves specific-user-agent vs
  wildcard rules; rate limiter correctly enforces spacing, daily cap, and
  single-connection constraints under concurrent calls.
- Integration test: simulate a domain returning a CAPTCHA challenge on every
  request — assert the module reports block observations and never retries
  with altered headers/IPs.
- Acceptance: a live crawl run against a real robots.txt-restricted site
  demonstrably skips disallowed paths; a live run against a rate-limited
  domain never exceeds 200 requests/day or violates the 3–5s spacing, verified
  from request logs/timestamps.

## 13. Open Questions

- List of specific paywalled aggregators TOH holds licences for (shared open
  question with module 02 §13) — determines which sources this module
  excludes from its normal fetch gate entirely versus routes through a
  licensed-access path outside this module.

## 14. Implementation Checklist

- [ ] Implement robots.txt fetch/parse/cache with weekly TTL.
- [ ] Implement Redis-backed per-domain rate limiter (spacing, daily cap, single connection).
- [ ] Implement fixed User-Agent constant and ensure all HTTP calls in modules 03/05 use it.
- [ ] Implement `can_fetch()` gate as the mandatory entry point for all fetches.
- [ ] Implement block-observation reporting back to module 02.
- [ ] Explicitly verify (code review + test) that no proxy rotation, CAPTCHA-solving, or header-spoofing-to-evade code paths exist anywhere in the crawl stack.
- [ ] Tests per §12.
