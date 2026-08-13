# Design — Fork customizations (packaging + fixes)

**Date:** 2026-08-13
**Branch:** `feature/customizations`
**Author:** Juan (owner) + WaLead (orchestrator)
**Status:** DRAFT — awaiting approval

---

## 1. Problem statement

`PageIndexNF` is a thin fork of `VectifyAI/PageIndex`, maintained as an **internal, reusable
Python library** for Neural Factory. A downstream backend consumes it via
`uv add "git+https://github.com/NeuralFactoryHub/PageIndexNF.git@feature/customizations"` and
imports the tree-building entry point.

Three upstream gaps block or degrade that use case. All three are documented in `FORK_NOTES.md`
and are addressed together in this cycle:

1. **Not installable as a package.** Upstream ships as a run-script repo (no `pyproject.toml`),
   so `uv add git+...` cannot build it. There is no stable public import surface.
2. **Guaranteed crash on misaligned page numbering** (`offset=None` in
   `add_page_offset_to_toc_json`).
3. **Non-discriminative node summaries** — the upstream `generate_node_summary` prompt describes
   the whole document on every node, in English regardless of source language.

## 2. Scope

**In scope (this cycle):** the three divergences above, on `feature/customizations` only.

**Non-goals (explicit):**
- No changes to `main` (stays a mirror of upstream).
- No domain- or client-specific wording anywhere (repo stays generic — no DUVRI, no
  Jungheinrich, no section names, etc.).
- No deployment / infra. This is a library, not a service: it is distributed, not deployed.
- No persistence inside the library (see §4.1 — the consumer persists).
- No rewrite of upstream logic beyond the minimal patch required per divergence.

## 3. Affected files (reference `project.yml` → service `pageindex`)

| Divergence | File(s) | Anchor |
|---|---|---|
| #1 Packaging | `pyproject.toml` (new), `pageindex/__init__.py`, `requirements.txt` | new + exports |
| #2 offset bug | `pageindex/page_index.py` | `add_page_offset_to_toc_json` (~L506) |
| #3 summary prompt | `pageindex/utils.py` | `generate_node_summary` (L637) |

No cross-service dependencies (single-service library). The only integration contract is the
**public import surface** (`project.yml` → `pageindex-public-api`).

---

## 4. Design per divergence

### 4.1 Divergence #1 — Packaging + `build_tree` (the integration contract)

**Goal:** make the fork `uv add`-installable and expose ONE stable public entry point.

**Public API — agreed contract:**

```python
from pageindex import build_tree

tree = build_tree(source, ...)   # source: bytes | str | Path
```

- **Single public entry point:** `build_tree`. This is the stability seam that insulates the
  backend from upstream renames/signature churn.
- **`source: bytes | str | Path`.** If `bytes`, resolve internally (BytesIO, or an internal temp
  file if a parsing lib requires a real path) — **implementation detail, not exposed**.
- **Returns the tree** (Python dict as produced by the core). **Does NOT persist** — the consuming
  backend decides what to do with it (store in Mongo, feed retrieval, etc.). The CLI's
  `./results/*.json` writing stays CLI-only.
- **No domain wording**, generic signature.

**Design:** `build_tree` is a thin public wrapper over the existing core `page_index_main` /
`page_index` (`page_index.py`). It normalizes `source` → the input type the core accepts
(path or `BytesIO`), then delegates. `run_pageindex.py` (CLI) and `build_tree` (library) become
**sibling adapters over the same core** — the CLI keeps its argparse + file-writing behavior
untouched.

**Packaging specifics:**
- Add minimal `pyproject.toml` (build backend + metadata + dependencies mirroring
  `requirements.txt`).
- **Add `boto3`** to dependencies — LiteLLM→Bedrock needs it and it is missing upstream.
- `pageindex/__init__.py` exposes `build_tree` as a public import.
- Must not break the CI matrix (py3.10/3.13, with/without agent frameworks). Note `tests.yml`
  already anticipates that `pyproject` "does not exist on all branches" — packaging lands here.

### 4.2 Divergence #2 — Patch `offset=None` crash

