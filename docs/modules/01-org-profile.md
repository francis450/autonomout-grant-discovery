# Module 01: Org Profile

## 1. Purpose

Every scoring decision the platform makes is a comparison between a grant record
and Tech On Hand's own facts (legal status, budget, geography, thematic pillars,
award-size appetite). This module is the single, versioned, editable source of
those facts. No org fact may ever be hardcoded in the scoring or prefilter code —
everything comes from this module's profile object.

## 2. Scope

### In scope
- Define and validate the org profile schema.
- Phase 1–3: profile lives as a single YAML file under version control.
- Phase 4: promote to a database-backed, team-editable record, with every edit
  versioned so any score can be traced back to the exact profile version that
  produced it.
- Provide a `profile_version` identifier and a loader API consumed by modules 07
  (prefilter) and 09 (scoring).

### Out of scope
- The scoring formula itself (module 09).
- The review app UI for editing the profile in Phase 4 (module 12 hosts the UI;
  this module defines the data contract it edits).

## 3. Dependencies

None — this is a foundational module. Everything else that touches TOH-specific
facts depends on it.

## 4. Roadmap Phase & Exit Criteria

Phase 1 deliverable: "org profile YAML" as part of Foundations and eval. Phase 1
exit criteria do not gate on this module directly, but scoring calibration
(module 09, Phase 1 exit criteria) cannot run without real profile values —
treat this as a Phase 1 blocking dependency in practice.

Phase 4 deliverable: promote YAML → DB-backed, versioned record, editable by the
grants team through the review app (module 12).

## 5. Inputs & Outputs

**Inputs**: values supplied by the TOH grants team (see Open Questions — several
are placeholders as of v3 of the design doc and must be confirmed before go-live).

