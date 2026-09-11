# Module 06: Attachment Parsing

## 1. Purpose

Most eligibility detail for a grant opportunity lives in attached PDFs (call
documents, guidelines, RFPs), not the HTML page itself. This module downloads,
parses, and text-extracts those attachments so their content can feed the
extraction engine (module 08) as first-class context, not an afterthought.
The design doc is explicit that this is a **core Phase 3 deliverable, not a
fallback**.

## 2. Scope

### In scope
- Identifying which linked files on a detail page are worth downloading
  (link-text pattern matching).
- Downloading with size/count caps.
- Text extraction (pdfplumber primary, pymupdf fallback, Tesseract OCR for
  scanned PDFs with no text layer).
- Producing the `Attachment` record and the labelled, capped context block
  appended to extraction prompts.
- Storing attachment text as its own content-addressed snapshot.

### Out of scope
- Deciding *whether* a page is an opportunity worth attaching to in the first
  place — module 07.
- The extraction logic that consumes the attachment context block — module
  08.
- Long-term object storage mechanics (bucket/filesystem layout, retention) —
  module 16 owns the object store; this module writes into it via a storage
  interface.

## 3. Dependencies

- Module 05 (Tiered Ingestion): supplies the detail page from which
  attachment links are extracted.
- Module 04 (Crawl Policy): attachment downloads are still HTTP fetches and
  must go through the same `can_fetch()` gate and rate limits as page fetches.
- Module 08 (Extraction Engine): consumes the assembled attachment context
  block as part of its prompt; owns the `Attachment` sub-model within
  `GrantRecord`.
- Module 16 (Runtime & Operations): object store for raw attachment bytes and
  extracted text snapshots.

## 4. Roadmap Phase & Exit Criteria

Phase 3 deliverable: "attachment parsing" alongside two-pass extraction and
scoring. Phase 3 exit criterion ("RECOMMENDED precision ≥ 60% on golden set")
implicitly depends on attachment content being available, since eligibility
detail often only exists there — a golden set with ≥ 30 PDF-attachment records
(module 15) is specifically built to validate this module.

## 5. Inputs & Outputs

**Inputs**: a detail page's markdown/HTML (from module 05) containing links to
files.

**Outputs**: zero or more `Attachment` objects (metadata + parsed text),
stored as content-addressed snapshots, plus a single assembled, labelled,
token-capped text block ready for injection into module 08's extraction
prompt.

## 6. Data Model

### `Attachment` (as defined in module 08's `GrantRecord` schema — reproduced here for this module's reference)

```python
class Attachment(BaseModel):
    url: HttpUrl
    filename: str
    content_hash: str
    text_chars: int
    parsed_ok: bool
```

### Postgres table `attachment_snapshots`

```
attachment_snapshots
  content_hash      text pk            -- sha256 of raw file bytes
  grant_record_id    uuid fk -> grant_records.id
  url                 text
  filename             text
  file_size_bytes       int
  mime_type              text
  parse_method            text          -- 'pdfplumber' | 'pymupdf' | 'tesseract_ocr'
  parsed_ok                boolean
  text_chars                int
  extracted_text              text      -- full extracted text (also mirrored to object store)
  downloaded_at                timestamptz
```

## 7. Functional Requirements

1. **Link identification**: on a detail page, find every linked file whose
   link text matches patterns for `call`, `guidelines`, `RFP`, `eligibility`,
   or `terms` (case-insensitive, word-boundary matching, extendable pattern
   list).
2. **Download caps**: at most **5 attachments** per detail page, each capped
   at **15 MB**. If more than 5 matching links exist, prioritize by pattern
   specificity (e.g. an exact match on "eligibility" outranks a generic "PDF"
   link) — document the tie-break order explicitly in code, don't leave it to
   iteration order.
3. **Download**: fetch via module 04's `can_fetch()` gate, same rate limits as
   page fetches (attachments count toward the same per-domain daily cap).
4. **Text extraction**:
   - Primary: `pdfplumber` (layout-aware) for PDFs.
   - Fallback: `pymupdf` if pdfplumber fails or produces near-empty output.
   - OCR: run Tesseract **only** when the text layer is empty after both
     pdfplumber and pymupdf (i.e. the PDF is scanned/image-based) — OCR is
     expensive, use it as a last resort, not a default.
   - DOCX: use an appropriate DOCX text extractor (e.g. `python-docx`);
     pdfplumber/pymupdf/Tesseract apply to PDF only.
5. **Content hashing**: `content_hash = sha256(raw_file_bytes)` — used both for
   dedup (identical attachment linked from multiple pages is only parsed
   once) and as the snapshot key.
6. **Context assembly**: concatenate attachment texts into a single labelled
   block per detail page:
   ```
   [ATTACHMENT: guidelines.pdf]
   <extracted text>

   [ATTACHMENT: eligibility_criteria.pdf]
   <extracted text>
   ```
   capped at **12,000 tokens** total. When the combined text exceeds the cap,
   locate and prioritize the **eligibility, budget, deadline, and applicant**
   sections using heading heuristics (regex/keyword matching on headings like
   "Eligibility", "Budget", "Deadline", "Who Can Apply") rather than naively
   truncating from the start of the document.
