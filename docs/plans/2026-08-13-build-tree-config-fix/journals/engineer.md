# Engineer Journal — build-tree-config-fix
## Skill: backend-python
## Service: pageindex/
## Plan: docs/plans/2026-08-13-build-tree-config-fix/plan.md

### Work Log

#### [10:00] Task 1: Defaults as a Python module (pageindex/config.py)
**What:** Created `pageindex/config.py` with `DEFAULT_CONFIG` dict mirroring the 10 keys from `config.yaml`. `summary_model` and `retrieve_model` are `None` rather than the old concrete placeholder strings ("gpt-5.6-luna", "gpt-5.4"), which were never real models — they existed only as documentation noise. Setting them to `None` is correct: `page_index.py:1263` already falls back to `model` when they are falsy.
**Why:** setuptools packages `.py` files by default; a `.yaml` requires explicit `package_data` config. Moving defaults into a module means they always travel in the installed package, removing the `FileNotFoundError` that consumers hit after `uv add git+...`.
**Alternatives considered:** keeping `config.yaml` as `package_data` via `pyproject.toml` — rejected because it requires both a manifest entry and user awareness; a `.py` module is zero-friction.
**Files touched:** `pageindex/config.py` (created)

#### [10:05] Task 2: ConfigLoader reads from DEFAULT_CONFIG (not YAML)
**What:** Added `from .config import DEFAULT_CONFIG` import, replaced `ConfigLoader.__init__` + `_load_yaml` with a one-liner that copies `DEFAULT_CONFIG` (or a caller-supplied override), removed the orphaned `import yaml` line.
**Why:** After Task 1, `_load_yaml` is the only consumer of `yaml` in `utils.py`. Removing it and the import eliminates a runtime dependency on a YAML file that no longer ships.
**Alternatives considered:** keeping `_load_yaml` as a fallback for backward compatibility — unnecessary because all five call sites pass no args, so the new `defaults=None` default covers them.
**Files touched:** `pageindex/utils.py`

#### [10:10] Task 3: build_tree builds opt and calls page_index_main
**What:** Rewrote `build_tree.py` to import `ConfigLoader` and `page_index_main` instead of `page_index`. The function now calls `ConfigLoader().load(kwargs or None)` to get a validated `opt`, then passes it to `page_index_main`. The docstring is updated to reflect that invalid keys raise `ValueError`.
**Why:** `page_index()` has a fixed parameter list that does not include `summary_model` or `retrieve_model`, so passing those as `**kwargs` would fail with `TypeError`. Routing through `page_index_main(doc, opt)` bypasses that restriction — `opt` is a SimpleNamespace that carries all config keys and `page_index_main` reads them from the object, not from its own signature.
**Alternatives considered:** monkeypatching `page_index`'s signature — rejected as invasive and fragile; the plan's `page_index_main` route is the right seam.
**Files touched:** `pageindex/build_tree.py`

#### [10:15] Task 4: Log the resolved LLM provider (observability)
**What:** Added `_logged_models` set and `_log_provider_once` helper near `_is_openai_model`. Called it in both `llm_completion` and `llm_acompletion` after the prefix-stripping block, before `max_retries`.
**Why:** A tree run generates hundreds of LLM calls; emitting one INFO line per distinct model string gives operators the routing confirmation they need without flooding the log. The guard is a module-level set so it survives across calls in the same process.
**Alternatives considered:** using a `functools.lru_cache` on the helper — skipped; `lru_cache` works on return value, not side-effects. The set guard is clearer.
**Files touched:** `pageindex/utils.py`

#### [10:20] Task 5: Delete config.yaml
**What:** Ran `git rm pageindex/config.yaml`.
**Why:** Nothing reads it anymore; keeping it would be misleading — a stale file suggests it still drives behavior.
**Files touched:** `pageindex/config.yaml` (deleted)

#### [10:25] Task 6: Update textual references + FORK_NOTES.md
**What:** Replaced `config.yaml` mentions with `config.py` in help strings/comments in `run_pageindex.py` and `pageindex/tree_optimize.py`. Extended `FORK_NOTES.md` divergence #1 to document: defaults live in `config.py`, `build_tree` accepts any valid key via kwargs, and provider is logged once per model at INFO.
**Why:** Stale documentation is a future debugging trap. The help strings are the primary documentation for CLI users; they must reflect reality.
**Files touched:** `run_pageindex.py`, `pageindex/tree_optimize.py`, `FORK_NOTES.md`

#### [10:30] Task 7: Regression + real-PDF verification
**What:** Ran `python -m pytest -q`. Task 7 Step 2 (real-PDF Bedrock run) is owner-run — requires AWS credentials not present in this environment.
**Files touched:** none
