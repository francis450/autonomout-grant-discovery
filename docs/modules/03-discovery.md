# Module 03: Discovery

## 1. Purpose

Finds new candidate sources and pages the platform doesn't already know about —
both fresh opportunity pages on the open web (Serper search, RSS, newsletters)
and new funder organizations worth tracking as full Class A sources (via
quarterly Class B prospecting). This is the platform's growth mechanism for the
Source Registry (module 02); without it, the source list never expands beyond
its Phase 1 seed.

## 2. Scope

### In scope
- Daily Serper query-feed generation and execution (Class C discovery).
- RSS ingestion from existing Class A sources, and manual newsletter-forward
  intake.
- URL-deduplication of discovery results against the registry and record store.
- The qualification procedure that promotes a candidate domain from
  `PENDING_QUALIFICATION` to `ACTIVE` (writing the transition via module 02's
  API).
- Quarterly Class B prospecting job (IATI/360Giving/Candid) that outputs a
  ranked funder shortlist for the grants team to approve.

### Out of scope
- Actually fetching/rendering pages at scale on a schedule (module 05, Tiered
  Ingestion — discovery does a lightweight Tier 1 fetch only for qualification,
  not the ongoing crawl).
- Storing/mutating source records (module 02 owns the registry; this module
  calls its API).
- Classifying a fetched page as opportunity/listing/article/etc. — discovery
  reuses module 07's record-type classifier for qualification, it does not own
  that logic.

## 3. Dependencies

- Module 02 (Source Registry): discovery writes new `PENDING_QUALIFICATION`
  sources and triggers promotion to `ACTIVE`.
- Module 01 (Org Profile): query templates are built from pillar keywords ×
  geography, sourced from the profile's `pillars` and `target_regions`.
- Module 07 (Deterministic Pre-Filter): the record-type classifier is reused
  to qualify a candidate page as opportunity/listing.
- Module 04 (Crawl Policy): the qualifying fetch must obey the same robots.txt
  and rate-limit rules as any other crawl.
- Module 05 (Tiered Ingestion): the actual Tier 1 fetch mechanism used for
  qualification is module 05's, invoked here as a library call.

## 4. Roadmap Phase & Exit Criteria

Phase 4 deliverable: "discovery feeds ... source health lifecycle, Class B
prospecting job, full source list active." Not required for Phase 1–3, which
run against the seeded registry only — but the query-template design and
Serper integration can be scaffolded earlier if convenient, since it has no
hard dependency on the review app.

## 5. Inputs & Outputs

**Inputs**: Serper API results, RSS feed content from Class A sources, manually
forwarded newsletter content, IATI Datastore / 360Giving GrantNav / Candid
exports (Class B).

**Outputs**: new rows in module 02's `sources` table (status
`PENDING_QUALIFICATION` → `ACTIVE`), and a quarterly ranked funder shortlist
(CSV or reviewable list) for the grants team.

## 6. Data Model

### Query template

```
QueryTemplate:
  pillar_keyword: str        # from org_profile.pillars keys, expanded to human phrases
  geography: str              # from org_profile.target_regions
  year: int                    # current or next year
  template: str                  # e.g. '"call for proposals" "{keyword}" {geography} {year}'
```

15–25 templated queries per day, built from the cross product of pillar
keywords × geography × year, e.g.:
`"call for proposals" "digital literacy" Kenya 2026`

### Postgres table `discovery_candidates`

```
discovery_candidates
  id                 uuid pk
  url                text
  normalized_url     text unique      -- see module 11 URL-normalization rule
  domain             text
  source_query       text             -- which template/feed produced it
  discovered_at      timestamptz
  qualification_result  text          -- 'pending' | 'opportunity' | 'listing' | 'rejected'
  qualified_at        timestamptz
  promoted_source_id   uuid null fk -> sources.id
```

### Class B prospecting output

```
FunderCandidate:
  funder_name: str
  funder_name_normalized: str
  funder_iati_id: Optional[str]
  total_grants_observed: int
  thematic_overlap_score: float      # heuristic match against org_profile.pillars
  geographic_overlap: bool           # funds in TOH's target_regions
  typical_award_size_usd: tuple[float, float]
  homepage_url: Optional[str]
  recommendation: str                # free-text rationale for the grants team
```

## 7. Functional Requirements

1. **Daily Serper run**: generate 15–25 queries from templates, execute against
   Serper, collect result URLs.
2. **URL dedup**: normalize each result URL (module 11's Tier A normalization
   rule — strip scheme, www, trailing slash, fragment, tracking params) and
   discard any URL already present in `sources.listing_urls`, the record store
   (`grant_records.canonical_url`, module 08), or `discovery_candidates`.
3. **RSS ingestion**: for each `ACTIVE` Class A source with a known RSS feed
   URL, poll daily, extract entry links, feed through the same dedup step.
4. **Manual newsletter intake**: provide a simple intake path (e.g. a forwarding
   email address or an admin-paste form in module 12) that inserts URLs
   directly into `discovery_candidates` with `source_query = 'manual-forward'`.
