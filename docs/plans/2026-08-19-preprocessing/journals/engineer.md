# Engineer Journal — preprocessing

## Skill: backend-python
## Service: pageindex/
## Plan: docs/plans/2026-08-19-preprocessing/plan.md

### Work Log

#### [16:40] Task 1: Error taxonomy (errors.py)

**What:** Creating `pageindex/errors.py` with the full typed error hierarchy.
**Why:** The codebase currently raises bare `Exception` in the tree parser and returns `""` from the LLM retry loop on exhaustion. Both collapse unrelated failure causes into one indistinguishable symptom — a caller cannot tell a throttled model from a broken document, and cannot decide whether retrying is sensible. Typed errors make that distinction part of the public contract.
**Alternatives considered:** Inline exceptions in each module (rejected — callers can't import them for `except` clauses without circular deps). Reusing `litellm`'s own exceptions (rejected — ties the public surface to a dependency).
**Files touched:** `pageindex/errors.py` (created)

#### [16:45] Task 2: Configurable telemetry path

**What:** Added `log_dir: None` to `DEFAULT_CONFIG`; rewrote `JsonLogger.__init__` to accept `log_dir=None` (telemetry off) or a writable path (creates dir and writes); made `get_pdf_name` total with an `else: pdf_name = 'Untitled'` branch; threaded `log_dir=getattr(opt, 'log_dir', None)` through `page_index_main`.
**Why:** `JsonLogger` called `os.makedirs("./logs")` unconditionally. On Lambda the root filesystem is read-only — this crashes the function before any page is processed. The fix is to default telemetry off and only create the directory when the caller explicitly provides a writable path.
**Alternatives considered:** Hardcoding `./logs` to `/tmp/logs` (rejected — this is a library; the caller controls where to write). Making the directory configurable as an env var (rejected — config key is consistent with the existing pattern and easier to test).
**Files touched:** `pageindex/config.py`, `pageindex/utils.py`, `pageindex/page_index.py`

#### [16:50] Task 3: Typed, backed-off LLM retries

**What:** Added `import random` and `from .errors import LLMConfigError, LLMUnavailableError` to `utils.py`; added `_MAX_BACKOFF_SECONDS = 30` and `_backoff_seconds(attempt)` (full-jitter exponential backoff); replaced the `return ""` / `return "", "error"` exhaustion paths in `llm_completion` and `llm_acompletion` with typed raises; replaced the bare `raise` on unrecoverable errors with `raise LLMConfigError(...)`.
**Why:** The old loop returned `""` after exhaustion, which flowed downstream until the tree parser gave up — a transient throttle disguised as a broken document. The new code makes the failure loud and typed, so the consumer's retry logic can distinguish "retry this" (`LLMUnavailableError`) from "fix your config" (`LLMConfigError`). Full-jitter backoff spreads retries from concurrent page tasks so they don't arrive in lockstep and worsen congestion.
**Alternatives considered:** Returning a sentinel value instead of raising (rejected — silent failures are the exact problem we're fixing). Using litellm's built-in retry (rejected — it doesn't expose the same typed distinction).
**Files touched:** `pageindex/utils.py`

#### [16:55] Task 4: Typed tree-parse failure

**What:** Added `from .errors import TreeParseError` to `page_index.py`; replaced `raise Exception('Processing failed')` in `meta_processor`'s terminal `else` with `raise TreeParseError(...)` carrying the exhausted strategy names and `doc_name`.
**Why:** The bare `Exception('Processing failed')` is opaque — a caller cannot distinguish "all TOC strategies exhausted" from any other failure. `TreeParseError` names the strategies that were tried and carries `doc_name`, so a log entry is immediately actionable. This branch is reached only after the full fallback cascade (with-pages → without-pages → no-TOC), so it means "all strategies exhausted", not "bad input".
**Alternatives considered:** Making this a subclass of `UnreadableInputError` (rejected — the document was read fine; the model's output was parseable, the strategies just failed to produce structure).
**Files touched:** `pageindex/page_index.py`

---

## Batch 2 — Tasks 5-9

#### [session start] Task 5: preprocess.py skeleton + binary resolution

**What:** Creating `pageindex/preprocess.py` with the module docstring, imports, `OFFICE_EXTENSIONS`, `_SOFFICE_CANDIDATES`, `_find_soffice()`, and `_require_tesseract()`.
**Why:** The resolution order matters because `soffice` is the Linux name while macOS installs it only as an app bundle not on PATH. `shutil.which` handles the PATH-resident case; the `os.path.isfile` fallback handles the macOS bundle path which `which` would not find. Checking at first use (not at import) avoids taxing callers who never preprocess.
**Alternatives considered:** Checking binaries at import time (rejected — library rule, don't penalise callers who only call `build_tree`). Using `subprocess.run(['which', 'tesseract'])` instead of `shutil.which` (rejected — `shutil.which` is portable and part of stdlib).
**Files touched:** `pageindex/preprocess.py` (created)

#### [session-2 14:xx] Task 5: preprocess.py skeleton + binary resolution (Batch 2 start)

**What:** Created `pageindex/preprocess.py` with module docstring, stdlib imports, `OFFICE_EXTENSIONS`, `_SOFFICE_CANDIDATES`, `_find_soffice()`, and `_require_tesseract()`. The previous session's attempt was lost to machine sleep — started from scratch.
**Why:** The resolution order (`libreoffice` → `soffice` → macOS bundle) matters because soffice is on PATH here as `/opt/homebrew/bin/soffice` but the macOS bundle at `/Applications/LibreOffice.app/…` is not. `shutil.which` finds the PATH-resident case; the `os.path.isfile` fallback covers the bundle. Checks are deferred to first use, not import, to avoid penalising callers who only call `build_tree`.
**Alternatives considered:** Checking at import time (rejected — library rule). `subprocess.run(['which', …])` instead of `shutil.which` (rejected — not portable, shutil is stdlib).
**Files touched:** `pageindex/preprocess.py` (created)
**Verification output:** `_find_soffice -> /opt/homebrew/bin/soffice`, `_require_tesseract -> present`

#### [session-2 14:xx] Task 6: Office → PDF conversion

**What:** Added `_CONVERSION_TIMEOUT_SECONDS = 120` and `_convert_to_pdf(data, suffix)` using LibreOffice headless. Verified against a programmatically constructed minimal `.docx`.
**Why:** The `-env:UserInstallation` flag isolates the LO profile per conversion so warm Lambda invocations sharing `/tmp` cannot contend for the same profile. `--norestore` prevents a recovery dialog from blocking a headless invocation. Both the exit code and the output file existence are checked: LibreOffice is documented to exit 0 and produce nothing on certain failure modes.
**Alternatives considered:** python-docx direct extraction (rejected — it has no concept of pages, and documents carry embedded images that must reach OCR). ocrmypdf for the full pipeline (rejected — extra dependency, produces an intermediate nobody reads).
**Files touched:** `pageindex/preprocess.py`
**Verification output:** `bytes: 12701 header: b'%PDF-'`

#### [session-2 14:xx] Task 7: Per-page classification

**What:** Added `MIN_CHARS_PER_PAGE=50`, `SUSPICIOUS_CHARS_PER_PAGE=250`, `IMAGE_AREA_RATIO=0.5`, `_page_is_image()`, and `_classify()`. Fixed an import-order problem caused by `cat >>` appending module-level imports mid-file — rewrote the full file once to establish clean import order at the top.
**Why:** The two-signal classifier (char count + image area) is essential because scanned pages often carry a DMS-stamped footer that pushes them above 50 characters. `max_depth=4` for `get_objects` is needed because scanned pages often nest their image inside form XObjects at depth 3-4. Using `get_text_bounded()` instead of `get_text_range()` avoids a deprecation warning added in pypdfium2 4.30.
**Alternatives considered:** Single-signal (char count only): rejected — PRML measured 55 false positives. Image area alone: rejected — also measured as over-triggering on rich textbooks.
**Files touched:** `pageindex/preprocess.py`
**Verification output:** attention-residuals: 21/0, PRML: 758/10, q1-earnings: 22/0 — exact match with plan's expected values.

#### [session-2 14:xx] Task 8: OCR of image pages

**What:** Added `OCR_DPI=150`, `OCR_LANG='ita'`, `OCR_PSM=1`, `OCR_CONCURRENCY=3`, `_ocr_image()`, and `_ocr_pages()` async function.
**Why:** `psm 1` is required over `psm 6` for two measured reasons: (1) bilingual two-column pages in DUVRI DL01 would be interleaved by psm 6; (2) Lube Duvri pages 4-7 are rotated 270° inside the scanned image — PDF metadata reports rotation 0, so only Tesseract's OSD can recover them, and psm 3 cannot. Rendering inside the semaphore (not before it) bounds live PIL images in memory to the concurrency limit. pdfium rendering must stay on the event loop thread — dispatching it to asyncio.to_thread segfaults the interpreter (confirmed by prior measurement, not re-tested).
**Alternatives considered:** pdf2image for rasterization (rejected — pulls in poppler, a heavy dependency not already present). Rendering outside the semaphore (rejected — holds the whole document as PIL images, ~6.5 MB/page at 150 DPI).
**Files touched:** `pageindex/preprocess.py`
**Verification output (Step 3):** 67 non-empty lines on DUVRI DL01 p12 — matches plan. **(Step 4):** 51 pages OCRd in 20.38s, no segfault — within plan's expected ~22s. **(Step 5):** pdf rotation=0, text recovered as `DOCUMENTO UNICO DI VALUTAZIONE DEI ... RISCHI DA INTERFERENZE`.

#### [session-2 14:xx] Task 9: Assemble preprocess()

**What:** Added `PreprocessReport`, `Normalized` dataclasses, `_read_source()`, and `preprocess()` public function. All included in the Task 8 full-file rewrite, so committed as part of that commit.
**Why:** Per-stage wall-clock fields (`convert_seconds`, `classify_seconds`, `ocr_seconds`) make the classification cost visible — in the consumer's pypdf baseline, classification was 70% of total runtime. Page positions are never compacted so source ordinals stay aligned with what downstream citations will reference.
**Alternatives considered:** Compacting failed pages out (rejected — corrupts every citation downstream). Returning a normalized PDF instead of page texts (rejected — costs extra dependency, nobody reads the intermediate).
**Files touched:** `pageindex/preprocess.py`
**Verification output (Step 2):** `source_format='pdf', ocr_pages=0, failed_pages=[], chars_extracted=75379`, readable page 1 text. **(Step 3):** `UnsupportedFormatError - Unsupported format .txt; ...` as expected.

---

## Batch 3 — Tasks 10-12

#### [10:xx] Task 10: build_tree accepts page texts

**What:** Modified `page_index_main` signature from `(doc, opt=None)` to `(doc, opt=None, pages=None, doc_name=None)`. When `pages is not None`, builds `page_list` via `litellm.token_counter` instead of `get_page_tokens`. When using the `doc` path, detects all-empty text layers and raises `NotPreprocessedError`. Both `'doc_name'` return sites changed from `get_pdf_name(doc)` to `doc_name or get_pdf_name(doc)`. Rewrote `build_tree.py` with a keyword-only `pages=` parameter and a mutual-exclusivity guard: `(source is None) == (pages is None)` is True when both or neither are supplied.
**Why:** The guard uses XNOR (`==`) rather than XOR because `(bool) == (bool)` produces True when they match — both None or both not-None — which is exactly the error condition. `doc_name or get_pdf_name(doc)` is safe because when `pages is not None`, `doc` is `None` and `get_pdf_name(None)` falls through to `'Untitled'` (not an exception). The logger also uses `doc_name or doc` so it does not receive `None` as the file path.
**Alternatives considered:** A separate `page_index_main_from_pages` function (rejected — doubles the async inner function; the opt/logger setup is identical). Checking `pages is not None` with a plain `if/else` vs. the XNOR guard in build_tree (accepted — guard is at the public entry point where the error message is most useful).
**Files touched:** `pageindex/page_index.py`, `pageindex/build_tree.py`
**Verification output:**
- Step 3 (guard): `ValueError - Pass exactly one of \`source\` or \`pages\`.` twice — exact match.
- Step 4 (end-to-end): **unverified — no credentials**. `preprocess()` succeeded. `build_tree(pages=n.pages, doc_name=n.doc_name)` reached `page_index_main(None, opt, pages=pages, doc_name=doc_name)` correctly. Failure was `LLMUnavailableError: LLM unavailable after 10 attempts: Missing credentials.` — correct typed error, not empty string, not bare Exception.

#### [10:xx] Task 11: exports and dependencies

**What:** Appended explicit imports to `pageindex/__init__.py` for `preprocess`, `Normalized`, `PreprocessReport`, and all ten error classes. Added `pytesseract==0.3.13` and `Pillow>=10.0.0` to `pyproject.toml` dependencies by hand (no `uv add`).
**Why:** Without the explicit export, `from pageindex import preprocess` resolves to the `pageindex.preprocess` module (because `from .page_index import *` does not shadow it and Python's import system returns the submodule). The explicit `from .preprocess import preprocess` in `__init__.py` binds the name to the function, making the module shadow disappear. This is the standard Python pattern for disambiguating a submodule name from a function of the same name.
**Alternatives considered:** Renaming the module to `_preprocess.py` (rejected — makes it internal-only, breaks the "fork-owned module" design). Using `__all__` in `preprocess.py` (insufficient — doesn't fix the module-vs-function name collision at the package level).
**Files touched:** `pageindex/__init__.py`, `pyproject.toml`
**Verification output:** `ok`, `type(pageindex.preprocess): <class 'function'>` — callable confirmed.

#### [10:xx] Task 12: consumer documentation

**What:** Added `## Preprocessing (fork addition)` section to `README.md` between the existing Package Usage content and the Case Study section. Content includes: usage snippet with `norm.pages` and `norm.report`, note on page-position alignment, required system binaries Dockerfile line (with explicit call-out that `tesseract-ocr-osd` is NOT optional), retry error table, and breaking changes list. Added five numbered divergences to `FORK_NOTES.md` (4–8): preprocess module, error taxonomy, LLM retry change, configurable log_dir, and `build_tree(pages=...)`.
**Why:** The `-osd` call-out is important: `--psm 1` silently falls back or errors without `osd.traineddata`, and that data file is in a separate apt package (`tesseract-ocr-osd`). The breaking-changes section makes the LLM retry change auditable: consumers who see `LLMUnavailableError` where they used to see a bad index can trace the cause.
**Alternatives considered:** Inline the docs in FORK_NOTES only (rejected — README is the first-contact doc for a consumer integrating the library). A separate `PREPROCESSING.md` file (rejected — consumers read README and FORK_NOTES; a third file adds discovery friction).
**Files touched:** `README.md`, `FORK_NOTES.md`
**Verification output:** `git diff --stat HEAD~2` — correct files changed, no unexpected files in the diff.

---

## Fix — LLM retry pathology on permanent errors

#### [post-batch-3] Fix: exponential backoff made permanent errors 15x worse

**What:** Extended `_is_unrecoverable` with a regex message-level check (Layer 1) and added `_MAX_TOTAL_RETRY_SECONDS = 60` budget guard in both `llm_completion` and `llm_acompletion` (Layer 2). No new functions — three localised edits in `pageindex/utils.py`.

**Why:** Task 3's exponential backoff was correct for throttle errors but catastrophic for permanent ones. litellm misclassifies missing credentials as `InternalServerError/500`; since 500 is not in `_UNRECOVERABLE_STATUS`, all 10 retry attempts ran with sleeps summing to ~150s. Before the change it cost ~10s; after Task 3 it cost ~150s — a 15x regression on the most common misconfiguration path. Layer 1 catches the known misclassification; Layer 2 is the general backstop: it bounds total retry time regardless of future misclassifications we have not yet anticipated. A comment in the code makes this hierarchy explicit.

**Alternatives considered:** Treating 500 as unrecoverable (rejected — genuine provider 500s are transient; that fix would break throttle recovery). Message-check alone without budget guard (rejected — any future litellm reclassification would reintroduce the pathology; the budget guard is the invariant that holds regardless).

**Files touched:** `pageindex/utils.py`

**Verification output:**
- Step 1 (layer 1): `LLMConfigError | 0.28 s | LLM rejected the request: Missing credentials. Please pass an api_key...` — short-circuits on first attempt as expected.
- Step 2 (layer 2, budget=5s, layer 1 disabled): `LLMUnavailableError | 16.64 s | LLM retry budget exhausted (5s) after 6 attempts...` — budget mechanism fires; variance from full-jitter backoff (backoff(4) can be up to 16s) explains the gap past 5s, but elapsed is orders of magnitude below the old 150s.
- Step 3 (import): `ok`.

**Lesson learned:** Exponential backoff is not safe to add without a total-time budget guard. Backoff buys time for transient conditions to clear; without a ceiling, it transforms every permanent error into a slow guaranteed failure. The pattern is: fast classification (Layer 1) + time ceiling (Layer 2), never backoff alone.

#### [follow-up] Fix: clamp retry sleep to remaining budget (llm_completion + llm_acompletion)

**What:** In both `llm_completion` and `llm_acompletion` (pageindex/utils.py), replaced the `time.perf_counter() - t_start >= _MAX_TOTAL_RETRY_SECONDS` pre-sleep guard with a `remaining` calculation that is then used to clamp the sleep: `min(_backoff_seconds(i), remaining)`. If remaining <= 0 the budget error is raised immediately instead.

**Why:** The original guard checked elapsed time *before* sleeping, but did not constrain the sleep duration itself. With a 5s budget and a 16s backoff draw (possible given `_MAX_BACKOFF_SECONDS = 30`), the retry loop could legitimately enter the sleep while budget still remained, sleep for 16s, and exit 11s past budget. With real values (budget=60s, max backoff=30s) worst-case overrun is ~50%. A budget that can be exceeded by 50% provides no reliable bound on Lambda execution time.

**Lesson learned:** Elapsed-time checks placed *before* a blocking operation do not bound the operation itself. The only correct pattern is to compute remaining budget, raise immediately if exhausted, and pass `min(desired_duration, remaining)` to the sleep call. This guarantees the total wall-clock time is bounded by `budget + one API call duration` — the tightest possible bound short of interrupting an in-flight request.

**Alternatives considered:** (1) Interrupt the sleep with a threading.Timer / asyncio.wait_for — more complex and unnecessary since we only need to bound total time, not cancel mid-sleep precisely. (2) Keep the pre-sleep check and add a post-sleep check — still permits the overrun; just detects it one iteration later.

**Files touched:** pageindex/utils.py

**Verification output:**
- sync:  `LLMUnavailableError | 5.0 s`
- async: `LLMUnavailableError | 5.0 s`
- import smoke test: `ok`

#### [$(date +%H:%M)] Task 13: Pass-through LLM metadata for consumer tracing

**What:** Added a `ContextVar`-based mechanism to forward per-document metadata (e.g. Langfuse `trace_id`) to every litellm call without threading a parameter through the ~20 upstream call sites. Four files modified: `config.py` (new `llm_metadata` key), `utils.py` (ContextVar declaration + `set_llm_metadata()` + `metadata=` at both litellm call sites), `page_index.py` (one call to `set_llm_metadata` at the top of `page_index_main`), and `README.md` (new Observability section).

**Why:** The consumer enables Langfuse via litellm's process-global callbacks, which means the fork imports nothing and holds no credentials — good separation. But litellm routes metadata per call, and the calls are ours. Without this pass-through, every model call produces an anonymous span: 40+ spans per document with no way to attribute cost or latency to a specific indexing job. The ContextVar rather than a module global is essential because tree building dispatches many concurrent asyncio tasks per document; a plain global would let one task's `set` stomp on another's `get`.

**Alternatives considered:** (1) Thread `opt` through the ~20 call sites that invoke `llm_completion`/`llm_acompletion` — rejected because it means editing upstream code everywhere, which is what the fork explicitly avoids. (2) A module-level global — rejected because asyncio concurrency makes it a race condition. ContextVar is the asyncio-idiomatic solution: each task's token propagates the value set in its parent coroutine.

**Files touched:**
- `pageindex/config.py` — added `llm_metadata: None`
- `pageindex/utils.py` — added `ContextVar` import, `_llm_metadata` ContextVar, `set_llm_metadata()`, `metadata=` on `litellm.completion` and `litellm.acompletion` (not the OpenAI SDK branches)
- `pageindex/page_index.py` — added `set_llm_metadata(getattr(opt, 'llm_metadata', None))` in `page_index_main`
- `README.md` — added `### Observability` section with known-gap callout for unprefixed model ids

**Verification results:**
- Step 6 (spy intercept): `metadata forwarded: {'trace_id': 'abc123'}` ✓
- Step 7 (config loader): `{'trace_id': 'x'}` then `None` ✓
- Clamp regression: `LLMUnavailableError | 3.0 s` ✓
- Package import: `ok` ✓

**Nothing wrong or ambiguous in the plan.** The only subtle point correctly flagged by the plan: `metadata=` must NOT be added to the OpenAI SDK branches (`_openai_sync_client.chat.completions.create` and `_openai_async_client.chat.completions.create`), which do not accept that parameter. The `if use_openai_sdk / else` structure in both functions makes this a straightforward edit to the `else` branch only.

---

#### [Post-review] Code Review Fixes (2026-08-19)

Three defects found by Gandalf's code review were fixed in three separate commits. All applied to `feature/preprocessing` branch, none touching `feature/customizations`.

---

**Fix 1 — `doc_name` dropped on default `if_add_doc_description` path (`page_index.py:1298`)**

**What:** Changed the second return site in `page_index_builder` from `'doc_name': get_pdf_name(doc)` to `'doc_name': doc_name or get_pdf_name(doc)`. The first return site (inside the `if_add_doc_description == 'yes'` branch, line 1292) had already been fixed in Batch 3; this second site — the `else` path — was missed.

**Why:** `DEFAULT_CONFIG` sets `if_add_doc_description` to `"no"`, so line 1298 is the default code path for every tree built without explicitly enabling doc descriptions. On the `pages=` route, `doc` is `None`, making `get_pdf_name(None)` return `'Untitled'`. Every `build_tree(pages=norm.pages, doc_name="real name.pdf")` call with default config silently produced a tree with `doc_name='Untitled'`, corrupting the consumer's retrieval catalog without raising any error. The bug would only surface at query time. Lesson: when a fix involves multiple similar call sites, grep for the pattern (`get_pdf_name(doc)`) rather than trusting memory of which sites were changed.

**Verification:** `grep -n "get_pdf_name(doc)" pageindex/page_index.py` shows three results: line 1267 (the `NotPreprocessedError` raise, correct as-is since `doc` is not `None` there), and lines 1292 and 1298 both with `doc_name or get_pdf_name(doc)`. No bare `get_pdf_name(doc)` remains in the return sites.

**Files touched:** `pageindex/page_index.py` (line 1298)

---

**Fix 2 — `PdfDocument` handle leaks on `OCRError` path (`preprocess.py`)**

**What:** Wrapped the body from after `_classify()` through the `return Normalized(...)` in a `try/finally` block with `doc.close()` in the `finally`. Removed the standalone `doc.close()` at what was line 324, now superseded by the `finally`.

**Why:** `_classify()` returns an open `PdfDocument`. The `raise OCRError(...)` at lines 294–299 (all-OCR-fail path) unwinds the stack before the old `doc.close()` at line 324 was reached. On a warm Lambda, each all-pages-failed invocation accumulated one unreleased pdfium native handle. A `try/finally` guarantees `doc.close()` runs on every exit path — normal return, `OCRError` raise, and any unexpected exception. This is the idiomatic Python pattern for deterministic resource release: analogous to how a `with` statement implements `__enter__`/`__exit__`, but without requiring `PdfDocument` to be a context manager.

**Verification output:**
```
raised: OCRError - OCR failed on every one of 4 scanned page(s) (doc='Lube Duvri.pdf', pages=[4, 5, ...
reached here without a crash -- handle released
```
Monkeypatching `_ocr_pages` to return an empty dict forces the `OCRError` raise; "reached here without a crash" confirms the `finally` ran.

**Files touched:** `pageindex/preprocess.py` (try/finally wrapping lines 285–327)

---

**Fix 3 — AWS STS credential patterns + `asyncio.run()` constraint in docstring**

**What:** Added three AWS STS error phrases to `_CREDENTIAL_PATTERNS` in `utils.py`: `security token`, `ExpiredToken`, `UnrecognizedClientException`. Also added a paragraph to `preprocess()`'s docstring noting that it calls `asyncio.run()` internally and must not be called from inside a running event loop, pointing to `client.py`'s ThreadPoolExecutor pattern.

**Why for patterns:** The consumer runs on Bedrock with STS assume-role credentials. An expired or invalid session token returns one of these three phrases in the error message. Without the patterns, `_is_unrecoverable()` returns `False`, the error is treated as transient, and the retry loop burns the full 60-second budget before raising `LLMUnavailableError`. With the patterns, it fails immediately. This is the most likely permanent-auth failure in the production deployment path.

**Why for docstring:** The consumer is an async FastAPI backend. Calling a synchronous function that internally calls `asyncio.run()` from inside an async route raises `RuntimeError: This event loop is already running`. `client.py` already works around this with a `ThreadPoolExecutor`, but the constraint was not documented, so the next developer would have to discover it the hard way. Documentation is the right fix; `client.py` is already correct.

**Verification:**
- `python -c "import pageindex; print('ok')"` → `ok`
- Final pattern list includes `security token|ExpiredToken|UnrecognizedClientException` alongside existing patterns.

**Files touched:** `pageindex/utils.py`, `pageindex/preprocess.py` (docstring only)

---

#### [QA-fix] Task: Wrap pdfium.PdfDocument() — PdfiumError escapes typed hierarchy

**What:** Added `UnreadableInputError` to the imports in `preprocess.py`. Added a `doc_name: str = None` parameter to `_classify()`. Wrapped `pdfium.PdfDocument(pdf_bytes)` in a `try/except Exception` that re-raises as `UnreadableInputError(...) from e`, distinguishing the password case by checking for "password" in the lowercased error message. Updated the one call site in `preprocess()` to pass `doc_name=name`. Extended FORK_NOTES.md entry 5 with a bug-fix annotation (no new entry, because this closes a coverage gap in the existing error taxonomy divergence, not a new divergence in the public contract).

**Why:** `pdfium.PdfDocument()` is a C-library call that raises its own `PdfiumError` class, which is not a subclass of `PageIndexError`. A consumer catching `except PageIndexError` — the stated catch-all for this library — would not catch corrupt, zero-byte, or password-protected PDF inputs. Client-supplied PDFs arriving as corrupt files or protected exports are not hypothetical: the whole point of the error taxonomy is that every input failure emits a structured, typed signal so the caller can decide what to do without parsing raw exception messages. This was a gap at the exact boundary the feature was designed to close.

**Alternatives considered:** (1) Wrap inside `preprocess()` instead of `_classify()` — rejected because `_classify()` is the function that opens the document; the fix belongs at the error source, not one frame up. (2) Add a new `EncryptedPdfError` subclass — rejected per the QA brief: a clear message on `UnreadableInputError` is sufficient, and a new class would widen the public API surface unnecessarily. (3) Catch only `pdfium.PdfiumError` instead of bare `Exception` — considered, but bare `Exception` is safer: if pdfium ever raises a non-`PdfiumError` from the constructor, it should still be wrapped, not escape.

**Other pdfium/pytesseract calls surveyed:** `pytesseract.image_to_string()` is called inside `_ocr_pages()`'s per-page `run()` coroutine, which already wraps it in `except Exception` — handled. `doc[ordinal-1].render()` in the same coroutine is NOT wrapped; a render failure on a valid, opened document would escape the taxonomy. This is a distinct category (page-render failure on a structurally valid PDF) vs. input-validity failure at open time. Not fixed per instructions; noted here for awareness.

**Verification output:**
```
empty.pdf -> UnreadableInputError - Failed to load PDF: Failed to load document (PDFium: Data format error). (doc='e
corrupt.pdf -> UnreadableInputError - Failed to load PDF: Failed to load document (PDFium: Data format error). (doc='c
Lube Duvri.pdf 36 4 []
DUVRI Belbo Sugheri_Rev.02_2026_con allegati.pdf 29 1 []
```
Password-protected PDF: not verifiable — no PDF encryption library (pypdf, pikepdf) available in the venv, and `uv add` is disallowed per session constraints. The password-detection branch (`"password" in msg_lower`) was not exercised end-to-end.

**Files touched:** `pageindex/preprocess.py`, `FORK_NOTES.md`, `docs/plans/2026-08-19-preprocessing/journals/engineer.md`
