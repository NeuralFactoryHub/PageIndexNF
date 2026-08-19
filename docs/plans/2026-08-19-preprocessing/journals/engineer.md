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