5. **Qualification**: for each new `discovery_candidates` row, perform a Tier 1
   fetch (module 05) and run the record-type classifier (module 07 §5.1). If
   classified as `opportunity` or `listing`, mark `qualification_result`
   accordingly and increment a per-domain qualified-page counter; otherwise
   mark `rejected`.
6. **Promotion rule**: once a domain accumulates **3 qualified pages**, create
   or update its `sources` row (module 02) with `status = ACTIVE`,
   `origin = 'discovery'`, and set `promoted_source_id` on the contributing
   `discovery_candidates` rows.
7. **Class B prospecting (quarterly)**: pull from IATI Datastore / iati.cloud,
   360Giving GrantNav, and Candid/Foundation Directory (manual export), filter
   to funders active in TOH's `target_regions` and thematic pillars, rank by
   overlap and award-size fit, and produce a `FunderCandidate` shortlist for
   grants-team review. Approved funders are added as Class A sources
   **manually** (this job does not auto-promote — funder prospecting output
   requires a human decision, unlike Class C's automated 3-page promotion
   rule).

## 8. Algorithms / Business Logic

### Query template generation

```
for keyword in org_profile.pillars.keys():
    for geography in org_profile.target_regions + org_profile.operating_countries:
        for template_pattern in QUERY_PATTERNS:   # e.g. 4-6 fixed patterns
            yield template_pattern.format(keyword=humanize(keyword), geography=geography, year=current_year)
# sample down to 15-25 for the day (rotate through the full set over a week
# rather than running all combinations daily, to control Serper API cost)
```

### Qualification promotion counter

```
on qualification_result in ('opportunity', 'listing'):
    domain = extract_domain(url)
    qualified_count = count(discovery_candidates where domain = domain and qualification_result in ('opportunity','listing'))
    if qualified_count >= 3 and source_registry.get(domain) is None or status == 'PENDING_QUALIFICATION':
        source_registry.create_or_update(domain, status='ACTIVE', origin='discovery')
```

## 9. Configuration

| Setting | Value |
|---|---|
| Daily query count | 15–25 |
| Promotion threshold | 3 qualified pages per domain |
| Class B prospecting cadence | Quarterly |
| Serper API key | `.env` (module 16 owns secrets management) |

## 10. Suggested Tech Stack & File Layout

```
app/
  discovery/
    __init__.py
    query_templates.py     # template generation from org profile
    serper_client.py         # Serper API wrapper
    rss_poller.py              # RSS feed ingestion
    manual_intake.py             # newsletter-forward intake
    qualification.py               # Tier 1 fetch + classify + promotion counter
    class_b_prospecting.py           # quarterly funder-shortlist job
    schema.py                          # DiscoveryCandidate, FunderCandidate
```

## 11. Error Handling & Edge Cases

- Serper API failures/rate limits: back off and retry next scheduled run;
  do not block the rest of the pipeline on a discovery failure.
- A domain that qualifies 3 pages but is already `QUARANTINED` in module 02
  (e.g. re-discovered after quarantine) — do not auto-reactivate; leave the
  manual-promotion gate in module 02 authoritative. Only auto-promote from
  `PENDING_QUALIFICATION` or "unknown" (no existing row).
- RSS feed URLs that go stale/404 — log and skip, do not crash the daily
  ingestion run; flag for admin review if a feed fails 5 consecutive times.
- Class B datasets are large (IATI Datastore can return huge result sets) —
  page/stream the query rather than loading entire exports into memory.

## 12. Testing & Acceptance Criteria

- Unit tests: query template generation produces expected query strings from a
  sample org profile; URL dedup correctly rejects known-seen URLs.
- Integration test: feed 3 synthetic "opportunity"-classified pages from one
  fake domain through qualification, assert the domain is promoted to `ACTIVE`
  in module 02.
- Acceptance (Phase 4): a full day's discovery run produces new
  `PENDING_QUALIFICATION`/`ACTIVE` sources traceable to specific queries or
  feeds; a quarterly Class B run produces a reviewable funder shortlist.

## 13. Open Questions

- Exact set of `QUERY_PATTERNS` (the 4-6 fixed phrasings combined with
  keyword × geography × year) is not specified in the design doc beyond one
  example — needs drafting and validation against real search results before
  Phase 4.
- Whether Class B prospecting Candid/Foundation Directory access is available
  to TOH (manual export) or requires a paid licence — ties to the platform-
  wide paywalled-aggregator licensing decision (see module 02 §13).

## 14. Implementation Checklist

- [ ] Define query template patterns and validate against org profile pillars/regions.
- [ ] Implement Serper client + daily scheduled run.
- [ ] Implement RSS poller against `ACTIVE` Class A sources.
- [ ] Implement manual newsletter intake path.
- [ ] Implement `discovery_candidates` schema + URL dedup against registry/record store.
- [ ] Implement qualification (Tier 1 fetch + module 07 classifier) and 3-page promotion rule.
- [ ] Implement quarterly Class B prospecting job and funder shortlist output.
- [ ] Tests per §12.
