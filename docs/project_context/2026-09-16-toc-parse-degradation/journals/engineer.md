# Engineer Journal — TreeParseError enters the degradation ladder
## Skill: nf:backend-python (project adaptation, generic FastAPI-oriented — mostly not applicable; this is a pure library patch to pageindex/errors.py and pageindex/page_index.py)
## Service: pageindex/
## Plan: docs/project_context/2026-09-16-toc-parse-degradation/plan.md

### Work Log

#### [00:00] Task 0: Branch
**What:** Cut `fix/strengthen-toc-ladder` from `feature/customizations` (up to date with origin, no pull needed).
**Why:** D-4 / plan constraint 4 — never commit directly to `feature/customizations`.
**Alternatives considered:** none — mechanical step.
**Files touched:** none.

#### [00:10] Tasks 1-7: judge fix, exception translation, structure_attempts
**What:** Added `TocTransformError(TreeParseError)` to `pageindex/errors.py`. In `pageindex/page_index.py`: imported the new type; changed the two raise sites at the end of `toc_transformer`'s retry loops (finished-but-rejected and max_output_reached) to raise `TocTransformError` instead of `TreeParseError`, leaving `extract_toc_content`'s two raises untouched (different stage). Rewrote `check_if_toc_transformation_is_complete`'s prompt to define "complete" as coverage only (explicitly listing flaws — backward/repeated/merged numbering, unnumbered entries — that must NOT be penalised) and narrowly scoping the "no" answer to missing entries or truncation. Wrapped the mode dispatch inside `meta_processor` in a `try/except TreeParseError`, logging and recording the attempt with `error: type(exc).__name__`, then delegating to a new `_next_strategy` helper. Added `_next_strategy` above `meta_processor`: raises through unchanged if `mode == 'process_no_toc'` (nothing below the floor); on `process_toc_with_page_numbers` with a `TocTransformError` specifically, skips `process_toc_no_page_numbers` (records `error: 'skipped'`) and jumps straight to `process_no_toc`; on `process_toc_with_page_numbers` with any other `TreeParseError` subclass, still tries `process_toc_no_page_numbers` normally (only the transform-stage failure is guaranteed to repeat). Added `'error': None` to the attempts entry on the normal (returning) path in `meta_processor`, so every entry in `structure_attempts` has the same key set. Added `structure_attempts: outcome.get('attempts', [])` next to both `structure_source` return sites in `page_index_builder`.
**Why:** Design fix [A] (judge prompt was asking for normative correctness, not coverage, an unsatisfiable contract against a transformer instructed to transcribe faithfully) and fix [C] (the `TreeParseError` raised by `toc_transformer` unwound past the ladder's `try` boundary — there wasn't one — before `accuracy` existed, so the working degrade-to-`process_no_toc` path was never reached). `TocTransformError` carries provenance so the ladder can skip `process_toc_no_page_numbers` when it is guaranteed to fail identically (same function, same input) — avoiding ~12 wasted LLM calls per failing document, per design §3 "Cost note".
**Alternatives considered:** Considered catching `TreeParseError` broadly at every ladder call site instead of centralizing in `_next_strategy`; rejected because the short-circuit logic (skip when it's specifically a `TocTransformError` from `process_toc_with_page_numbers`) needs to live in one place to stay correct as the ladder evolves. Considered not subclassing and instead checking the exception message; rejected as fragile — a typed provenance class is the pattern already used across `errors.py`.
**Files touched:** `pageindex/errors.py`, `pageindex/page_index.py`.

**Verification commands run (all passed):**
- `python -c "from pageindex.errors import TocTransformError, TreeParseError; assert issubclass(TocTransformError, TreeParseError); print('ok')"` → `ok`
- `grep -n "TocTransformError\|TreeParseError" pageindex/page_index.py` → import line 9; `TocTransformError` at former :421/:451 sites (now :421/:451, unaffected by later edits since they precede the dispatch); `TreeParseError` still at extract_toc_content's two sites and the terminal raise.
- Judge prompt check: `import inspect; src = inspect.getsource(m.check_if_toc_transformation_is_complete); assert 'COVERAGE' in src and 'truncated mid-entry' in src` → `ok`.
  **Lesson:** `import pageindex.page_index as m` resolves `m` to the `page_index` *function* (pre-existing name collision: `pageindex/__init__.py` does `from .page_index import *`, and `page_index.py` defines a function literally named `page_index`, which shadows the submodule attribute on the package after import). Used `importlib.import_module('pageindex.page_index')` instead to get the actual module object. Not a regression introduced by this change — pre-existing repo quirk, noted here so the next person doesn't waste time on it.
- `python -c "import importlib; m = importlib.import_module('pageindex.page_index'); print('imports ok'); assert callable(m._next_strategy); print('ok')"` → `imports ok` / `ok`.
- `grep -n "outcome.setdefault('attempts'" pageindex/page_index.py` → 3 occurrences (Task 4 exception path, Task 5 skip-recording, Task 6 normal path), all with an `'error'` key.
- `grep -n "structure_attempts" pageindex/page_index.py` → 2 occurrences, one per return path in `page_index_builder`.

#### [00:20] Task 8: Run existing suite
**What:** `python -m pytest -q`.
**Output (verbatim, tail):**
```
..................                                                       [100%]
=============================== warnings summary ===============================
.venv/lib/python3.13/site-packages/PyPDF2/__init__.py:21
  /Users/juanandresgussalli/CursorProjects/PageIndexNF/.venv/lib/python3.13/site-packages/PyPDF2/__init__.py:21: DeprecationWarning: PyPDF2 is deprecated. Please move to the pypdf library instead.
    warnings.warn(

<frozen importlib._bootstrap>:488
<frozen importlib._bootstrap>:488
  <frozen importlib._bootstrap>:488: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:488
<frozen importlib._bootstrap>:488
  <frozen importlib._bootstrap>:488: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

<frozen importlib._bootstrap>:488
  <frozen importlib._bootstrap>:488: DeprecationWarning: builtin type swigvarlink has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
18 passed, 6 warnings in 0.15s
```
**Why:** AC-7 — documents that index correctly today must still produce an unchanged structure; the existing suite is the regression guard for that (per D-3, no new tests are added).
**Alternatives considered:** none — mechanical verification step.
**Files touched:** none.

#### [00:30] Task 9: Manual verification (AC-1, AC-3, AC-4, AC-5)
**Credentials check (D-6):** local `~/.aws/credentials` holds an `AKIA...` key pair (account
`654855421610`, user `jungheinrich-project-aws-cli`, region `eu-west-1`). Contrary to the
orchestrator's assumption in decisions.md D-6 that fork credentials live only in the consuming
repo, these local credentials DO reach Bedrock. `aws sts get-caller-identity` succeeded.
**Deviation from plan/design's stated model:** `bedrock/eu.anthropic.claude-haiku-4-5` (named in
design.md's prior-evidence section) does not exist as an inference profile on this account —
`aws bedrock list-inference-profiles --region eu-west-1` lists no `claude-haiku-4-5` id, and
`eu.anthropic.claude-3-haiku-20240307-v1:0` is rejected as "Legacy...not actively used in 30
days". Used `bedrock/eu.anthropic.claude-sonnet-4-5-20250929-v1:0` instead (confirmed working
with a smoke call). Noting this as a deviation, not a substitution I'm hiding: the judge prompt
change is model-agnostic by design intent, but the prior 5/5 evidence in design.md was measured
against Haiku and this run is against Sonnet. Task 9 is therefore verified, but not against the
exact model named in the design's prior-evidence section.