**Root cause:** `calculate_page_offset` returns `None` when it finds no matching page pairs
(`page_index.py:496`). That `None` flows into `add_page_offset_to_toc_json`, which computes
`data[i]['page'] + offset` → `TypeError: unsupported operand type(s) for +: 'int' and 'NoneType'`.
This crashes tree-building on any document whose logical page numbering is misaligned (e.g.
numbering starting at "2").

**Fix:** default `offset` to `0` when `None` (identity offset — physical index equals logical
page). Minimal and behavior-preserving for the aligned case (`0` offset changes nothing).

### 4.3 Divergence #3 — Node-distinctive summaries

**Root cause:** the upstream prompt (`utils.py:638`) asks for "a description of the partial
document", so every node's summary re-describes the whole document with a meta-preamble, buries
node-specific content, and is emitted in English regardless of source language. Summaries become
non-discriminative — useless for the one job they have: *deciding which node to open*.

**Fix:** replace the prompt so the summary is **extractive, node-specific, self-contained, and in
the same language as the section text**, with no meta-preamble. Proposed prompt (from FORK_NOTES):

> You are given one section of a larger document. Write a summary of THIS section only. State
> directly the specific topics, entities, values, and details it contains. Do NOT describe the
> document as a whole, do NOT restate its purpose or legal framework, and do NOT begin with
> phrases like "This document is..." or "This section describes...". Start with the content
> itself. Write in the same language as the section text.

Preserve the existing `SUMMARY_RAW_TEXT_TOKENS` behavior (tiny leaves reuse raw text as summary).

---

## 5. Acceptance criteria

**#1 Packaging**
- [ ] `pip install .` / `uv add git+...@feature/customizations` succeeds from a clean env.
- [ ] `from pageindex import build_tree` works after install.
- [ ] `build_tree(bytes)`, `build_tree(str_path)`, `build_tree(Path)` all produce a tree.
- [ ] `build_tree` returns the tree object and writes nothing to disk.
- [ ] `boto3` is declared as a dependency.
- [ ] CI matrix (py3.10/3.13, with/without frameworks) stays green.

**#2 offset**
- [ ] A document with misaligned numbering (offset resolves to `None`) builds a tree without
      crashing.
- [ ] Aligned documents produce identical output to before the patch (no regression).

**#3 summaries**
- [ ] Node summaries contain node-specific content, no whole-document meta-preamble.
- [ ] Summary language matches the section text language.
- [ ] Tiny leaves still reuse raw text (`SUMMARY_RAW_TEXT_TOKENS` behavior intact).

## 6. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Packaging breaks the CI matrix on branches without `pyproject` | `tests.yml` already installs from `requirements.txt`, not the package; verify no import-path regressions |
| `build_tree` bytes→path handling leaks temp files | Prefer `BytesIO` in-memory; if a temp file is unavoidable, use a context manager and clean up |
| Summary prompt change alters output shape expected by tests | Check `tests/` for summary assertions before changing the prompt |
| Divergence widens the fork (harder upstream merges) | Keep each patch minimal and localized; document every change in `FORK_NOTES.md` |

## 7. Open questions (to resolve in PLAN / engineer investigation)

1. ~~Second summary generator?~~ **RESOLVED (2026-08-13):** two separate summary paths exist —
   `generate_node_summary` (utils.py:638, OSS path) and `summarize_tree` (utils.py:741, flash path,
   with its own already-distinct prompts at L772/L799). Divergence #3 touches **only**
   `generate_node_summary`. The flash path is out of scope.
2. **`pyproject` build backend choice** (setuptools vs hatchling) — pick the lightest that
   packages a flat `pageindex/` package + its `flash/` subpackage. First-use checkpoint applies if
   the tool is new to Juan.
3. **Version/metadata** — package name, version, Python requires-python floor (CI floor is 3.10).

---

## 8. Data lifecycle note (architecture)

The library only **produces** the tree; it does not **read/update/delete/persist** it. Those
belong to the consuming backend. This is deliberate: a library that imposed persistence would
dictate the consumer's storage. The full CRUD + persistence lifecycle of a tree is the backend's
concern, out of scope here.
