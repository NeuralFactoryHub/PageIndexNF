# Code Review — preprocessing

**Branch:** `feature/preprocessing` (base `feature/customizations`)
**Reviewer:** Gandalf
**Date:** 2026-08-19

---

## Verdict: APPROVED

*(Updated after fix verification — commits `96f5c6f`, `96b6b37`, `cfb4a8d`.)*

---

## Fix Verification (re-review 2026-08-19)

### Critical §1 — `doc_name` second return site (`page_index.py:1298`)

Both return sites inside `page_index_builder` now read `doc_name or get_pdf_name(doc)`. The only
remaining bare `get_pdf_name(doc)` is line 1267, inside the `NotPreprocessedError` branch where
`doc is not None` — correct as-is. Fix confirmed complete, no new issue introduced.

### Critical §2 — `PdfDocument` handle on `OCRError` path (`preprocess.py`)

The block from `_classify()` through the `return Normalized(...)` is now wrapped in
`try/finally: doc.close()`. Behavioral analysis: in Python a `return` inside `try` saves the
return value, runs `finally`, then returns — so `doc.close()` now runs on both the normal return
path (semantically identical to the previous explicit call) and on the `OCRError` raise path
(previously leaked). No behavioral change beyond handle release. Fix confirmed correct.

### Minor §3 — `_CREDENTIAL_PATTERNS` STS coverage (`utils.py`)

Three phrases added: `security token`, `ExpiredToken`, `UnrecognizedClientException`. All three
map to permanent AWS auth failures; none appears in any transient Bedrock error message
(throttling uses `ThrottlingException`/`TooManyRequestsException`, not these phrases). The
existing `access denied` pattern was also reviewed: IAM `AccessDeniedException` is permanent,
and no plausible transient Bedrock response includes that phrase. The patterns are sound for the
consumer's Bedrock-via-STS use case.

### Remaining minor observations — accepted as-is

- **Unclosed page handles in `_ocr_pages`** (PyPy-only): Lambda runs CPython, reference counting
  releases immediately. Not a defect in the current runtime. Accepted.
- **`asyncio.run()` from async context**: now documented in `preprocess()`'s docstring. The
  consumer's Lambda handler is synchronous. Accepted.

---

---

## Plan Compliance

- [x] Task 1: `errors.py` — typed hierarchy, all ten classes present and exported
- [x] Task 2: configurable `log_dir`, Lambda crash fixed, `get_pdf_name` made total
- [x] Task 3: exponential backoff + `LLMUnavailableError`/`LLMConfigError` on exhaustion
- [x] Task 4: `TreeParseError` with exhausted strategy names in `meta_processor`
- [x] Task 5: `preprocess.py` skeleton, binary resolution, first-use checks
- [x] Task 6: Office→PDF via LibreOffice headless, profile isolation, dual exit-code check
- [x] Task 7: per-page classifier, two-signal (char count + image area), text gate
- [x] Task 8: async OCR, psm 1, rendering on event-loop thread, semaphore-bounded memory
- [x] Task 9: `preprocess()` public function, `Normalized`, `PreprocessReport`, ordinal alignment
- [x] Task 10: `build_tree(pages=...)` path, mutual-exclusivity guard, `NotPreprocessedError` detection
- [x] Task 10 (second return site): fixed in commit `96f5c6f` — confirmed
- [x] Task 11: `__init__.py` exports, `pyproject.toml` dependencies
- [x] Task 12: README consumer section, `FORK_NOTES.md` divergences
- [x] Fix (post-batch-3): `_is_unrecoverable` message-level check + `_MAX_TOTAL_RETRY_SECONDS` budget
- [x] Fix (follow-up): sleep clamped to remaining budget in both sync and async loops
- [x] Task 13: `ContextVar`-based `llm_metadata` pass-through

---

## Requirements Compliance

- [x] AC: Office→PDF conversion via LibreOffice headless — implemented
- [x] AC: Per-page scanned-page detection — two-signal classifier implemented, PRML false-positive gate working
- [x] AC: OCR only on image pages — ordinal-based, empty string held at failed positions
- [x] AC: `pages` list never compacted — confirmed, source ordinals preserved
- [x] AC: `failed_pages` carries source ordinals — confirmed
- [x] AC: `OCRError` raised only when every scanned page fails — confirmed
- [x] AC: typed error taxonomy, `LLMUnavailableError` is the only retryable signal — implemented
- [x] AC: LLM retry loop raises instead of returning `""` — implemented
- [x] AC: `NotPreprocessedError` on all-empty text layer in `source=` path — implemented
- [x] AC: mutual-exclusivity guard in `build_tree` — XNOR guard correct
- [x] AC: `doc_name` propagated from `preprocess()` through `build_tree` — PARTIAL (see Critical §1)
- [x] AC: `log_dir` configurable, Lambda crash removed — implemented
- [x] AC: `llm_metadata` ContextVar pass-through — implemented, OpenAI SDK branches correctly excluded
- [x] AC: resource handles released on all paths — fixed in commit `96b6b37`, try/finally confirmed

