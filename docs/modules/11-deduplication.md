# Module 11: Deduplication

## 1. Purpose

The same grant opportunity routinely appears from multiple sources: the
funder's own page, an aggregator's listing, a discovery-feed hit, a
re-crawled URL with different tracking parameters. This module ensures each
real-world opportunity exists as exactly one `GrantRecord`, using three
increasingly semantic tiers of matching, and never silently loses information
when merging.

## 2. Scope

### In scope
- Tier A (URL-based) dedup: the cheap, always-on first line of defense.
- Tier B (Entity-based) dedup: fuzzy matching across differently-sourced
  records of the same real-world grant.
- Tier C (Snapshot-based) dedup: content-hash provenance and change detection.
- Funder name normalization and the alias table.
- The merge procedure when a Tier B match is confirmed.

### Out of scope
- Deciding a record's score/relevance — module 09 (dedup runs independently
  of scoring; a merge can happen before or after scoring, but merge logic
  itself doesn't compute scores).
- Content-hash computation itself — defined in module 08 §8 as
  `sha256(page_markdown + attachment_text)`; this module consumes and stores
  it, doesn't define the hash function.
- Re-check scheduling — module 10 (module 10 uses this module's Tier A
  dedup/content-hash-change detection as an input to its own logic, but this
  module doesn't own re-check cadence).

## 3. Dependencies

- Module 05 (Tiered Ingestion): Tier A URL dedup gates whether a detail page
  even gets fetched — this module's normalization function is called by
  module 05 before every detail fetch.
- Module 08 (Extraction Engine): supplies `content_hash`,
  `funder_name_normalized`, `grant_title`, `extraction_confidence` — all
  inputs to Tier B/C matching and the merge decision.
- Module 02 (Source Registry) / Module 03 (Discovery): both call this
  module's URL normalization for their own dedup needs, reusing the same
  function rather than duplicating it.
- Module 15 (Evaluation Harness): measures dedup metrics (duplicate pairs
  found/seeded, false merges) against the golden set.

## 4. Roadmap Phase & Exit Criteria

Phase 2 deliverable: "Tier A/C dedup, snapshot store." Phase 3 deliverable:
"Tier B dedup." Phase 3 exit criterion explicitly includes **zero false
merges** — this is a hard, non-negotiable bar (a false merge silently loses a
distinct real opportunity), stricter than the precision target for scoring.

## 5. Inputs & Outputs

**Inputs**: `canonical_url`, `funder_name_normalized`, `grant_title`,
`closing_date`, `content_hash`, `extraction_confidence` from newly extracted
or re-checked `GrantRecord`s.

**Outputs**: either a new `GrantRecord` (no match found), an updated
`last_seen_at`/re-extraction trigger (Tier A URL match), or a merged record
with unioned `sources[]`/`attachments[]` (Tier B entity match confirmed).

## 6. Data Model

| Tier | Key | On match |
|---|---|---|
| A — URL | `sha256(canonical_url)` after stripping scheme, `www`, trailing slash, fragment, and tracking parameters (`utm_*`, `fbclid`, `gclid`, `ref`, session ids) | Update `last_seen_at`; re-extract only if `content_hash` changed |
| B — Entity | `funder_name_normalized + title_normalized` (lowercase, punctuation and stop words removed, whitespace collapsed); candidates found by **trigram similarity ≥ 0.85** on title within the same normalized funder; `closing_date` within **±7 days** is a *confirming signal*, not part of the key | Merge: append `SourceRef`, keep the record with higher `extraction_confidence` as canonical, union `attachments` |
| C — Snapshot | `sha256(page markdown + attachment text)` stored with the raw snapshot in object storage | Provenance only; used to detect content change (feeds module 10) |

### Postgres table `url_dedup_index` (Tier A)

```
url_dedup_index
  normalized_url_hash   text pk       -- sha256(normalized_url)
  grant_record_id         uuid fk -> grant_records.id
  first_seen_at              timestamptz
  last_seen_at                 timestamptz
```

### Postgres table `funder_aliases`

```
funder_aliases
  alias              text pk         -- e.g. 'EC', 'European Commission', 'EU Funding & Tenders'
  canonical_name       text          -- e.g. 'European Commission'
  added_by               text        -- 'seed' | reviewer username (grown from review-time merges)
  added_at                  timestamptz
```

### Merge audit table `record_merges`

```
record_merges
  id                    uuid pk
  canonical_record_id     uuid fk -> grant_records.id
  merged_record_id          uuid       -- the record that was absorbed (kept for audit, not a live row)
  merge_tier                  text     -- 'A' | 'B'
  matched_on                    jsonb   -- similarity score, matched fields, for audit/debugging
  merged_at                       timestamptz
```

## 7. Functional Requirements

### 7.1 Tier A — URL dedup

1. **Normalization function** (single shared implementation, reused by
   modules 02, 03, 05):
   - Strip scheme (`http://`/`https://`).
   - Strip leading `www.`.
   - Strip trailing slash.
   - Strip URL fragment (`#...`).
   - Strip known tracking parameters: `utm_*`, `fbclid`, `gclid`, `ref`, and
     session-id-shaped query params.
   - Hash the result: `sha256(normalized_url)`.
2. **Lookup before fetch**: before module 05 fetches a detail page, check
   `url_dedup_index` — if present, skip the fetch **unless** the content may
   have changed (re-check logic owned by module 10, which itself consults
   this index).
3. **On match**: update `last_seen_at`; trigger re-extraction only if the
   newly observed `content_hash` differs from the stored one.

### 7.2 Tier B — Entity dedup

1. **Normalization**: lowercase, strip punctuation and stop words, collapse
   whitespace, for both `funder_name` (via the alias table first) and
   `grant_title`.
2. **Candidate search**: within records sharing the same normalized funder,
   find titles with **trigram similarity ≥ 0.85** against the new record's
   normalized title.
3. **Confirming signal**: if a candidate also has `closing_date` within **±7
   days** of the new record's `closing_date`, treat this as increasing
   confidence in the match — but note it is **not part of the match key
   itself** (a candidate can match on title similarity alone; the date
   proximity is corroborating evidence surfaced in the merge audit, not a
   required condition).
4. **Merge procedure on confirmed match**:
   - Append the new record's `SourceRef` to the canonical record's
     `sources[]` list.
   - The record with the **higher `extraction_confidence`** becomes/remains
     canonical; if the new record has higher confidence, its field values
     replace the previously-canonical record's fields (except `sources[]`
     and `attachments[]`, which are unioned, not replaced).
   - Union `attachments[]` (dedup by `content_hash` within the union).
   - Log the merge in `record_merges` for audit and false-merge review.

