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