---

## Issues

### Critical

**§1 — Second `doc_name` return site not updated (`page_index.py:1298`)**

File: `pageindex/page_index.py`, line 1298.

The engineer's journal states: "Both `doc_name` return sites changed from `get_pdf_name(doc)` to
`doc_name or get_pdf_name(doc)`." The diff shows only one site was changed. The `page_index_builder`
async inner function contains two early-return paths:

- **Return site 1** (line 1292, inside `if opt.if_add_doc_description == 'yes'`): **fixed** →
  `'doc_name': doc_name or get_pdf_name(doc)`
- **Return site 2** (line 1298, the path taken when `if_add_doc_description == 'no'`): **not fixed**
  → `'doc_name': get_pdf_name(doc)`

`if_add_doc_description` defaults to `"no"` in `DEFAULT_CONFIG`. This means the second site is the
default path for every document that does not explicitly enable doc_description. When called via
`build_tree(pages=norm.pages, doc_name=norm.doc_name)`, `doc=None`, so `get_pdf_name(None)` returns
`'Untitled'`. Every tree produced via the `pages=` path with default config has
`doc_name='Untitled'`.

This is a silent data corruption: the consumer's retrieval catalog receives `'Untitled'` for every
document. It would only manifest at catalog query time, not at build time, which makes it hard to
notice without an end-to-end run.

**Fix:** change line 1298 to:
```python
'doc_name': doc_name or get_pdf_name(doc),
```

Manual verification: run `build_tree(pages=["sample text"], doc_name="My Doc.pdf")` with default
config; confirm the returned dict carries `doc_name='My Doc.pdf'`.

---

**§2 — `PdfDocument` handle leaks on `OCRError` path (`preprocess.py:294–299`)**

File: `pageindex/preprocess.py`, lines 281–324.

`_classify()` returns an open `PdfDocument` at line 282. `_ocr_pages()` renders from it at line
199. `doc.close()` is at line 324 — after the `raise OCRError(...)` at lines 294–299. On the "all
OCR pages fail" path, the exception unwinds the stack and `doc.close()` is never reached. The
native pdfium handle leaks for the lifetime of the Lambda invocation.

Lambda reuses the runtime process across invocations ("warm start"). A document with many scanned
pages that all fail OCR would accumulate open handles across invocations.

**Fix:** wrap the classify-through-return block in a `try/finally`:

```python
doc, classified = _classify(data)
try:
    # ... ocr_ordinals, asyncio.run(...), pages loop, report ...
    return Normalized(pages=pages, doc_name=name, report=report)
finally:
    doc.close()
```

Remove the `doc.close()` that currently appears at line 324 (it will be superseded by the finally).

---

### Major

None beyond the two critical issues above.

---

### Minor

**§3 — `_CREDENTIAL_PATTERNS` does not cover AWS STS token errors**

File: `pageindex/utils.py`, `_CREDENTIAL_PATTERNS` regex.

The phrase "The security token included in the request is invalid" (returned by AWS STS for expired
temporary credentials) is not matched by any pattern. An expired assume-role token would be treated
as retryable and burn the full 60-second budget. Low practical risk for Lambda with its own IAM
role (credentials auto-rotated by the runtime), but becomes relevant if the consumer test-drives
the library with short-lived assume-role tokens locally. Adding `"security token"` to the pattern
covers the case at no cost.

---

**§4 — Page handles from `doc[ordinal - 1]` not explicitly closed in `_ocr_pages`**

File: `pageindex/preprocess.py`, line 199.

```python
image = doc[ordinal - 1].render(scale=dpi / 72).to_pil()
```

The `PdfPage` returned by `doc[ordinal - 1]` is used inline and not assigned to a variable, so no
`.close()` is called. CPython's reference counting drops the native buffer immediately. PyPy would
leak. Lambda runs CPython, so this is not a practical defect today, but it would silently break if
the runtime ever changed.

Minimal fix: `page = doc[ordinal - 1]; image = page.render(...).to_pil(); page.close()`.

---

**§5 — `asyncio.run()` in `preprocess()` fails inside an existing event loop**

File: `pageindex/preprocess.py`, line 290.

`preprocess()` is synchronous and calls `asyncio.run(_ocr_pages(...))`. If the consumer's Lambda
handler is async (e.g., FastAPI via Mangum with an async route), `asyncio.run()` raises
`RuntimeError: This event loop is already running`. This matches `page_index_main`'s same pattern,
so it is not a regression, but it is worth documenting in the README alongside the "call
`preprocess()` before `build_tree()`" guidance.

