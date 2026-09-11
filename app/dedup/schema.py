"""Deduplication schema — module 11.

Full spec: docs/modules/11-deduplication.md §6.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class UrlDedupEntry(BaseModel):
    normalized_url_hash: str
    grant_record_id: str
    first_seen_at: datetime
    last_seen_at: datetime


class FunderAlias(BaseModel):
    alias: str
    canonical_name: str
    added_by: str  # 'seed' | reviewer username
    added_at: datetime


class RecordMerge(BaseModel):
    id: str
    canonical_record_id: str
    merged_record_id: str
    merge_tier: str  # 'A' | 'B'
    matched_on: dict
    merged_at: datetime
    date_confirms: bool | None = None