**Outputs**:
- A validated profile object consumable in-process by modules 07 and 09.
- A `profile_version` string stamped onto every scored `GrantRecord`
  (`RelevanceBreakdown.profile_version` in module 08's schema) and onto every
  superfilter gate decision.

## 6. Data Model

### Phase 1–3: YAML file (`config/org_profile.yaml`)

```yaml
# org_profile.yaml — values confirmed by the grants team
legal_entities:
  - name: Tech On Hand Inc.
    jurisdiction: US
    status: 501(c)(3) public charity
    registered_since: <year>
  - name: Tech On Hand Kenya
    jurisdiction: KE
    status: <NGO / CBO / company limited by guarantee>
    registered_since: <year>

operating_since: <year>                    # earliest entity
audited_financials_available_years: <n>
annual_budget_usd: <amount>
operating_countries: [KE]
target_regions: [East Africa, Sub-Saharan Africa]

pillars:
  e_waste_refurbishing: {weight: 1.0}
  digital_education:    {weight: 1.0}
  off_grid_solar:       {weight: 0.8}
  connectivity:         {weight: 0.8}
  capacity_logistics:   {weight: 0.6}

award_range_usd: {ideal_min: 15000, ideal_max: 250000, hard_max: 2000000}
can_provide_matching_funds: false
certifications: []                         # e.g. R2, e-Stewards — used by superfilter
```

### Pydantic model (mirrors the YAML; validates on load)

```python
from pydantic import BaseModel, Field
from typing import List

class LegalEntity(BaseModel):
    name: str
    jurisdiction: str          # ISO 3166-1 alpha-2
    status: str
    registered_since: int

class PillarWeight(BaseModel):
    weight: float = Field(..., ge=0.0, le=1.0)

class AwardRange(BaseModel):
    ideal_min: float
    ideal_max: float
    hard_max: float

class OrgProfile(BaseModel):
    profile_version: str                     # semantic or content-hash version tag
    legal_entities: List[LegalEntity]
    operating_since: int
    audited_financials_available_years: int
    annual_budget_usd: float
    operating_countries: List[str]           # ISO 3166-1 alpha-2
    target_regions: List[str]
    pillars: dict[str, PillarWeight]
    award_range_usd: AwardRange
    can_provide_matching_funds: bool
    certifications: List[str] = []
```

### Phase 4: Postgres table `org_profile_versions`

```
org_profile_versions
  id                 uuid pk
  version            text unique          -- e.g. "2026-09-11T14:03Z" or v1, v2, ...
  profile_json        jsonb               -- full OrgProfile serialized
  edited_by           text
  edited_at           timestamptz
  change_summary      text                -- free-text diff note, shown in review app
  is_current          boolean             -- exactly one row true at a time
```

Editing creates a new row; nothing is ever mutated in place. `is_current` flips
atomically in a transaction.

## 7. Functional Requirements

1. **Loader**: `load_org_profile() -> OrgProfile` reads the current profile
   (YAML file in Phase 1–3, `is_current` row in Phase 4) and returns a validated
   object. Fail loudly (raise, do not silently default) if required fields are
   missing or out of range — a bad profile silently corrupts every score.
2. **Versioning**: every load returns a `profile_version`. Phase 1–3: derive from
   a content hash of the YAML file (e.g. `sha256` truncated to 12 chars) so any
   edit produces a new version automatically without manual bumping. Phase 4:
   the DB row's `version` column, assigned at write time.
3. **Immutability of history**: once a `profile_version` has been used to score
   any record, that version's content must never change. Phase 4 enforces this
   structurally (new row per edit); Phase 1–3 relies on the content-hash scheme
   naturally satisfying it (any edit changes the hash).
4. **Validation**: reject profiles where `award_range_usd.ideal_min > ideal_max`
   or `ideal_max > hard_max`, where any pillar weight is outside [0, 1], or where
   `legal_entities` is empty.
5. **Access pattern**: modules 07 and 09 must call the loader once per run (not
   per record) and pass the resulting object through, so all records in a single
   run are scored against one consistent profile snapshot even if an edit lands
   mid-run.

## 8. Algorithms / Business Logic

No scoring logic lives here — this module is pure data plus validation. The one
piece of logic worth calling out precisely:

```
profile_version (Phase 1-3) = sha256(canonicalized_yaml_bytes)[:12]
```

Canonicalize by parsing YAML → dict → re-serializing with sorted keys before
hashing, so incidental whitespace/comment changes in the file do not spuriously
bump the version, but any actual value change does.

## 9. Configuration

| Setting | Phase 1–3 | Phase 4 |
|---|---|---|
| Profile location | `config/org_profile.yaml`, version-controlled | Postgres `org_profile_versions` table |
| Who can edit | Direct file edit + PR review | Grants team via review app (module 12), admin-gated |
| Secrets | None — this file contains no credentials | Same |

## 10. Suggested Tech Stack & File Layout

```
app/
  org_profile/
    __init__.py
    schema.py        # OrgProfile, LegalEntity, PillarWeight, AwardRange (pydantic)
    loader.py         # load_org_profile(), version hashing
    store_yaml.py      # Phase 1-3 backend
    store_db.py         # Phase 4 backend (behind the same loader interface)
config/
  org_profile.yaml
```

Keep `loader.py`'s public interface (`load_org_profile() -> OrgProfile`) stable
across the Phase 1→4 backend swap so modules 07/09 never change.

## 11. Error Handling & Edge Cases

- Missing/malformed YAML at startup: fail fast with a clear error naming the
  missing field — do not fall back to defaults for org-identity facts.
  This module is on the critical path for every scoring run.
- Phase 4: concurrent edits — use a DB transaction to flip `is_current`
  atomically; last-write-wins with the `change_summary` field making the
  overwrite visible in an audit trail, rather than attempting merge logic.
- Pillar keys in the profile must match the module 09 scoring engine's expected
  pillar-key set exactly (they are matched against `GrantCategory` mappings) —
  validate this against a fixed allow-list of known pillar keys, not free text.

## 12. Testing & Acceptance Criteria

- Unit tests: valid profile loads cleanly; each validation rule (bad award
  range, out-of-bounds pillar weight, empty legal_entities) raises.
- Version stability test: reloading an unchanged file twice yields the same
  `profile_version`; changing any value changes it.
- Integration test (with module 09): scoring the same golden-set record against
  two different profile versions produces different `profile_version` stamps
  and, where profile changes affect gates/weights, different scores.
- Acceptance: a platform admin can hand-edit `org_profile.yaml`, and on the next
  scoring run every newly scored record carries the new `profile_version` with
  no code change required.

## 13. Open Questions

- Actual values for `registered_since` (both entities), `audited_financials_available_years`,
  and `annual_budget_usd` are placeholders in the design doc — must be confirmed
  by the grants team before Phase 1 scoring calibration can run meaningfully.
  This is the single highest-priority open item blocking realistic scoring.
- Whether the Kenyan entity should be treated as qualifying `INCORPORATED_AFRICA`
  eligibility for Kenya-only calls under its own name (affects module 09's
  eligibility vector) — a profile-level fact to capture explicitly once decided,
  e.g. `legal_entities[].applies_to_local_calls: bool`.
- `certifications: []` is currently empty — confirm whether TOH holds any
  (R2, e-Stewards, etc.) that should be populated for the superfilter gate in
  module 09 to use correctly.

## 14. Implementation Checklist

- [ ] Define `OrgProfile` Pydantic schema and sub-models.
- [ ] Write `config/org_profile.yaml` with real (not placeholder) values, confirmed by grants team.
- [ ] Implement YAML loader with content-hash versioning.
- [ ] Implement validation rules (§7.4) with clear error messages.
- [ ] Unit + integration tests per §12.
- [ ] Phase 4: design `org_profile_versions` table, migration, and swap loader backend behind the same interface.
- [ ] Phase 4: wire review-app edit flow (module 12) to write new versioned rows, never mutate.
