"""Runtime & operations service layer — module 16.

Full spec: docs/modules/16-runtime-ops.md

Implements: scheduler cadence registration, LLM job queue (single worker per
Ollama instance, priority ordering), object store interface, alert
evaluation, and backups. This is the infrastructure layer most other
modules depend on. Not implemented yet — stubs only; needs Postgres/Redis
(see .env.example) before anything here can run for real.
"""
from __future__ import annotations

from app.runtime.schema import LLMJob


def register_scheduled_jobs() -> None:
    """Registers every module's cadence (see the table in module 16 §7.1):
    listing crawls (05), re-checks (10), discovery (03), Class B
    prospecting (03), lifecycle recompute (10), source health (02), robots
    re-check (04), few-shot rotation (13), weight recalibration (13),
    Monday digest (14), backups (16). Stagger same-time jobs to avoid DB
    write contention. See §7.1, §11.
    """
    raise NotImplementedError("See docs/modules/16-runtime-ops.md §7.1")


def enqueue_llm_job(job_type: str, payload: dict) -> LLMJob:
    """Pushes onto the priority queue using LLM_JOB_PRIORITY. See §7.2, §8."""
    raise NotImplementedError("See docs/modules/16-runtime-ops.md §7.2, §8")


def run_llm_worker(ollama_instance: str) -> None:
    """Exactly one worker per Ollama instance — hard constraint, not
    tunable up, since the GPU host can't usefully serve concurrent
    requests. Crawling must never block on this. See §7.2, §8, §11.
    """
    raise NotImplementedError("See docs/modules/16-runtime-ops.md §7.2, §8")


def object_store_put(content_hash: str, content: bytes) -> str:
    """MinIO or local filesystem, keyed by content hash — decide backend
    per OBJECT_STORE_BACKEND. See §7.3.
    """
    raise NotImplementedError("See docs/modules/16-runtime-ops.md §7.3")


def object_store_get(content_hash: str) -> bytes:
    raise NotImplementedError("See docs/modules/16-runtime-ops.md §7.3")


def evaluate_alerts() -> list[str]:
    """Fires on: any run failed; LLM queue depth > LLM_QUEUE_DEPTH_ALERT_THRESHOLD;
    no records produced in NO_RECORDS_ALERT_HOURS; Ollama host unreachable.
    A silent outage was a real failure mode in the predecessor system — this
    must never fail silently itself. See §7.5, §8.
    """
    raise NotImplementedError("See docs/modules/16-runtime-ops.md §7.5, §8")


def run_nightly_backup() -> None:
    """pg_dump + snapshot-directory rsync to a second location. Restore
    must be tested once before go-live — a required, blocking step. See
    §7.6.
    """
    raise NotImplementedError("See docs/modules/16-runtime-ops.md §7.6")
