# Code Review — build-tree-config-fix

**Date:** 2026-08-13
**Branch:** feature/customizations
**Reviewer:** Reviewer agent

---

## Verdict: NEEDS_WORK

One undocumented behavioral change in `pageindex/utils.py` (the `generate_node_summary` prompt
rewrite) must be acknowledged in the plan and journal before this is PR-ready. All core bug-fix
tasks are correctly implemented and all acceptance criteria are satisfied.

---

## Layer 1: Plan Compliance

- [x] Task 1 — `pageindex/config.py` created with `DEFAULT_CONFIG` (10 keys, correct values).
- [x] Task 2 — `ConfigLoader.__init__` simplified to `dict(DEFAULT_CONFIG)`, `_load_yaml` removed,
      `import yaml` and `from pathlib import Path` removed. `import logging` reorganized to line 1
      (not dropped).
- [x] Task 3 — `build_tree.py` routes through `ConfigLoader().load(kwargs or None)` →
      `page_index_main`.
- [x] Task 4 — `_logged_models` set + `_log_provider_once` helper added; called in both
      `llm_completion` and `llm_acompletion` after prefix stripping, before `max_retries`.
- [x] Task 5 — `pageindex/config.yaml` deleted via `git rm`.
- [x] Task 6 — `run_pageindex.py`, `pageindex/tree_optimize.py`, `FORK_NOTES.md` updated; no
      code-path references to `config.yaml` remain.
- [x] Task 7 — Pytest run recorded (Step 1). Step 2 (Bedrock real-PDF run) deferred to owner per
      plan.
