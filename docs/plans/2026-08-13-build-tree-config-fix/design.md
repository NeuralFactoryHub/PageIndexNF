# Design — `build_tree` usable without a packaged `config.yaml`

**Date:** 2026-08-13
**Branch:** `feature/customizations`
**Author:** Juan (owner) + WaLead (orchestrator)
**Status:** DRAFT — awaiting approval

---

## 1. Problem statement

Divergence #1 exposed `build_tree` as the public entry point. In a real run from the
consuming backend it **fails**: the backend had to bypass `build_tree` and call internals
(`page_index_main` + a hand-built `opt`) to produce the tree. That coupling to internals is
fragile and must be removed.

Two independent root causes:

1. **`config.yaml` does not travel in the package.** `ConfigLoader.__init__` (utils.py:929)
   reads `Path(__file__).parent / "config.yaml"`. With `[tool.setuptools.packages.find]` only
   `.py` files are packaged; `config.yaml` is *package-data* and does not enter the wheel.
   After `uv add`, the file is absent in the consumer's environment → `FileNotFoundError`
   when constructing `ConfigLoader()`. The underlying cause: the library's defaults live in a
   non-Python file that depends on packaging + `__file__`.

2. **`build_tree` cannot pass `summary_model` (or other valid keys).** `build_tree` delegates
   to `page_index()` (page_index.py:1283), whose signature enumerates only `model` and the
   toggles. `build_tree(..., summary_model=...)` → `**kwargs` → `TypeError: unexpected keyword
   argument`. The consumer cannot choose the summary model via the public API.

## 2. Scope

**In scope:** the two root causes above, on `feature/customizations`.

**Non-goals:**
- No changes to `main`.
- No domain wording (repo stays generic).
- No persistence in the library (the backend persists).
- No rewrite of upstream logic beyond the minimal patch per cause.
- No `--flash` (paid path).

## 3. Affected files

| Cause | File(s) | Anchor |
|---|---|---|
| #1 defaults without a file | `pageindex/config.py` (new), `pageindex/utils.py`, `pageindex/config.yaml` (delete) | `ConfigLoader` (L926) |
| #2 kwargs routing | `pageindex/build_tree.py` | `build_tree` |
| #3 provider observability | `pageindex/utils.py` | `llm_completion` (L57), `llm_acompletion` (L103) |

`pyproject.toml` is **not** touched (defaults become a `.py`, packaged by default — see §4.1).
`page_index.py` is **not** touched (thin fork — see §4.2). The ~5 importers of `ConfigLoader`
are **not** touched (it stays in `utils.py`).

---

## 4. Design per cause

### 4.1 Cause #1 — Defaults become a Python module (`config.py`)

**Principle:** a library's defaults are code, not a file on disk. setuptools **always** packages
`.py` files; a `.yaml` is *package-data* and does not travel without an explicit declaration.
Making the defaults a Python module removes the "file not packaged" bug by construction — and
`ConfigLoader` stops depending on `open()` + `Path(__file__)` (fragile under zipimport / a
packaged Lambda / a bundler).

**Fix:** replace `pageindex/config.yaml` with **`pageindex/config.py`** (same location, same
values) exposing a `DEFAULT_CONFIG` dict. `ConfigLoader` imports that dict instead of reading
YAML: the `__init__` that did `open()`/`_load_yaml` collapses to using `DEFAULT_CONFIG` as its
base. No file I/O.

```python
# pageindex/config.py  (new, fork-owned)
DEFAULT_CONFIG = {
    "model": "gpt-4o-2024-11-20",
    "summary_model": None,   # falls back to `model` (page_index.py:1263)
    "retrieve_model": None,  # falls back to `model`
    "toc_check_page_num": 20,
    "max_page_num_each_node": 10,
    "max_token_num_each_node": 20000,
    "if_add_node_id": "yes",
    "if_add_node_summary": "yes",
    "if_add_doc_description": "no",
    "if_add_node_text": "no",
}
```

This:
- Fixes the consumer's `FileNotFoundError` by construction (it is an import, not a file).
- Makes the defaults a single source of truth in code, in their own fork-owned module.
- `_validate_keys` validates against `DEFAULT_CONFIG`'s keys (same set as the current yaml).

