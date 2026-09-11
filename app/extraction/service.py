"""Extraction engine service layer — module 08.

Full spec: docs/modules/08-extraction-engine.md

Implements: model selection (bake-off), constrained-decoding two-pass
extraction (factual -> relevance), retry-on-validation-failure, and computed
extraction_confidence. Not implemented yet — stubs only.
"""
from __future__ import annotations

import hashlib

from app.extraction.schema import GrantRecord
from app.org_profile.schema import OrgProfile


def content_hash(page_markdown: str, attachment_text: str = "") -> str:
    """sha256(page_markdown + attachment_text). See §8.

    Fully specified — safe to use as-is; also consumed by module 11 (Tier C
    dedup) and module 10 (change detection).
    """
    return hashlib.sha256((page_markdown + attachment_text).encode("utf-8")).hexdigest()


def extract_pass1(page_markdown: str, attachment_context: str, few_shot_examples: list) -> GrantRecord:
    """Pass 1: factual fields only (title, funder, dates, amounts,
    eligibility text, regions, attachments, application_method,
    superfilter_blockers). See §7.2.

    Must use constrained decoding (Ollama JSON-schema `format` param, schema
    generated from GrantRecord/pass-1 subset) with one retry on validation
    failure; extraction_status = OK | RETRIED_OK | FAILED.
    """
    raise NotImplementedError("See docs/modules/08-extraction-engine.md §7.2, §8")


def extract_pass2(pass1_record: GrantRecord, profile: OrgProfile, few_shot_examples: list):
    """Pass 2: qualitative relevance analysis only (matching_pillars,
    dealbreaker_claims with verbatim citations, summary_justification).

    Does NOT compute numeric scores — module 09 (Scoring Engine) owns the
    deterministic composite/vector math. See §7.2.
    """
    raise NotImplementedError("See docs/modules/08-extraction-engine.md §7.2")


def compute_extraction_confidence(
    record: GrantRecord,
    rule_layer_findings: dict,
    dual_decode_result: object | None = None,
) -> float:
    """1.0 minus penalties for: null fields the rule layer found, dual-decode
    disagreement on key fields (review-band records only), implausible
    dates. Never self-reported by the model. See §7.2, §8.
    """
    raise NotImplementedError("See docs/modules/08-extraction-engine.md §7.2, §8")


def run_model_bakeoff(candidate_models: list, golden_set) -> dict:
    """Phase 1: compare candidate models (Qwen 7B/14B, Mistral 7B v0.3, +1)
    on weighted field accuracy (closing_date, geographic_scopes,
    eligible_applicants, amount) subject to >= 8 records/min throughput
    floor. Delegates metric computation to module 15. See §7.1.
    """
    raise NotImplementedError("See docs/modules/08-extraction-engine.md §7.1")
