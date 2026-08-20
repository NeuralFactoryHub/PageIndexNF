# Fork notes — PageIndexNF

Fork of [VectifyAI/PageIndex](https://github.com/VectifyAI/PageIndex).
All intentional divergences from upstream live here, each with its rationale, so the
fork stays **thin** and upstream updates remain mergeable.

**All customizations land on branch `feature/customizations`.**

> Scope rule: this repo is **generic** (reusable across clients/documents). Do NOT introduce
> any domain- or client-specific wording (no DUVRI, no Jungheinrich, no section names, etc.).
> Domain logic lives in the consuming application, never here.

## Divergences from upstream

### 1. Packaging — make the fork installable as a library
**Why:** the consuming backend installs this via `uv add "git+…@feature/customizations"` and
imports the tree-building entry point. Upstream ships as a run-script repo, not a package.
**Do:** add a minimal `pyproject.toml` and expose the tree-building entry point as a public
import (e.g. `from pageindex import build_tree`). Add `boto3` to deps (LiteLLM→Bedrock needs it;
missing upstream).
**Status:** DONE

**Extended (2026-08-13):**
- Library defaults moved from `config.yaml` (package-data, not auto-packaged) to
  `pageindex/config.py` (a `.py` module, always packaged). `ConfigLoader` reads from
  `DEFAULT_CONFIG` in that module; `_load_yaml` is removed. This eliminates the
  `FileNotFoundError` consumers hit after `uv add git+...` when no `config.yaml` is present.
- `build_tree` now routes through `ConfigLoader().load(kwargs) → page_index_main` instead of
  `page_index(**kwargs)`, so any valid config key — including `summary_model` and
  `retrieve_model` — can be passed as a kwarg. Invalid keys raise `ValueError` at call time.
- The resolved LLM provider is logged once per distinct model string at INFO level
  (`LLM dispatch: provider=... model=...`), giving operators routing visibility without
  enabling LiteLLM verbose logging.

### 2. Patch `offset=None` crash in `add_page_offset_to_toc_json`
**Why:** guaranteed crash on any document whose logical page numbering is misaligned
(e.g. numbering that starts at "2"). Blocks tree-building on real inputs.
**Do:** default `offset = 0` when `None`.
**Status:** DONE

### 3. Node-distinctive summaries — rewrite `generate_node_summary` prompt (`utils.py:638`)
**Why (generic):** the upstream prompt asks for a "description of the partial document", so every
node's summary opens with the same meta-preamble re-describing the whole document instead of the
node. Result: summaries are non-discriminative (near-identical across nodes), bury the
node-specific content, and are emitted in English regardless of source language. This makes them
nearly useless for deciding *which node to open* — the whole point of a summary.
**Do:** replace the prompt so the summary is **extractive, node-specific, self-contained**, with
no meta-preamble, in the **same language as the section text**. Proposed prompt:

```
You are given one section of a larger document. Write a summary of THIS
section only. State directly the specific topics, entities, values, and
details it contains. Do NOT describe the document as a whole, do NOT
restate its purpose or legal framework, and do NOT begin with phrases
like "This document is..." or "This section describes...". Start with the
content itself. Write in the same language as the section text.

Section text: {node['text']}

Return only the summary.
```

Keep the existing `SUMMARY_RAW_TEXT_TOKENS` behavior (tiny leaves reuse raw text as summary).
**Status:** DONE

**Adjusted (2026-08-13, owner decision):** the shipped prompt structures the instructions with
`###` section headers and prescribes a fixed opener — `Begin with: "In this section you will
find..."`. This intentionally departs from the "start with the content itself / no opener
phrase" wording above. Rationale: consistent, section-anchored summaries that keep the model
from drifting to whole-document description. Accepted trade-off: a constant leading phrase
carries no discriminative signal, so the node-distinctive content starts a few tokens later
(minor cost for retrieval/embedding). The core goals of #3 hold — section-scoped (not
whole-document) content, source-language output, no upstream meta-preamble.

### 4. Document preprocessing — `pageindex/preprocess.py`
**Why:** upstream indexes only born-digital PDFs. Real client documents arrive as scanned PDFs
and Office files. Scanned pages return empty text from `extract_text()`, so without OCR the tree
is built from blank pages and looks valid. OCR must run before tree building, not as a downstream
step, because section headings only exist as pixels in scanned annexes — a tree built from the
text layer loses the structural boundaries exactly where the annexes begin. `preprocess.py` is
isolated (like `build_tree.py`) so upstream merges do not conflict.
**Status:** DONE

**Extended (2026-08-20 — scope fix):** `OCR_LANG` default changed from `"ita"` to `"eng"`.
The Italian default was inherited from the first consumer and violated the generic-repo scope
rule (see preamble). Consumers targeting non-English documents must pass `ocr_lang` explicitly.