- [ ] **DEVIATION (not in any task):** `generate_node_summary` prompt rewritten in
      `pageindex/utils.py` (L654-672). The change adds a forced opener ("Begin with: 'In this
      section you will find...'"), restructures the prompt with `###` section headers, and removes
      the original "Start with the content itself" instruction. This behavioral change is absent from
      both the plan and the journal.

---

## Layer 2: Requirements Compliance

- [x] AC1 — Fixes `FileNotFoundError` by construction: `config.py` is a `.py` module, packaged
      by setuptools automatically. No file I/O in `ConfigLoader.__init__`. ✓
- [x] AC2 — `build_tree(pdf_bytes, model="bedrock/…", if_add_node_summary="yes")` works; passing
      only `model` is enough (summaries fall back to `model` via `page_index.py:1263` because
      `summary_model` defaults to `None`). ✓
- [x] AC3 — `build_tree` accepts any valid config key; invalid keys raise `ValueError` at call
      time (before PDF parsing), confirmed live: `ValueError: Unknown config keys: {'bogus'}`. ✓
- [x] AC4 — Provider logged once per distinct model string at INFO level; module-level
      `_logged_models` set guards repeat calls. ✓
- [x] AC5 — Backend can use `build_tree` directly; the internals workaround is no longer needed. ✓
- [x] AC6 — Test suite run recorded (Step 1). No new tests added (per CLAUDE.md). ✓

**Key parity verified:** `DEFAULT_CONFIG` has the same 10 keys as the deleted `config.yaml`.
Values for `summary_model` and `retrieve_model` changed from placeholder strings
(`"gpt-5.6-luna"`, `"gpt-5.4"`) to `None` — correct per design §4.1 (falls back to `model` via
`page_index.py:1263`).

---

## Layer 3: Code Quality

### Fork-thinness constraint

| File | Modified? | Expected |
|---|---|---|
| `pageindex/page_index.py` | No | Not modified ✓ |
| `pageindex/client.py` | No | Not modified ✓ |
| `pageindex/flash/api.py` | No | Not modified ✓ |
| `pyproject.toml` | No | Not modified ✓ |
| `pageindex/tree_optimize.py` | Yes — textual refs only | Task 6 ✓ |

### ConfigLoader callers — backward-compat check

All five call sites use `ConfigLoader()` with no arguments:
- `client.py:46` — `ConfigLoader().load(overrides or None)` ✓
- `flash/api.py:113` — `ConfigLoader().load()` ✓
- `page_index.py:1291` — `ConfigLoader().load(user_opt)` ✓
- `tree_optimize.py:744` — `ConfigLoader().load({})` → equivalent to `load(None)` ✓
- `build_tree.py` — new caller, uses `ConfigLoader().load(kwargs or None)` ✓

The renamed parameter `default_path` → `defaults` does not break any caller because all sites
pass no args.

### `kwargs or None` in `build_tree.py:38`

When `build_tree` is called with no kwargs, `kwargs = {}` (empty dict, falsy) →
`kwargs or None` → `None` → `load(None)` → all defaults. Correct.

### `_log_provider_once` edge cases

- `model=None`: `None and "/" in None` short-circuits to `False` → `provider="openai"`. Safe. ✓
- `model=""`: same short-circuit. Safe. ✓
- `model="gpt-4o"` (no `/`): `"gpt-4o" and "/" in "gpt-4o"` → `False` → `provider="openai"`.
  When `use_openai_sdk=True`, branch also gives `"openai"` — consistent. ✓
- Unbounded set growth: acceptable for a library (one entry per distinct model string per
  process; sets in practice stay small).

### Residual `config.yaml` references

`grep -rn "config.yaml"` across `pageindex/` and `run_pageindex.py` returns zero hits. The two
remaining occurrences in `FORK_NOTES.md` are in historical/explanatory prose ("defaults moved
from `config.yaml`…") — intentional. ✓

---

## Issues

### Major

**M1 — Undocumented prompt rewrite in `pageindex/utils.py:654-672`**

`generate_node_summary`'s prompt was rewritten outside any plan task. The change:
- Adds a forced opener (`Begin with: "In this section you will find..."`) that constrains every
  summary the library ever produces.
- Restructures the instructions with `###` section headers.
- Removes the original prohibition on beginning with "This document is..." or "This section
  describes...", replacing it with a specific fixed phrase instead.

This is a behavioral change to a core library function. It is not in design.md, not in any plan
task, and not in `journals/engineer.md`. There is no regression test for summary content, so the
change ships unverified. It also may not be appropriate for all consumers of the library.

**Required action before PR:** either (a) remove the prompt change and open a separate cycle
for it with a design decision (is the forced opener intentional?), or (b) document it in the
journal, add a comment explaining the rationale, and confirm with the owner that the forced
opener is acceptable for all consumers.

### Minor

**m1 — `logging` import position inconsistency**

The diff shows `import logging` moved from its former position (after `load_dotenv()`) to line 1.
The reorganization is correct and the import is present. No functional issue, but the diff reads
as "removed" without context, which caused review complexity. No action needed — flagged for
awareness.

**m2 — `flash/api.py:113` calls `ConfigLoader().load()` with no args**

This is a pre-existing call site, not modified by this cycle. It is compatible with the new
`defaults=None` signature. Flagged only to confirm it was checked.

---

## Summary

The three-cause bug fix (causes #1, #2, #3) is complete, correct, and thin. Key parity is
exact, fork-thinness constraint holds across all five ConfigLoader callers, the new `build_tree`
routing via `ConfigLoader + page_index_main` is sound, and `_log_provider_once` handles all edge
cases safely. The single blocker is an undocumented prompt rewrite to `generate_node_summary`
that changes library behavior without a design decision or journal entry — resolve that one point
and the PR is ready.

---

## PR Readiness: Likely CTO Questions

These are questions Juan should be able to answer at PR review:

1. **"Why does `summary_model` default to `None` instead of a real model string?"**
   Suggested answer: Because `page_index.py:1263` already falls back to `model` when
   `summary_model` is falsy. A concrete default would force every consumer to explicitly pass
   `summary_model` or risk a wrong-provider call. `None` means "use the same model as
   everything else unless you specifically need a different one."

2. **"What happens if I call `build_tree` with `summary_model=None` explicitly?"**
   Suggested answer: `ConfigLoader().load({'summary_model': None})` merges `None` into the
   config — same result as the default. `page_index_main` sees `opt.summary_model = None` and
   falls back to `opt.model`. No change in behavior.

3. **"Why did the summary prompt change? Was that part of this fix?"**
   This is the question that currently has no good answer — see M1 above.

4. **"Could `_logged_models` ever cause a memory leak?"**
   Suggested answer: It is a module-level set of model-name strings. In practice, a process uses
   one or two distinct model strings; the set stays tiny. Not a concern in normal usage.

5. **"How do we know the `ConfigLoader` callers in `client.py`, `page_index.py`, `flash/api.py`
   still work?"**
   Suggested answer: All five callers use `ConfigLoader()` with no arguments. The new `__init__`
   accepts `defaults=None` as the only param, defaulting to `DEFAULT_CONFIG`. No caller is
   broken. We also verified this via static grep of all call sites.