### 7.3 Tier C — Snapshot dedup

1. **Storage**: every fetched page's markdown + attachment text is hashed
   (`content_hash`, defined in module 08 §8) and the raw snapshot stored in
   object storage keyed by that hash (module 16 owns the object store
   itself).
2. **Purpose**: provenance only — this tier does not merge records. It is
   the mechanism module 10 uses to detect "has this specific page's content
   changed since we last looked," and it lets two different URLs that happen
   to serve byte-identical content be recognized as such without a Tier B
   fuzzy match being necessary.

### 7.4 Funder normalization

Maintain an alias table (`funder_aliases`) seeded manually (e.g. "European
Commission" / "EC" / "EU Funding & Tenders" → canonical `European
Commission`) and **grown from review-time merges** — when a human reviewer
in module 12 confirms two records are the same funder under different names,
that becomes a new alias table entry, feeding back into future Tier B
matching automatically.

## 8. Algorithms / Business Logic

### URL normalization

```python
TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
                    "fbclid", "gclid", "ref"}
SESSION_ID_PATTERN = re.compile(r"^(sid|session|sessionid|phpsessid)$", re.I)

def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    netloc = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/")
    query_params = [(k, v) for k, v in parse_qsl(parsed.query)
                    if k not in TRACKING_PARAMS and not SESSION_ID_PATTERN.match(k)]
    query = urlencode(sorted(query_params))
    return f"{netloc}{path}" + (f"?{query}" if query else "")

def url_hash(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode()).hexdigest()
```

### Tier B candidate matching

```python
def find_tier_b_match(record: GrantRecord) -> Optional[GrantRecord]:
    funder_norm = resolve_alias(record.funder_name)  # via funder_aliases table
    title_norm = normalize_title(record.grant_title)
    candidates = query_records(funder_name_normalized=funder_norm)
    for candidate in candidates:
        similarity = trigram_similarity(title_norm, normalize_title(candidate.grant_title))
        if similarity >= 0.85:
            date_confirms = (record.closing_date and candidate.closing_date and
                              abs((record.closing_date - candidate.closing_date).days) <= 7)
            return candidate   # date_confirms logged in record_merges.matched_on, not required
    return None

def merge_records(canonical: GrantRecord, incoming: GrantRecord) -> GrantRecord:
    if incoming.extraction_confidence > canonical.extraction_confidence:
        canonical, incoming = incoming, canonical   # incoming becomes canonical
    canonical.sources = union_sources(canonical.sources, incoming.sources)
    canonical.attachments = union_attachments(canonical.attachments, incoming.attachments)
    log_merge(canonical.grant_id, incoming.grant_id, tier="B",
              matched_on={"trigram_similarity": similarity, "date_confirms": date_confirms})
    return canonical