### 5. Typed error taxonomy — `pageindex/errors.py`
**Why:** upstream raises bare `Exception` everywhere and returns `""` on LLM exhaustion. Both
collapse unrelated causes into one indistinguishable symptom. A caller cannot tell a broken
document from a throttled model and cannot decide whether retrying is sensible. The typed
hierarchy makes that distinction part of the public contract: only `LLMUnavailableError` is
worth a retry.
**Status:** DONE

**Extended (2026-08-19 — bug fix):** `pdfium.PdfDocument()` in `_classify()` raised `PdfiumError`
(not a `PageIndexError` subclass) on zero-byte, corrupt, and password-protected PDFs, breaking the
typed contract for those inputs. Fixed by wrapping the constructor call in `_classify()` and
re-raising as `UnreadableInputError(...) from e`. Password-protected inputs are distinguished in
the message ("PDF is encrypted — provide an unlocked copy") so the consumer can act on the
specific cause. No new exception class introduced; the message on `UnreadableInputError` carries
the distinction. `_classify()` gains a `doc_name` parameter (one call site updated in
`preprocess()`) so the error carries the filename.

### 6. LLM retry raises `LLMUnavailableError` instead of returning `""`
**Why:** returning `""` on exhaustion let transient throttling be reported as a broken document —
a silent, wrong result that wasted the full retry budget before appearing. Raising a typed error
lets the caller see the cause immediately and decide whether to retry. This is a deliberate
breaking change: documents that previously indexed badly-but-successfully now fail loudly.

The retry loop also replaces flat 1 s sleeps with exponential backoff (full jitter) bounded by a
wall-clock budget (`_MAX_TOTAL_RETRY_SECONDS`, 60 s). The backoff alone made permanent failures far
more expensive than the flat sleep it replaced: a permanent error that slips past
`_is_unrecoverable` runs the whole series, `1+2+4+8+16+30+30+30+30 ≈ 151 s` worst case, against
9 s before. Measured with no credentials configured, that path took ~150 s — 15× the old cost, on a
Lambda where every failing call competes for one 890 s invocation.

Two layers bound it. `_is_unrecoverable` also matches the exception *message*, because litellm
reports missing credentials as `InternalServerError` with status 500 and a genuine 500 must stay
retryable — the status code alone cannot separate them. Independently, each sleep is clamped to the
budget still remaining (`min(backoff, remaining)`), so the budget holds exactly rather than being
overrun by up to one backoff interval. Verified: a 3 s budget returns at 3.01 s, an 8 s budget at
8.00 s. The clamp is the load-bearing half — it bounds any future misclassification the message
matching does not anticipate.
**Status:** DONE

### 7. Configurable `log_dir` — telemetry off by default
**Why:** `JsonLogger.__init__` previously called `os.makedirs("./logs")` unconditionally. On
Lambda the filesystem is read-only outside `/tmp`, so this crashed before a single page was
processed. `log_dir=None` (the new default) disables telemetry entirely; pass a writable path
to re-enable it.
**Status:** DONE

### 8. `build_tree(pages=...)` — second input path from `preprocess()`
**Why:** downstream the consuming backend extracts page text a second time, independently of the
tree, to build the catalog that `get_page_content` serves. Text hidden inside `build_tree` would
produce a correct tree while the backend kept serving blank pages. Returning `norm.pages` removes
that second read and makes one source of truth per document. The two paths (`source=` vs
`pages=`) are mutually exclusive; passing both is an error.
**Status:** DONE

### 9. Pass-through `llm_metadata` for consumer tracing
**Why:** the consumer enables Langfuse via litellm's process-global callbacks — the fork imports no
tracing SDK and holds no keys, so vendor choice stays entirely theirs. But Langfuse metadata
travels per call, and the model calls are the fork's; it cannot be injected from outside. The fork
owns the pass-through, not the instrumentation.

The value is carried on a `ContextVar` (`_llm_metadata`) set once in `page_index_main` and read at
the two `litellm.completion` / `litellm.acompletion` call sites. A ContextVar rather than a module
global because tree building dispatches many concurrent asyncio tasks per document — a plain global
would let one task's set stomp on another's get. Threading a new `metadata=` argument through the
~20 upstream call sites that invoke `llm_completion`/`llm_acompletion` was the alternative; it
would have produced ~24 hunks instead of 4, making future merge conflicts significantly harder to
read and resolve.

Known gap: a model id with no provider prefix (e.g. `gpt-4o-2024-11-20`) bypasses litellm via the
OpenAI SDK directly, so neither callbacks nor `llm_metadata` reach it. The symptom is metrics
silently vanishing, not an error. Prefixed models (`bedrock/...`, `anthropic/...`) are unaffected.
**Status:** DONE

## Config notes (not code changes — for the consumer)
- Pass `summary_model` as a kwarg to `build_tree` or set it in `pageindex/config.py`
  (`DEFAULT_CONFIG`). On the OSS path the `--summary-model` CLI flag is captured but not wired
  through `user_opt`; use `build_tree` kwargs instead.
- Avoid `--flash` (upstream paid hosted service).
