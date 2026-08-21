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

**2026-08-20 hardening:** `_is_unrecoverable` now also type-checks for `ImportError`,
`AttributeError`, and `TypeError` before any message inspection. Motivated by two real failures
(`ModuleNotFoundError: No module named 'langfuse'` and `AttributeError: module 'langfuse' has no
attribute 'version'`) that burned the full 60 s retry budget because neither carries a status code
nor reads like a credential error. Type-matching is independent of how litellm wraps the message
and keeps vendor names out of our code. `_CREDENTIAL_PATTERNS` renamed `_UNRECOVERABLE_PATTERNS`
to reflect its broadened scope.
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

**Extended (2026-08-20 — generation naming):** All litellm calls were labeled `litellm-completion`
(litellm's default), making Langfuse traces with ~40 generations per document unreadable.
Inside `llm_completion` and `llm_acompletion` (litellm branches only, not OpenAI SDK), derive
`generation_name` from `sys._getframe(1).f_code.co_name` — the name of the upstream function that
called into the fork's wrapper. The ContextVar dict is **copied** before adding the key; mutating
it in place would leak one call's name into every subsequent call for that document. Consumer's
own `generation_name` wins if already present. No upstream file edits required — new call sites
are named automatically.

Verified: 34 calls on a 2-page docx produced 5 distinct names
(`check_title_appearance`, `check_title_appearance_in_start`, `toc_detector_single_page`,
`generate_toc_init`, `generate_node_summary`); `trace_id` intact on all 34.

### 10. Fix TOC continuation loop — separate truncation from finished-but-rejected
**Why:** `toc_transformer` and `extract_toc_content` entered a "continue from where you left off"
loop whenever the checker said the output was incomplete, regardless of whether the model had
actually been truncated (`finish_reason == 'max_output_reached'`) or had finished normally
(`finish_reason == 'finished'`). Asking a model to continue a **complete** JSON makes it emit a
second, separate JSON object; concatenating that onto the first produces malformed input that the
checker correctly rejects forever. Measured on a 51-page document: 6 calls, all
`finish_reason='finished'`, all `if_complete='no'`, accumulated chars 2365 → 1414 → 141 → 41 → 41
→ 41 (41 = `{"table_of_contents": []}`), then raised bare `Exception`.

**Do:**
- `finish_reason == 'max_output_reached'` (truncated): keep existing continuation loop unchanged.
- `finish_reason == 'finished'` + checker says no: fresh single-shot retries of the original
  prompt (no chat history, no concatenation), up to 5 attempts.
- Bare `Exception` on retry exhaustion replaced by `TreeParseError` (already imported) so
  consumers can distinguish structured failures from bugs.

Same fix applied to both `extract_toc_content` and `toc_transformer` in `page_index.py`.

**Status:** DONE

### 10a. Fix `toc_transformer` dropping unnumbered TOC entries (e.g. "Allegati / Annex")
**Why:** The `init_prompt` described `structure` as "the numeric system which represents the index
of the hierarchy section". The model inferred its scope was numbered sections only and consistently
dropped trailing unnumbered entries (bare labels with no number, no page, no dot leader) such as
`Allegati / Annex` common in Italian safety documents. `check_if_toc_transformation_is_complete`
then correctly rejected the output, causing every retry to reproduce the same omission and
eventually raising `TreeParseError` after maximum retries. This is independent of the
continuation-loop bug fixed in §10.

**Root cause confirmed by:** three controlled experiments by the debugger — feeding only the
2305-char TOC page reproduced the same 15-entry output, ruling out input-selection as the cause.

**Fix:** one sentence added after "You should transform the full table of contents in one go."
in `toc_transformer`'s `init_prompt`:
> Include ALL entries present in the raw text — even unnumbered ones such as appendices, annexes,
> references, or prefaces — and set structure to null for those.

**Verified on:**
- Target (51-page DUVRI DL01_Toffetti.pdf): completes end-to-end, wall=103s, no `TreeParseError`.
  Tree has 9 top-level nodes. No explicit Allegati node visible in printed tree — the unnumbered
  entry appears to be absorbed by the large-node `process_no_toc` sub-path that fires on the
  section spanning pages 15–42 (100% accuracy there). Downstream page-assignment for null-page
  entries warrants a follow-up audit (see downstream risk note below).
- Regression 1 (DUVRI Belbo Sugheri_Rev.02_2026_con allegati.pdf): 10 top-level nodes,
  `[24-29] ALLEGATI` present, 100% accuracy. Unchanged.
- Regression 2 (BRIVAPLAST.docx, no-TOC path): 1 top-level node `[1-2] INFO PER GESTIONE DUVRI`,
  100% accuracy. Unchanged.

**Downstream risk (open):** a TOC entry with `page: null` (unnumbered entry without a page number)
feeds `process_toc_with_page_numbers` → `convert_page_to_int` → page-assignment logic. If that
path silently drops or misassigns such entries they will not appear as nodes in the final tree. On
the Toffetti document the Allegati entry is not visible as a distinct top-level node — likely
swallowed by the sub-path restructuring, not surfaced as a wrong-page node. Needs explicit audit on
a document where the unnumbered entry IS the only terminal node so the drop would be unambiguous.

**`extract_toc_content` assessment:** its prompt says "extract the full table of contents" without
numeric-only language and operates at raw-text level (no JSON schema). No gap found; no change made.

**Status:** DONE (prompt fix); downstream null-page handling open for audit.

### 11. `verify_toc` — tri-state result, mode-aware coverage check, flat-tree floor
**Why:** Two documents out of a six-document consumer batch (33%) raised `TreeParseError` despite
having their text extracted correctly. Both failures resolve to `verify_toc` (`page_index.py:1096`),
by two different paths.

**Path A — a correct structure discarded without being checked.** Upstream returned `0, []` from
the early guard `last_physical_index is None or last_physical_index < len(page_list)/2`. That
heuristic — "TOC entries should reach the document's midpoint" — holds for an *extracted* table of
contents, which by construction spans the document. It does not hold for a *generated* one. An
18-page scanned DUVRI (5 pages of numbered sections, 13 pages of unheaded annexes and signature
forms) produced a clean 12-entry TOC that the guard rejected at `last_physical_index=5 < 9.0`.
`check_title_appearance` never ran on a single entry. `meta_processor` cannot distinguish that
`0, []` from "every entry was checked and every entry was wrong", so it fell to the terminal
`else` and raised. **When the guard is skipped in this mode, the same document verifies at 100%.**

Aggravating detail: `tree_parser` enters `meta_processor` *directly* with `mode='process_no_toc'`
when no TOC is found, so the terminal branch fires on the first attempt. The message
"exhausted all TOC strategies (…, …, …)" named three strategies when one had run.

**Path B — a document with no hierarchy to find.** A 2-page form ("INFO PER GESTIONE DUVRI",
1734 chars) has field labels, not sections. `generate_toc_init` normalised 14 labels into
Title-Case headings, one on the wrong page. `check_title_appearance` correctly rejected 6 of 14
(e.g. generated `Referenti` against text reading "Referente cliente"; generated `Tipo di Pratica`
against "PRATICA / NUOVA / NULLA MUTATO"). At 0.5714 the structure fell below the `> 0.6` gate
and the whole document was discarded — including the 8 entries the judge had accepted.

The consumer attributed Path B to verifier variance. Measurement does not support that: five runs
of the failing document returned 0.5714 every time, and its two sibling documents from the same
template returned 1.00 and 0.9333 stably (`llm_completion` calls with `temperature=0`). One later
run of the 1.00 document returned 0.9375, so the judge is near-deterministic rather than exactly
deterministic — but the 1.00 / 0.93 / 0.57 spread is produced by the documents, not by run-to-run
noise. Sampling the judge N times would therefore cost N× and change nothing.

**Changes:**
- `verify_toc` returns `accuracy=None` for "could not check" — the three paths that produced
  `0, []` (no valid physical index, coverage guard, zero items checked) — leaving `0.0` to mean
  "checked, all wrong". `meta_processor` gates its comparisons on `accuracy is not None`.
- New `check_coverage` parameter, passed `False` when `mode == 'process_no_toc'`. That mode is
  terminal, so the guard there can only discard work, never redirect it.
- New config key `fallback_flat_tree` (default `"yes"`): when every strategy fails, return a
  single node spanning the document instead of raising. For a form with no sections this is the
  correct output, not a degraded one — and correctly extracted text is worth more to a caller as
  a flat index than as an exception. `page_index_main` reports which happened as
  `structure_source: "verified" | "flat_fallback"`; the tree alone cannot distinguish a floor
  result from a genuine one-section document.
- `process_large_node_recursively` skips subdivision when the floor fires, rather than grafting a
  child identical to its parent.
- `TreeParseError` (now only reachable with `fallback_flat_tree="no"`) names every strategy that
  ran and what each scored.
- `logger.info` emits the real `mode` instead of the hardcoded `'process_toc_with_page_numbers'`
  (`page_index.py:1172`). All consumer telemetry reported the wrong mode, costing diagnosis time.

**Verified on** (`bedrock/claude-haiku-4-5`, `preprocess()` → `build_tree()`):
- Target A (18-page scanned `260227 JUNGHEINRICH.pdf`): was `TreeParseError`; now 100% accuracy,
  13 top-level nodes, `structure_source: verified`.
- Target B (2-page `AMAZON MEZZATE.docx`): was `TreeParseError`; now 1 node `[1-2] Full document`
  with a summary, `structure_source: flat_fallback`.
- Regression (`AMAZON PIOLTELLO.docx`, `AMAZON BURAGO.docx`): 0.9375 / 0.9333, `verified`.
- Regression (`DUVRI Belbo Sugheri_Rev.02_2026_con allegati.pdf`, extracted-TOC path): 100%,
  10 top-level nodes, `verified`. Unchanged.
- Regression (`Lube Duvri.pdf`, no-TOC path): 100%, 7 top-level nodes, `verified`.
- Regression (`DUVRI DL01_Toffetti.pdf`, 51 pages, fully scanned): 93.33% then 100%, hierarchical
  tree to 4 levels, `verified`. Unchanged.

**Not established:** whether the judge's stricter rejections (3 of the 6 on Target B were literal
substrings of the page text, inside question sentences) misfire on documents that *do* have real
sections. None of the six documents showed it, but the corpus is small.

**Open:** `TreeParseError` still sits outside `UnreadableInputError`, so a caller catching only
`UnreadableInputError` as "permanent" retries it. Documented in `INTEGRATION.md` §4 with the
recommended catch; a shared base class for deterministic document-level failures would fix it
properly but changes the public exception hierarchy.

**Status:** DONE.

## Config notes (not code changes — for the consumer)
- Pass `summary_model` as a kwarg to `build_tree` or set it in `pageindex/config.py`
  (`DEFAULT_CONFIG`). On the OSS path the `--summary-model` CLI flag is captured but not wired
  through `user_opt`; use `build_tree` kwargs instead.
- Avoid `--flash` (upstream paid hosted service).
