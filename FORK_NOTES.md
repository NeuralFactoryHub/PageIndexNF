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

## Config notes (not code changes — for the consumer)
- Pass `summary_model` as a kwarg to `build_tree` or set it in `pageindex/config.py`
  (`DEFAULT_CONFIG`). On the OSS path the `--summary-model` CLI flag is captured but not wired
  through `user_opt`; use `build_tree` kwargs instead.
- Avoid `--flash` (upstream paid hosted service).