Not a blocker: the consumer's handler is synchronous (confirmed from the brief's Lambda
architecture), but the library makes this assumption silently.

---

## Page-Number Alignment Audit

Design contract: `pages[i]` corresponds to source ordinal `i + 1`; positions are never compacted;
a failed OCR page holds `""` and its ordinal is in `report.failed_pages`.

Trace through `preprocess()`:

1. `_classify()` calls `enumerate(doc, start=1)` → ordinals 1, 2, …, N. Appends `(ordinal, text,
   needs_ocr)` in document order. The doc is iterated once, in order — no gaps, no re-ordering.
2. `ocr_text = {ordinal: text}` is a dict keyed by ordinal. Lookups are by ordinal, not by list
   position.
3. The final loop over `classified` (already in ordinal order) appends to `pages` in order. For
   each entry: if OCR succeeded → `ocr_text[ordinal]`; if OCR failed → `""`; if not a scan →
   original text. No compaction.

Result: `pages[ordinal - 1]` is always the correct page, regardless of which pages needed OCR or
which failed. The contract holds.

The `pages=` path in `page_index_main` (line 1249):
```python
page_list = [(text, litellm.token_counter(model=opt.model, text=text)) for text in pages]
```
Preserves the list in order. `token_counter("")` returns 0, which is valid — the tree builder
treats a zero-token page as empty content. Ordinal alignment is maintained end-to-end.

---

## Retry Loop Audit

`_is_unrecoverable` two-layer design:

- **Layer 1 (status code):** `{401, 403, 404}` are permanently unrecoverable. Note: `400` is
  excluded because `context_length_exceeded` arrives as 400 and is treated as an absorbed per-prompt
  failure (not retried). This is correct.
- **Layer 2 (message regex):** catches litellm's known misclassification of credential errors as
  500. The pattern covers `missing credentials`, `api_key`, `could not locate credentials`, `access
  denied`, `unrecognized client`, `invalid api key`, `no credentials`. The gap noted in §3 (STS
  security token) is the one identified omission.

Budget guard: `_MAX_TOTAL_RETRY_SECONDS = 60`. Sleep is clamped to `min(_backoff_seconds(i),
remaining)`. On the last iteration (`i == max_retries - 1`), the budget path is not checked —
`raise LLMUnavailableError(f"LLM unavailable after {max_retries} attempts...")` fires directly.
This is correct: the final iteration cannot sleep, so remaining budget is irrelevant.

The sync and async loops are symmetric — both implement the same clamp logic. No discrepancy
found.

---

## `build_tree` / `page_index_main` Seam Audit

`build_tree.py` guard: `(source is None) == (pages is None)` raises `ValueError` when both are
supplied or neither is supplied. This is XNOR — True when both match (both None or both not-None),
which is the error condition. Correct.

When `pages is not None`: `page_index_main(None, opt, pages=pages, doc_name=doc_name)`. `doc=None`
is passed. The `pages is not None` branch in `page_index_main` never dereferences `doc`.

Legacy `page_index()` entrypoint: calls `page_index_main(doc, opt)` — `pages` and `doc_name`
default to `None`. Both paths in `page_index_builder` use `get_pdf_name(doc)` (the unfixed second
site is still consistent for the `doc` path since `doc` is not `None` there). No regression to
the upstream entrypoint.

`client.py`: not modified in this diff. It calls `build_tree` or `page_index_main` via the
existing interface — unaffected.

---

## Upstream Footprint Audit

Files modified that are not fork-owned:

| File | Edits | Avoidable? |
|---|---|---|
| `pageindex/utils.py` | LLM retry, `set_llm_metadata`, `ContextVar`, `log_dir` in `JsonLogger` | No — these are in the call sites that must change |
| `pageindex/page_index.py` | `page_index_main` signature, `TreeParseError`, `NotPreprocessedError` | No — no fork-owned indirection layer can avoid touching the call site |
| `pageindex/config.py` | `log_dir: None`, `llm_metadata: None` | No — config validation reads from `DEFAULT_CONFIG` |
| `pageindex/build_tree.py` | New `pages=` parameter | No — this IS the public seam |

The `from .utils import *` in `page_index.py` ensures that `set_llm_metadata` from `utils.py` is
available in `page_index_main`'s scope without an additional import. This is correct.

Every edit to upstream files is the minimum required by the design. The fork-owned modules
(`preprocess.py`, `errors.py`) contain all new logic.

---

## Known Gap (pre-existing, not a new finding)

No end-to-end tree build has run with real credentials. `build_tree(pages=...)` was verified up
to the point of `LLMUnavailableError` (correct typed error on missing credentials). The
`doc_name` bug in Critical §1 would be caught by this run.