7. **`parsed_ok` flag**: set `false` if extraction produced no usable text
   after all fallbacks (e.g. OCR also failed or file was corrupt) — the
   attachment is still recorded (for audit) but contributes nothing to the
   context block.

## 8. Algorithms / Business Logic

### Link pattern matching

```
ATTACHMENT_LINK_PATTERNS = [
    r"\bcall\b", r"\bguidelines?\b", r"\bRFP\b", r"\beligibility\b", r"\bterms\b"
]
candidates = [link for link in page_links
              if link.file_ext in ('.pdf', '.docx')
              and any(re.search(p, link.text, re.I) for p in ATTACHMENT_LINK_PATTERNS)]
candidates = rank_by_specificity(candidates)[:5]
```

### Extraction fallback chain

```python
def extract_text(file_bytes: bytes, mime_type: str) -> tuple[str, str, bool]:
    if mime_type == "application/pdf":
        text = try_pdfplumber(file_bytes)
        method = "pdfplumber"
        if not text.strip():
            text = try_pymupdf(file_bytes)
            method = "pymupdf"
        if not text.strip():
            text = try_tesseract_ocr(file_bytes)
            method = "tesseract_ocr"
        return text, method, bool(text.strip())
    elif mime_type in DOCX_MIME_TYPES:
        text = try_docx_extract(file_bytes)
        return text, "python-docx", bool(text.strip())
    return "", "unsupported", False
```

### Heading-heuristic prioritization when over the 12k token cap

```python
PRIORITY_HEADINGS = ["eligibility", "who can apply", "applicant", "budget", "amount", "deadline", "closing date"]

def prioritize_sections(full_text: str, token_cap: int) -> str:
    sections = split_by_headings(full_text)
    prioritized = sorted(sections, key=lambda s: heading_priority(s.heading, PRIORITY_HEADINGS))
    return truncate_to_token_cap(prioritized, token_cap)
```

## 9. Configuration

| Setting | Value |
|---|---|
| Max attachments per page | 5 |
| Max size per attachment | 15 MB |
| Context block token cap | 12,000 tokens |
| Link pattern list | call, guidelines, RFP, eligibility, terms (extendable) |
| OCR engine | Tesseract, used only when text layer is empty |

## 10. Suggested Tech Stack & File Layout

```
app/
  attachments/
    __init__.py
    link_finder.py          # pattern matching + ranking on detail-page links
    downloader.py              # module-04-gated download with size/count caps
    extract_pdf.py                # pdfplumber -> pymupdf -> tesseract fallback chain
    extract_docx.py                  # python-docx extraction
    context_assembly.py                # labelled block building + heading-priority truncation
    schema.py                            # Attachment, attachment_snapshots row
```

Python libraries: `pdfplumber`, `pymupdf` (fitz), `pytesseract` (+ system
Tesseract binary), `python-docx`.

## 11. Error Handling & Edge Cases

- Corrupt or password-protected PDFs: all three extraction methods fail
  gracefully, `parsed_ok = false`, do not crash the detail-page pipeline.
- Attachment URL 404s/times out: record the attempt with `parsed_ok = false`
  and no text; do not block extraction of the rest of the page's attachments.
- Duplicate attachment across multiple detail pages (same `content_hash`):
  reuse the existing parsed text rather than re-downloading/re-parsing;
  still create a per-record `Attachment` reference.
- Extremely large scanned PDFs (OCR is slow): apply a reasonable per-file OCR
  timeout; on timeout, mark `parsed_ok = false` rather than blocking the
  pipeline indefinitely.
- Non-English attachments: out of scope for OCR/extraction language handling
  in v3 — extract text as-is; downstream extraction (module 08) model
  behavior on non-English text is a model-selection concern, not this
  module's.

## 12. Testing & Acceptance Criteria

- Unit tests: link pattern matching correctly identifies/excludes sample
  link texts; extraction fallback chain correctly escalates pdfplumber →
  pymupdf → Tesseract on synthetic empty-text-layer PDFs.
- Integration test: real-world sample PDFs (text-based and scanned) from the
  golden set (module 15, ≥ 30 PDF-attachment records) parse successfully with
  expected `parsed_ok` outcomes.
- Context assembly test: a set of attachments whose combined text exceeds
  12k tokens is correctly truncated with eligibility/budget/deadline/applicant
  sections retained over less relevant sections.
- Acceptance (Phase 3): for the golden set's ≥ 30 PDF-attachment records,
  attachment text materially improves field-level extraction accuracy
  (measured via module 15's harness) versus extraction without attachment
  context.

## 13. Open Questions

None specific to this module beyond the platform-wide open decisions in the
README — attachment parsing behavior is fully specified by the design doc.

## 14. Implementation Checklist

- [ ] Implement link-text pattern matching and ranking (max 5, 15MB cap).
- [ ] Implement download path through module 04's `can_fetch()`.
- [ ] Implement pdfplumber → pymupdf → Tesseract OCR fallback chain.
- [ ] Implement DOCX extraction.
- [ ] Implement content hashing and snapshot storage (dedup identical attachments).
- [ ] Implement labelled context block assembly with 12k-token cap and heading-priority truncation.
- [ ] Tests per §12, including real golden-set PDF samples.
