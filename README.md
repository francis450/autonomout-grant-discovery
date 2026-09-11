# Autonomous Grant Discovery Platform

Discovers open funding opportunities relevant to Tech On Hand (TOH), extracts
them into a structured record, scores them against TOH's organisational
profile, and delivers a reviewed shortlist to the grants team every week.

This is a new, separate codebase from `toh-grants-engine` — no shared code,
database, scoring, or ERPNext integration. See
[`docs/modules/README.md`](docs/modules/README.md) for the full architecture,
the 16-module breakdown, build order, and platform-wide open decisions.

Full design spec: `Grant_Discovery_Platform_Design_v3.docx`.

## Status

Skeleton stage. Directory structure, canonical data schemas, and stub service
interfaces are in place per module; business logic is not yet implemented.
Each `app/<module>/service.py` stub function's docstring points at the
relevant section of its module spec in `docs/modules/`.

## Project layout

```
app/
  org_profile/      # 01 — org_profile.yaml loader, versioning
  sources/            # 02 — Source Registry & health lifecycle
  discovery/            # 03 — Serper feeds, RSS, Class B prospecting
  crawl_policy/            # 04 — robots.txt, rate limits, bot identification
  ingestion/                  # 05 — Tier 0/1/2 fetch
  attachments/                   # 06 — PDF/DOCX download + parsing
  prefilter/                        # 07 — record-type + expiry filter
  extraction/                          # 08 — canonical GrantRecord schema, two-pass LLM extraction
  scoring/                                # 09 — gates, vectors, composite score
  lifecycle/                                # 10 — lifecycle recompute, re-checks
  dedup/                                       # 11 — Tier A/B/C deduplication
  review_app/                                    # 12 — Queue/Record/Sources views, API
  feedback_loop/                                    # 13 — few-shot bank, recalibration, precision feedback
  delivery/                                            # 14 — Monday digest, CSV export
  eval_harness/                                           # 15 — golden set + metrics
  runtime/                                                   # 16 — scheduler, LLM queue, storage, monitoring, backups
config/
  org_profile.yaml   # module 01 — placeholder values, needs grants-team confirmation
docs/
  modules/           # full per-module specs — read before implementing any module
tests/
  mirrors app/, one smoke-import test per module for now
```

## Getting started

```bash
python -m venv .venv
. .venv/Scripts/activate         # Windows
pip install -e ".[dev]"
cp .env.example .env             # fill in secrets — never commit .env
```

Postgres and Redis are required for anything beyond the schema layer (see
`docs/modules/16-runtime-ops.md`); they are not started automatically here.

## Implementing a module

1. Read `docs/modules/<NN>-<name>.md` in full — it's self-contained (purpose,
   scope, dependencies, data model, algorithms, config, acceptance criteria).
2. Fill in `app/<module>/service.py`'s stub functions; extend `schema.py`
   only if the module doc's data model changes.
3. Add tests under `tests/<module>/`.
4. Any model/prompt/weight/threshold change must be validated against the
   golden set via module 15 before being promoted (see that module's doc).
