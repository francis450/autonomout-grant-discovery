"""Attachment parsing service layer — module 06.

Full spec: docs/modules/06-attachment-parsing.md

Implements: link identification, download (through module 04's can_fetch),
pdfplumber -> pymupdf -> Tesseract OCR fallback chain, DOCX extraction, and
labelled/capped context-block assembly. Not implemented yet — stubs only.
"""
from __future__ import annotations

from app.attachments.schema import AttachmentSnapshot


def find_attachment_links(page_html_or_markdown: str) -> list[dict]:
    """Match LINK_TEXT_PATTERNS against linked .pdf/.docx files, rank by
    pattern specificity, cap at MAX_ATTACHMENTS_PER_PAGE. See §7.1, §7.2, §8.
    """
    raise NotImplementedError("See docs/modules/06-attachment-parsing.md §7.1, §7.2, §8")


def download_attachment(url: str) -> bytes:
    """Fetch via app.crawl_policy.service.can_fetch() gate, capped at
    MAX_ATTACHMENT_SIZE_BYTES. See §7.3.
    """
    raise NotImplementedError("See docs/modules/06-attachment-parsing.md §7.3")


def extract_text(file_bytes: bytes, mime_type: str) -> AttachmentSnapshot:
    """PDF: pdfplumber -> pymupdf -> Tesseract OCR (only when the text layer
    is empty after both). DOCX: python-docx. content_hash = sha256(raw
    bytes), used for both dedup and snapshot key. parsed_ok=False on total
    failure, never raises. See §7.4, §7.5, §8.
    """
    raise NotImplementedError("See docs/modules/06-attachment-parsing.md §7.4, §7.5, §8")


def assemble_context_block(snapshots: list[AttachmentSnapshot]) -> str:
    """Labelled '[ATTACHMENT: filename]' blocks, capped at
    CONTEXT_BLOCK_TOKEN_CAP tokens. When over cap, prioritize sections by
    PRIORITY_HEADINGS (eligibility/budget/deadline/applicant) via heading
    heuristics rather than naive truncation. See §7.6, §8.
    """
    raise NotImplementedError("See docs/modules/06-attachment-parsing.md §7.6, §8")
