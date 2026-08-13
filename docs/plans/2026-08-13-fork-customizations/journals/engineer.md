# Engineer Journal — Fork Customizations (packaging + fixes)
## Skill: executing-plans + backend-python
## Service: pageindex/
## Plan: docs/plans/2026-08-13-fork-customizations/plan.md

### Work Log

#### [Start] Pre-flight inspection
**What:** Read profile.md, CLAUDE.md, design.md, plan.md, and key source files before touching anything.
**Why:** The plan modifies three separate files across two concerns (packaging + two patches). Reading first prevents cargo-cult edits — I need to know the exact current state of each file to write a correct diff.
**Files inspected:** `pageindex/__init__.py`, `pageindex/page_index.py` (L490–512), `pageindex/utils.py` (L630–658), `requirements.txt`, `FORK_NOTES.md`.
**Observations:**
- `add_page_offset_to_toc_json` at L506 has no guard — `None + int` would crash immediately, confirming the design root cause.
- `generate_node_summary` at L637 uses the old prompt verbatim, in English only, with no language instruction.
- `requirements.txt` lists 8 deps, all pinned except `regex`. `boto3` is absent.
- `__init__.py` does `from .page_index import *` — we will append one clean named import, not another wildcard.

#### [T1] Task 1: pyproject.toml
**What:** Created `pyproject.toml` with setuptools build backend, name `pageindexnf`, version `0.1.0`, requires-python `>=3.10`, all deps from requirements.txt plus `boto3` (unpinned). `[tool.setuptools.packages.find]` with `include = ["pageindex*"]` captures `pageindex` and `pageindex.flash`.
**Why:** setuptools was chosen over hatchling because it requires no extra install beyond the standard build toolchain and handles the `packages.find` pattern cleanly for a flat src layout. Pinning `boto3` was skipped per the confirmed decisions — upstream pins all other deps, so this is a known inconsistency to resolve later.
**Alternatives considered:** hatchling (more modern but adds a dep); flit (too minimal, no sub-package support without config). setuptools is the safest for a fork that may receive upstream merges.
**Files touched:** `pyproject.toml` (created)
**Verification:** `python -m build --wheel` produced `dist/pageindexnf-0.1.0-py3-none-any.whl` with no errors.
**Deviation:** The system Python is 3.14, which caused the built-in `python -m pip install --upgrade build` to block (PEP 668 externally managed). Created `.venv` with system Python 3.14 first for the wheel build, then `.venv313` with `python3.13` for the full install+import verification (litellm==1.84.0 requires <3.14). The pyproject.toml content is unchanged — this is an environment discrepancy, not a code issue.

#### [T2] Task 2: build_tree entry point
**What:** Created `pageindex/build_tree.py` with `build_tree(source, **kwargs)` that normalizes bytes→BytesIO, Path→str, str→str and delegates to `page_index()`. Added `from .build_tree import build_tree` to `pageindex/__init__.py`.
**Why:** Isolated in its own module so upstream merges to `page_index.py` never conflict with the fork's public API. `BytesIO` handles bytes in-memory (no temp file leaks). `page_index()` already accepts both a path string and a BytesIO object, so the wrapper is a pure normalization layer with no logic duplication.
**Alternatives considered:** patching `page_index.py` directly — rejected because it widens the diff surface and conflicts on every upstream merge. Putting `build_tree` directly in `__init__.py` — rejected because it mixes the public API with import machinery.
**Files touched:** `pageindex/build_tree.py` (created), `pageindex/__init__.py` (1 line added)
**Verification:** `.venv313/bin/python -c "from pageindex import build_tree; print(build_tree)"` → `<function build_tree at 0x107e8d300>`.

#### [T3] Task 3: Fix offset=None crash
**What:** Added `if offset is None: offset = 0` guard at the top of `add_page_offset_to_toc_json` in `pageindex/page_index.py` (L506).
**Why:** `calculate_page_offset` returns `None` when its `differences` list is empty (no matching page pairs found). The downstream arithmetic `data[i]['page'] + offset` then raises `TypeError`. Zero is the correct identity offset: it leaves physical_index equal to the logical page number, which is the correct fallback when alignment cannot be determined.
**Alternatives considered:** returning early and leaving `page` keys intact — rejected because callers downstream expect `physical_index`, not `page`. Raising a descriptive error — rejected because the design says "behavior-preserving for the aligned case" and the zero-offset assumption is safe.
**Files touched:** `pageindex/page_index.py` (3 lines added inside function)
**Verification:** `.venv313/bin/python -c "...add_page_offset_to_toc_json([{'page': 5}], None)"` → `[{'physical_index': 5}]`.

#### [T4] Task 4: Node-distinctive summary prompt
**What:** Replaced the upstream prompt in `generate_node_summary` (utils.py) with the extractive, language-preserving prompt from the design/FORK_NOTES.
**Why:** The upstream prompt ("generate a description of the partial document about what are main points covered") causes the LLM to write a document-level preamble on every node, making summaries nearly identical across nodes and always in English. The new prompt constrains the LLM to the current section only, forbids meta-preambles explicitly, and instructs it to match the source language — making summaries discriminative for retrieval.
**Alternatives considered:** adding a language detection step — rejected as over-engineering; instructing the LLM to match the section language is sufficient and avoids an extra API call. Preserving the old behavior behind a flag — rejected because the design says "replace", not "add an option", and the library has no config surface for this yet.
**Files touched:** `pageindex/utils.py` (prompt string replaced, function signature unchanged)
**Verification:** `.venv313/bin/python -c "from pageindex.utils import generate_node_summary; print('ok')"` → `ok`.

#### [T5] Task 5: Regression check + FORK_NOTES
**What:** Installed pytest in `.venv313` and ran the full test suite. Flipped all three `Status: TODO` entries in `FORK_NOTES.md` to `Status: DONE`.
**Why:** The test suite is the safety net against unintended regressions. Updating FORK_NOTES closes the documentation loop — the file is the single source of truth for fork divergences.
**Files touched:** `FORK_NOTES.md` (3 status lines updated)
**Verification:** `18 passed, 6 warnings in 0.08s`. The 6 warnings are pre-existing deprecation notices from PyPDF2 and Swig; none are new.