**`summary_model` / `retrieve_model` default to `None`** (not the upstream concrete
placeholder). `page_index_main` (page_index.py:1263) does
`getattr(opt, 'summary_model', None) or opt.model`, so `None` falls back to `model`: passing
only `model="bedrock/…"` makes summaries use the same model. A concrete default (e.g.
`"gpt-5.6-luna"`) would force the consumer to always pass `summary_model` or get a wrong-provider
call — a footgun for a generic Bedrock-consumed fork.

**Accepted trade-off:** the on-disk `config.yaml` override is dropped. To change defaults, edit
`config.py`, or pass kwargs via `build_tree` / CLI args. Acceptable for a library (decided with
the owner, 2026-08-13).

### 4.2 Cause #2 — `build_tree` builds `opt` and calls `page_index_main`

**Fix:** `build_tree` stops delegating to `page_index()` (restrictive signature) and instead
does `ConfigLoader().load(kwargs)` → `page_index_main(doc, opt)`. `ConfigLoader` validates the
kwargs against `DEFAULT_CONFIG`, so it accepts **any valid key** (including `summary_model`,
`retrieve_model`, toggles) without enumerating signatures.

Mergeability upside: `page_index.py` (large, upstream) is **not** touched → less merge-conflict
surface. All fork logic lives in `build_tree.py`.

`build_tree` keeps the `source: bytes | str | Path` normalization it already has. Invalid keys
still raise `ValueError` (via `_validate_keys`), which is desirable (explicit failure, not
silent).

### 4.3 Cause #3 — Log the resolved LLM provider (observability)

**Motivation:** the fork does not decide the provider — it delegates to LiteLLM by model-string
prefix (`_is_openai_model`, utils.py:34). Today there is no fork-side signal of which provider a
run actually used; certainty requires enabling LiteLLM's own verbose logging or observing the
AWS call. A one-line log makes the resolved provider explicit.

**Fix:** a `_log_provider_once(model, use_openai_sdk)` helper, called in both `llm_completion`
(L57) and `llm_acompletion` (L103) right after the provider decision. Provider label =
`"openai"` when `use_openai_sdk`, else the prefix before `/` (`bedrock`, `anthropic`, …). Logged
at INFO, **once per distinct model per process** (module-level `set` guard) so a tree's hundreds
of calls do not spam the log.

**Fork-thinness note:** this touches upstream `utils.py` (two 1-line call sites + one additive
helper). Minimal and additive; documented in `FORK_NOTES.md`.

---

## 5. Acceptance criteria

- [ ] `from pageindex import build_tree` works after `uv add` in a clean environment (no
      `FileNotFoundError`; defaults come from `config.py`, packaged because it is a `.py`).
- [ ] `build_tree(pdf_bytes, model="bedrock/…", if_add_node_summary="yes")` builds the tree
      with summaries via the public API — passing only `model` is enough (summaries fall back to
      it). `summary_model="bedrock/…"` remains an optional override.
- [ ] `build_tree` accepts any valid config key and rejects invalid ones with `ValueError`.
- [ ] A `build_tree(..., model="bedrock/…")` run logs the resolved provider once
      (`provider='bedrock'`) at INFO — no per-call spam.
- [ ] The backend can delete the internals workaround and go back to `build_tree`.
- [ ] The existing test suite stays green (no new tests, per CLAUDE.md).

## 6. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Residual `config.yaml` referenced in docs/CLI after deletion | Grep the repo for `config.yaml`; update references. |
| `page_index_main` needs keys `page_index` set implicitly | `ConfigLoader().load()` produces the same `config` object `page_index` uses today; verify field parity. |
| Routing change alters output expected by tests | Run the suite before/after; same baseline. |
| Upstream merge touches `ConfigLoader` | Minimal, localized patch; document in `FORK_NOTES.md`. |

## 7. Open questions

1. ~~Keep or remove `config.yaml`?~~ **RESOLVED (2026-08-13):** remove it; `config.py` replaces
   it (canonical defaults in code, packaged because it is a `.py`).
2. Module name: `config.py` vs `defaults.py` (avoid confusion with the `config` SimpleNamespace
   alias in `utils.py` — no technical clash). To decide in PLAN.
3. Document as divergence #4 in `FORK_NOTES.md`, or extend #1? Proposal: extend #1 (same
   surface: packaging + public API).
