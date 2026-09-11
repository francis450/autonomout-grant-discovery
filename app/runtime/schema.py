"""Runtime & operations schema — module 16.

Full spec: docs/modules/16-runtime-ops.md §6.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

LLM_QUEUE_DEPTH_ALERT_THRESHOLD = 500
NO_RECORDS_ALERT_HOURS = 48

# Lower = higher priority. See §7.2.
LLM_JOB_PRIORITY = {
    "recheck_closing_soon": 0,
    "new_detail_page": 1,
    "prefilter_model_classify": 1,
    "dual_decode_check": 1,
    "discovery_qualification": 2,
}


class Run(BaseModel):
    id: str
    run_type: str  # 'crawl' | 'discovery' | 'lifecycle_recompute' | 'recalibration' | 'digest' | ...
    started_at: datetime
    finished_at: datetime | None = None
    pages_fetched: int = 0
    records_produced: int = 0
    llm_calls: int = 0
    failures: int = 0
    queue_depth_at_start: int = 0
    status: str = "running"  # 'success' | 'partial_failure' | 'failed' | 'running'


class LLMJob(BaseModel):
    id: str
    job_type: str
    priority: int
    payload: dict
    enqueued_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    status: str = "queued"  # 'queued' | 'running' | 'done' | 'failed'