Manual verification recommended before merge:
1. Patch the second return site (Critical §1).
2. Call `build_tree(pages=norm.pages, doc_name="Test.pdf")` with real credentials on a 1-page
   scanned document. Confirm `result['doc_name'] == 'Test.pdf'` in both config variants
   (`if_add_doc_description: 'yes'` and `'no'`).

---

## Summary

The feature is architecturally sound and the implementation is thorough. All 13 planned tasks plus
two post-implementation fixes are complete. Page-number alignment, the retry loop, the mutual-
exclusivity guard, and the upstream footprint are all correct. Two targeted fixes are required: the
second `doc_name` return site (which silently corrupts the output for every document on the default
config path) and the `try/finally` around `doc.close()` (which leaks a pdfium handle on the all-
OCR-fail path). Neither requires re-planning — both are single-line or small-block changes.

---

## Likely CTO Questions

These are questions Juan should be prepared to answer at PR review. Suggested talking points follow
each one.

**Q1: "Why two calls — `preprocess()` then `build_tree(pages=...)` — instead of handling
everything inside `build_tree`?"**

The consumer extracts page text a second time, independently of the tree, to serve `get_page_content`.
If OCR were hidden inside `build_tree`, the tree would be correct but the backend's page-content
store would still serve blank pages for scanned documents — half the problem fixed. Separating the
calls also makes the omission loud: forgetting `preprocess()` raises `NotPreprocessedError` instead
of producing an empty-but-valid tree. The two behaviours (silent internal OCR vs. loud omission
detection) are mutually contradictory; they cannot coexist in one function.

**Q2: "Why `--psm 1` and not `--psm 6` as the brief specified?"**

Two measurements on the real client corpus. `psm 6` (uniform block) interleaves the columns of
bilingual pages in `DUVRI DL01_Toffetti.pdf` line by line, producing mixed-language soup that
poisons node summaries — and it also mangles the heading "DUVRI DL01" → "x. -» DUVRI DLO1",
which is precisely what the tree is built from. `psm 3` fails on `Lube Duvri.pdf` pages 4–7,
which are scanned at 270° rotation baked into the image (PDF metadata reports 0°). `psm 1`
recovers the correct heading on those pages at a measured cost of 2.45 extra seconds across the
worst document in the corpus, against the consumer's 890-second Lambda timeout.

**Q3: "Why does rendering stay on the event-loop thread and only Tesseract go to a thread?"**

pdfium is a C library that is not thread-safe. Touching a `PdfDocument` from any thread other than
the one that opened it causes an immediate segfault — no exception, no traceback, a dead Lambda
invocation. This was found by measurement on the first draft, which rendered inside the worker and
crashed the process. The cost of keeping rendering on the event loop is negligible: 0.042 s per
page vs. ~0.4 s for Tesseract. The expensive half is still the parallel one.

**Q4: "What does `LLMUnavailableError` mean and why is it the only retryable error?"**

It means the model call failed due to throttling or a transient transport failure — something that
a wait-and-retry can fix. Every other error class means either the input is broken
(`UnreadableInputError` and its subclasses), the credentials or model config are wrong
(`LLMConfigError`), or the model answered but produced unstructured output (`TreeParseError`). None
of those improve with retrying. The consumer's differentiated retry policy — retry on
`LLMUnavailableError`, alert on everything else — is what enables that distinction.

**Q5: "What happens if a page OCR fails? Does it corrupt the downstream citation index?"**

No. A failed page holds `""` in its position in the `pages` list, and its 1-based source ordinal
is recorded in `report.failed_pages`. Positions are never compacted — the list length is always
equal to the PDF page count, and `pages[i]` always corresponds to source ordinal `i + 1`. The tree
builder receives `""` for that page and produces whatever structure it can from the surrounding
content. The citation index is unaffected because page numbering is stable.

**Q6: "Why `ContextVar` for `llm_metadata` and not a function parameter?"**

Threading it through function parameters would mean editing approximately 20 upstream call sites
that currently receive `opt` — exactly the kind of upstream footprint the fork is designed to
minimize. A module-level global would cause a race condition: tree building dispatches many
concurrent asyncio tasks per document, and a plain global's `.set()` from one task would
overwrite another's `.get()`. `ContextVar` is the asyncio-native solution: each task inherits
the value set in its parent coroutine, so tasks belonging to different documents (if the consumer
ever runs concurrently) do not interfere.

**Q7 (likely follow-up to §1 bug): "How did both return sites get missed?"**

The `page_index_builder` inner function has two early returns — one inside
`if opt.if_add_doc_description == 'yes'` and one outside it. The first was updated; the second
was not. The bug is invisible without an end-to-end run with real credentials that checks the
returned `doc_name` field, which could not be done on this machine. It would be caught immediately
by the manual verification step in the merge checklist.
