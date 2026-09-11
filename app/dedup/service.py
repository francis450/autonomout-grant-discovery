"""Deduplication service layer — module 11.

Full spec: docs/modules/11-deduplication.md

normalize_url / normalize_title are fully specified and deterministic —
implemented below for real, and imported by modules 02, 03, 05 rather than
reimplemented. Tier B/merge logic requires DB access (pg_trgm) — stubbed.
"""
from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlparse

from app.extraction.schema import GrantRecord

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "ref",
}
_SESSION_ID_PATTERN = re.compile(r"^(sid|session|sessionid|phpsessid)$", re.IGNORECASE)

STOP_WORDS = {"the", "a", "an", "for", "of", "and", "to", "in"}


def normalize_url(url: str) -> str:
    """Strip scheme, leading www, trailing slash, fragment, and tracking
    params. Tier A dedup key input. See §6, §8. Idempotent.
    """
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    netloc = netloc.removeprefix("www.")
    path = parsed.path.rstrip("/")
    query_params = [
        (k, v) for k, v in parse_qsl(parsed.query)
        if k not in TRACKING_PARAMS and not _SESSION_ID_PATTERN.match(k)
    ]
    query = urlencode(sorted(query_params))
    return f"{netloc}{path}" + (f"?{query}" if query else "")


def url_hash(url: str) -> str:
    """sha256(normalize_url(url)) — the Tier A dedup key. See §6."""
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()


def normalize_title(title: str) -> str:
    """Lowercase, strip punctuation, drop stop words, collapse whitespace.
    Tier B matching input. See §7.2, §8.
    """
    text = re.sub(r"[^\w\s]", "", title.lower())
    words = [w for w in text.split() if w not in STOP_WORDS]
    return " ".join(words)


def find_tier_a_match(url: str):
    """Lookup url_dedup_index by url_hash(url). See §7.1."""
    raise NotImplementedError("See docs/modules/11-deduplication.md §7.1")


def find_tier_b_match(record: GrantRecord):
    """Within records sharing the resolved (alias-normalized) funder name,
    find candidates with trigram similarity >= 0.85 on normalized title;
    closing_date within +-7 days is a confirming signal, not part of the
    key. See §7.2, §8. Guard against false merges on annual recurrence
    (large closing_date gap at high title similarity) per §11.
    """
    raise NotImplementedError("See docs/modules/11-deduplication.md §7.2, §8, §11")


def merge_records(canonical: GrantRecord, incoming: GrantRecord) -> GrantRecord:
    """Higher extraction_confidence wins as canonical; sources[] and
    attachments[] are unioned (dedup attachments by content_hash), never
    replaced. Logs to record_merges for audit / false-merge review.
    See §7.2.
    """
    raise NotImplementedError("See docs/modules/11-deduplication.md §7.2")


def resolve_funder_alias(funder_name: str) -> str:
    """Look up funder_aliases table; falls back to the raw name if no alias
    exists. Grown from review-time merges (module 12/13). See §7.4.
    """
    raise NotImplementedError("See docs/modules/11-deduplication.md §7.4")