```

### Title normalization

```python
STOP_WORDS = {"the", "a", "an", "for", "of", "and", "to", "in"}

def normalize_title(title: str) -> str:
    text = re.sub(r"[^\w\s]", "", title.lower())
    words = [w for w in text.split() if w not in STOP_WORDS]
    return " ".join(words)
```

## 9. Configuration

| Setting | Value |
|---|---|
| Tier B title similarity threshold | ≥ 0.85 (trigram) |
| Tier B date confirming window | ±7 days (signal only, not required) |
| Tracking params stripped | `utm_*`, `fbclid`, `gclid`, `ref`, session-id patterns |
| False-merge target | 0 |

## 10. Suggested Tech Stack & File Layout

```
app/
  dedup/
    __init__.py
    url_normalize.py         # Tier A — single shared implementation
    tier_a_index.py              # url_dedup_index repository
    title_normalize.py               # for Tier B
    funder_alias.py                     # alias resolution + review-time growth
    tier_b_matching.py                     # trigram similarity search + merge
    merge.py                                  # merge_records() + record_merges audit log
    snapshot_store.py                            # Tier C — content hashing + object store interface
```

Use Postgres `pg_trgm` extension for trigram similarity — it gives
`similarity()` and a GIN/GiST trigram index directly, avoiding a custom
fuzzy-matching implementation.

## 11. Error Handling & Edge Cases

- Two records that are genuinely different opportunities from the same
  funder with similar titles (e.g. "2026 Innovation Grant" recurring
  annually as separate calls) could trigger a false Tier B match — this is
  exactly the zero-false-merge risk the Phase 3 exit criterion targets;
  mitigate by treating a large `closing_date` gap (e.g. > 300 days) as
  evidence *against* merging even at high title similarity, since annual
  recurrence should produce separate records connected via module 10's
  reopening-watch mechanism, not a Tier B merge.
- A Tier B merge where both records have attachments referencing the same
  `content_hash` (identical file linked twice): union must dedupe by hash,
  not create duplicate `Attachment` entries.
- Alias table conflicts (an alias mapped to two different canonical names
  by different reviewers): last-write-wins with an audit trail
  (`added_by`, `added_at`); surface conflicts for admin review rather than
  auto-resolving silently.
- Very high crawl volume making Tier B's per-funder candidate search slow:
  index on `funder_name_normalized` and use Postgres trigram indexing so the
  search stays performant as the record store grows.

## 12. Testing & Acceptance Criteria

- Unit tests: URL normalization strips exactly the specified components and
  is idempotent (`normalize(normalize(url)) == normalize(url)`); title
  normalization correctly removes stop words/punctuation.
- Unit tests: trigram similarity threshold boundary (0.85 exactly matches,
  0.84 doesn't) using known string pairs.
- Integration test: two records for the same real grant scraped from
  different sources (e.g. funder site + aggregator) correctly merge with
  sources unioned and the higher-confidence record's fields preserved.
- Regression test: two records for what *should* be distinct annual
  recurrences of a similar-titled grant do **not** merge (validates the
  date-gap safeguard).
- Acceptance (Phase 2): Tier A dedup live, preventing redundant detail-page
  fetches; Tier C snapshot store live, content-hash change detection working.
- Acceptance (Phase 3): Tier B dedup live with **zero false merges** measured
  against the golden set (module 15) — this is a hard bar, not a target to
  approach.

## 13. Open Questions

None specific to this module — the tiered dedup design is fully specified.
The false-merge-vs-annual-recurrence distinction (§11) is an implementation
detail the team should validate carefully against real examples during
Phase 3 golden-set testing.

## 14. Implementation Checklist

- [ ] Implement shared URL normalization function; wire into modules 02/03/05 dedup calls.
- [ ] Implement `url_dedup_index` (Tier A) with fetch-skip logic in module 05.
- [ ] Implement title normalization and Postgres `pg_trgm`-based similarity search (Tier B).
- [ ] Implement funder alias table, seeded manually, with review-time growth hook (module 12/13).
- [ ] Implement merge procedure (higher-confidence-wins, sources/attachments unioned) with audit logging.
- [ ] Implement recurrence safeguard against false merges on annual re-postings.
- [ ] Implement Tier C content-hash snapshot storage (coordinate with module 16's object store).
- [ ] Tests per §12, with explicit zero-false-merge validation against the golden set.