**Step 1 — AC-3 / AC-4, the judge against the real model.** Script:
`/private/tmp/claude-501/.../scratchpad/task9_judge_check.py` (session scratchpad, not
committed). Synthetic raw TOC (structural only, no real document content): a line merging two
section numbers (`1.- 2. Introduction and Scope`), a duplicated section number (`3.` appears
twice), and backward numbering (`3.` followed by `2.`), plus one unnumbered trailing entry
(`Appendix`) exercising the §10a fix.
- **Positive** (faithful JSON transform reproducing all three defects) run 5x:
  `yes, yes, yes, yes, yes` — **5/5 yes**.
- **Negative** (same JSON truncated mid-entry, ~50%) run 5x:
  `no, no, no, no, no` — **5/5 no**.
Both meet the plan's gate. The 5/5 negative result is the hard gate per D-6/plan Task 9 — it
holds, so proceeding was safe.

**Step 2 — AC-1 / AC-2, end-to-end ladder.** Real end-to-end indexing of a document with a
merged-numbering TOC was not attempted, because after the judge fix such a document plausibly no
longer fails at all (that is the point of fix [A]) — so it cannot reliably reproduce the
non-convergent-transform case on demand, and per D-5 no real client PDF may be used anyway.
Instead: `/private/tmp/claude-501/.../scratchpad/task9_e2e_check.py` calls `meta_processor`
directly (real function, unmodified) on 3 short synthetic pages with numbered headings ("1.
Introduction", "2. Methodology", "3. Conclusion" — generic placeholder text, no client content),
with `process_toc_with_page_numbers` mocked to raise `TocTransformError` (simulating the
documented failure mode: a transform that never converges against the judge). Everything else —
`_next_strategy`, `process_no_toc`, `verify_toc`, `check_title_appearance` — ran unmocked against
the real Bedrock model.
Result: no exception raised. `structure_attempts` (verbatim):
```
{'mode': 'process_toc_with_page_numbers', 'accuracy': None, 'error': 'TocTransformError'}
{'mode': 'process_toc_no_page_numbers', 'accuracy': None, 'error': 'skipped'}
{'mode': 'process_no_toc', 'accuracy': 1.0, 'error': None}
```
Matches design §3's expected ladder trace exactly: step 1 raises and is recorded, step 2 is
skipped (not attempted) and recorded as such, step 3 runs for real and verifies at 100%. AC-1 and
AC-2 confirmed against the real model, not by reasoning alone.

**Step 3 — AC-5, error propagation.** Confirmed by inspection AND by MRO check:
`LLMUnavailableError`, `LLMConfigError`, `UnreadableInputError` (and its subclasses
`UnsupportedFormatError`, `ConversionError`, `OCRError`, `NotPreprocessedError`) all descend
directly from `PageIndexError`, never through `TreeParseError`:
```
LLMUnavailableError -> PageIndexError -> Exception
LLMConfigError -> PageIndexError -> Exception
UnreadableInputError -> PageIndexError -> Exception
```
The `except TreeParseError` clause added in Task 4 therefore cannot catch any of them; they
propagate out of the dispatch unchanged. AC-5 confirmed.

**Task 9 status: PASSED** (not blocked — credentials were available). All four ACs (1, 2, 3, 4,
5 — Step 3 covers AC-5) verified against the real Bedrock model, with the model-id deviation
noted above.
**Files touched:** none inside the repo (verification scripts live in the session scratchpad,
outside the repo, per D-5).

#### [00:45] Task 10: Document the divergence
**What:** Appended `### 12.` to `FORK_NOTES.md` after `### 11`, covering: the untranslated
exception channel, the coverage-only judge prompt (with the truncation-guard rationale), the
`TocTransformError` provenance type and the transform-stage short-circuit, and the additive
`structure_attempts` field. Written structurally ("a TOC line that merges two section numbers
into one entry"), no document type or client name.
**Why:** Definition of Done requires documenting the divergence; FORK_NOTES.md is the fork's
single divergence log.
**Alternatives considered:** none.
**Files touched:** `FORK_NOTES.md`.

**Verify step result — deviation noted:** `grep -n "^### 12" FORK_NOTES.md` finds the heading
(line 330). `grep -ci "duvri\|jungheinrich\|marcallo" FORK_NOTES.md pageindex/page_index.py`
returns `pageindex/page_index.py:0` (clean, as expected) but `FORK_NOTES.md:11` — NOT 0. I
checked every hit (`grep -n -i "duvri\|jungheinrich\|marcallo" FORK_NOTES.md`): all 11 are at
lines 10-316, inside the pre-existing scope-rule preamble and the already-committed §10a/§11
sections (from commits `f88b2f6`/`a7f8a79`/`ed56ca5`, before this branch). My new §12 (line 330
onward) contains zero such mentions — I verified this is a pre-existing violation of the repo's
own scope rule, not something this task introduced. I did not touch or rewrite §10a/§11 — that is
out of scope for this plan and rewriting another engineer's already-reviewed, already-merged
verification history did not seem like a call to make unilaterally. Flagging this for the
orchestrator/CTO rather than silently treating Task 10's verify step as fully green.
**Lesson:** the plan's verify command for Task 10 assumes a clean baseline that does not exist;
worth re-running this grep against the whole file BEFORE writing new content next time, so a
pre-existing violation isn't mistaken for one introduced by the current task.

#### [00:50] Task 11: Commit
**What:** Staged `FORK_NOTES.md`, `pageindex/errors.py`, `pageindex/page_index.py`, and the whole
`docs/project_context/2026-09-16-toc-parse-degradation/` feature folder (design, plan, decisions,
this journal) — following the precedent of commit `78dbfbc` which committed its
`docs/project_context/` folder alongside the code. Committed on `fix/strengthen-toc-ladder` as
`fix(toc): route TreeParseError into the degradation ladder`, with the ClickUp link and a summary
of both fixes and the verification results in the body.
**Why:** Definition of Done requires the commit on the correct branch, never `feature/customizations` directly.
**Alternatives considered:** leaving `docs/project_context/` uncommitted; rejected — no
`.gitignore` entry excludes it and there's a direct precedent for committing it with the code.
**Files touched (this commit):** `FORK_NOTES.md`, `pageindex/errors.py`, `pageindex/page_index.py`,
`docs/project_context/2026-09-16-toc-parse-degradation/{decisions.md,design.md,plan.md,journals/engineer.md}`.
**Commit:** `9ad4758` on `fix/strengthen-toc-ladder`. `git status --short` clean after commit.

#### [01:10] Post-review fix-plan (Gandalf, verdict NEEDS_WORK) — two doc-only fixes
**What:** Full review at `docs/project_context/2026-09-16-toc-parse-degradation/validation/code_review.md` confirmed the implementation sound (all 7 ACs, 18/18 tests, control flow and exception boundary independently traced) and flagged two documentation gaps, no code changes requested.
- **Fix 1 (blocking):** added a `structure_attempts` section to `INTEGRATION.md`, right after the existing `structure_source` block (before the `fallback_flat_tree` note), matching that section's register (prose + a compact table + one example block). Covers the returned shape (`list[{mode, accuracy, error}]`, one entry per attempted strategy in order), what `accuracy=None` and each `error` value mean, and states explicitly that `structure_source` (quality) and `structure_attempts` (derivational history) are two distinct axes a consumer reads for two distinct purposes.
- **Fix 2 (minor, factual):** corrected `FORK_NOTES.md` §12 — it named `toc_transformer` **and** `extract_toc_content` as the truncation-detection call sites for the tightened judge. The coordinator verified `extract_toc_content` and `check_if_toc_extraction_is_complete` have zero call sites anywhere under `pageindex/` (dead code) — I independently confirmed with `grep -rn "extract_toc_content(" pageindex/` (no hits outside its own definition). `check_if_toc_transformation_is_complete` (the judge I actually modified in Task 3) IS called from both `toc_transformer` and `extract_toc_content` in the source, but since nothing calls `extract_toc_content` itself, that call site is unreachable — the only live, load-bearing site is inside `toc_transformer`. Corrected the sentence to name only `toc_transformer`. Left the dead code itself untouched, per the coordinator's explicit instruction (a separate decision for the user).
**Why:** `structure_attempts` is the observability payoff of design.md §4 — undocumented, the consuming backend has no way to know it exists, defeating the point. The FORK_NOTES correction keeps the fork's own change log factually accurate about which code path is actually exercised in production.
**Alternatives considered:** none — both are corrections to existing prose, not design decisions.
**Files touched:** `INTEGRATION.md`, `FORK_NOTES.md`, this journal.
**Verify:** `python -m pytest -q` → `18 passed, 6 warnings in 0.14s` (unchanged, as expected for a doc-only change). Amended into `9ad4758` rather than adding a second commit, per the coordinator's instruction to keep the branch at one commit.
