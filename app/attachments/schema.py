"""Attachment parsing schema — module 06.

Full spec: docs/modules/06-attachment-parsing.md §6.

The Attachment model itself lives in app.extraction.schema (it's a field of
GrantRecord, owned canonically by module 08) — imported here, not redefined.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.extraction.schema import Attachment  # noqa: F401 — re-exported for convenience

MAX_ATTACHMENTS_PER_PAGE = 5
MAX_ATTACHMENT_SIZE_BYTES = 15 * 1024 * 1024
CONTEXT_BLOCK_TOKEN_CAP = 12_000
LINK_TEXT_PATTERNS = [r"\bcall\b", r"\bguidelines?\b", r"\bRFP\b", r"\beligibility\b", r"\bterms\b"]
PRIORITY_HEADINGS = [
    "eligibility", "who can apply", "applicant", "budget", "amount", "deadline", "closing date",
]


class AttachmentSnapshot(BaseModel):
    content_hash: str
    grant_record_id: str
    url: str
    filename: str
    file_size_bytes: int
    mime_type: str
    parse_method: str  # 'pdfplumber' | 'pymupdf' | 'tesseract_ocr' | 'python-docx'
    parsed_ok: bool
    text_chars: int
    extracted_text: str | None = None
    downloaded_at: datetime
