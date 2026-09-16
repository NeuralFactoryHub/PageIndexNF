# TreeParseError enters the degradation ladder — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: use the nf:executing-plans skill to implement this plan task-by-task.

**Goal:** A document whose TOC transform never converges must degrade through the existing
strategy ladder instead of raising, and the run must report how it got there.

**Architecture:** `meta_processor` (`pageindex/page_index.py`) already degrades
`process_toc_with_page_numbers -> process_toc_no_page_numbers -> process_no_toc`, gated on
`accuracy: float | None`. `toc_transformer` reports failure by raising `TreeParseError`, which
unwinds past the ungarded dispatch at `page_index.py:1187-1192` before `accuracy` exists. This
plan (a) tightens the judge prompt that causes the spurious failure, (b) translates the exception
into the ladder's own signal, and (c) surfaces the per-strategy trace in the returned dict.

**Services touched:** `pageindex` (`pageindex/`, `python-library`, skill: `nf:backend-python`).
Single service; no cross-service contract changes.

**Design:** `docs/project_context/2026-09-16-toc-parse-degradation/design.md`
**Work item:** https://app.clickup.com/t/123y1w8cjwa

**Acceptance criteria** (verbatim from design §6):

- **AC-1** A document whose TOC transform never converges is indexed instead of raising; the run reaches `process_no_toc`.
- **AC-2** `process_toc_no_page_numbers` is skipped — not attempted — when step 1 failed inside the transform stage, and the skip is recorded in `structure_attempts`.
- **AC-3** The judge accepts a faithful transform that reproduces broken source numbering.
- **AC-4** The judge still rejects a transform truncated mid-way (regression guard for the `max_output_reached` continuation path).
- **AC-5** `LLMUnavailableError`, `LLMConfigError` and `UnreadableInputError` still propagate out of the dispatch unchanged.
- **AC-6** `page_index_main` returns `structure_attempts` alongside `structure_source`; `structure_source` keeps its three existing values and its current semantics.
- **AC-7** Documents that index correctly today still produce an unchanged structure.

---

## Constraints — read before the first edit

1. **No new tests.** Root `CLAUDE.md`: *"DO NOT write tests unless explicitly requested."*
   Confirmed with the user on 2026-09-16 for this work item. The existing suite must keep
   passing (Task 8); the ACs are verified manually (Task 9) and walked by QA.
2. **The repo is generic.** `FORK_NOTES.md` scope rule: no domain- or client-specific wording in
   code, comments or `FORK_NOTES.md` — no document type names, no client names, no section
   titles from any real document. Describe the defect structurally ("a TOC line merging two
   section numbers"), never by naming the document family it came from.
3. **Comments explain *why*, sparingly.** Root `CLAUDE.md`. Match the density already in
   `page_index.py` around the ladder.
4. **Branch:** `fix/strengthen-toc-ladder`, cut from `feature/customizations`, **never** from
   `main`. Never commit directly to `feature/customizations` (`.claude/SDLC.md` §5 override).
5. **No new dependency.** Everything here is stdlib plus what the module already imports.

---

## Task 0: Branch

**Step 1: Cut the branch**
```bash
git checkout feature/customizations && git pull
git checkout -b fix/strengthen-toc-ladder
```
Expected: `Switched to a new branch 'fix/strengthen-toc-ladder'`

---

## Task 1: Add `TocTransformError` — covers AC-2

The ladder must tell *where* a `TreeParseError` came from: a failure inside the transform stage
makes the next strategy pointless, because it calls the same function with the same input. A
subclass carries that provenance without a new error channel, matching the taxonomy already in
`errors.py`.

**Files:**
- Modify: `pageindex/errors.py:59-61`

**Step 1: Implement**

Replace the final block of `pageindex/errors.py`:

```python
# (c) The model answered but the structure could not be built from the answer.
class TreeParseError(PageIndexError):
    pass


class TocTransformError(TreeParseError):
    """The raw TOC could not be turned into JSON.

    Provenance, not a new failure class. Both TOC-based strategies call `toc_transformer` with
    the same input, so once it has failed for one of them the other cannot succeed; the ladder
    uses this type to skip it instead of paying for a lost cause.
    """
```

**Step 2: Verify**
```bash
python -c "from pageindex.errors import TocTransformError, TreeParseError; assert issubclass(TocTransformError, TreeParseError); print('ok')"
```
Expected: `ok`

---

## Task 2: Raise the new type from `toc_transformer` — covers AC-2

**Files:**
- Modify: `pageindex/page_index.py:9` (import), `:421`, `:451`

**Step 1: Extend the import**

Line 9 currently reads:
```python
from .errors import NotPreprocessedError, TreeParseError
```
Replace with:
```python
from .errors import NotPreprocessedError, TocTransformError, TreeParseError
```

**Step 2: Replace both raise sites inside `toc_transformer`**

At `page_index.py:421` (end of the finished-but-rejected retry loop) and `page_index.py:451`
(end of the `max_output_reached` continuation loop), replace:
```python
        raise TreeParseError('Failed to complete TOC transformation after maximum retries')
```
with:
```python
        raise TocTransformError('Failed to complete TOC transformation after maximum retries')
```

Both sites, identical replacement. Do **not** touch the two raises at `:265` and `:284` — those
belong to `extract_toc_content`, a different stage, and must stay `TreeParseError`.

**Step 3: Verify**
```bash
grep -n "TocTransformError\|TreeParseError" pageindex/page_index.py | head -20
```
Expected: the import on line 9; `TocTransformError` at the two former `:421` / `:451` sites;
`TreeParseError` still at `:265`, `:284` and in the terminal raise of `meta_processor`.

---

## Task 3: Define "complete" for the judge — covers AC-3, AC-4

`check_if_toc_transformation_is_complete` never defines *complete*, so the model supplies the
normative reading ("well formed, correctly numbered") instead of the coverage reading ("nothing
is missing"). That contradicts `toc_transformer`, which is instructed to transcribe faithfully:
the transform cannot pass without falsifying the source.

**Files:**
- Modify: `pageindex/page_index.py:222-232`

**Step 1: Implement**

Replace the prompt literal inside `check_if_toc_transformation_is_complete` (keep the function
signature, the `_secure_doc_text` calls, the `llm_completion` call and the return untouched):

```python
def check_if_toc_transformation_is_complete(content, toc, model=None):
    prompt = f"""
    You are given a raw table of contents and a cleaned JSON version of it.
    Your only job is to check COVERAGE: whether every entry of the raw table of contents is
    present in the cleaned version, and whether the cleaned version ends where the raw one ends.

    Answer "yes" when the cleaned version covers the raw one, even if the raw table of contents
    is itself flawed. Reproducing a flaw of the source is CORRECT behaviour, not an error.
    Flaws you must NOT penalise:
      - numbering that repeats, skips, or runs backwards
      - several section numbers merged into one line
      - entries with no number at all
      - inconsistent depth or indentation

    Answer "no" ONLY when the cleaned version fails to cover the raw one, that is:
      - entries present in the raw text are missing from the cleaned version, or
      - the cleaned version is cut off before the end of the raw text (truncated mid-entry).

    Reply format:
    {{
        "thinking": <which raw entries you checked, and whether any is missing or the output is cut off>
        "completed": "yes" or "no"
    }}
    Directly return the final JSON structure. Do not output anything else."""
```

**Why the "no" branch is spelled out narrowly:** this judge is load-bearing twice. Besides gating
the transform it is the signal that detects a response truncated by output limit, which drives
the `max_output_reached` continuation path in `toc_transformer` and `extract_toc_content`.
Loosening it into "always yes" would silently break continuation.

**Step 2: Verify**
```bash
python -c "import pageindex.page_index as m; s=m.check_if_toc_transformation_is_complete.__doc__ or ''; import inspect; src=inspect.getsource(m.check_if_toc_transformation_is_complete); assert 'COVERAGE' in src and 'truncated mid-entry' in src; print('ok')"
```
Expected: `ok`

**Note:** the empirical validation of this prompt is Task 9, not an automated test.

---

## Task 4: Catch the exception at the dispatch — covers AC-1, AC-2, AC-5

**Files:**
- Modify: `pageindex/page_index.py:1187-1192`

**Step 1: Implement**

Replace the dispatch block:

```python
    if mode == 'process_toc_with_page_numbers':
        toc_with_page_number = process_toc_with_page_numbers(toc_content, toc_page_list, page_list, toc_check_page_num=opt.toc_check_page_num, model=opt.model, logger=logger)
    elif mode == 'process_toc_no_page_numbers':
        toc_with_page_number = process_toc_no_page_numbers(toc_content, toc_page_list, page_list, model=opt.model, logger=logger)
    else:
        toc_with_page_number = process_no_toc(page_list, start_index=start_index, model=opt.model, logger=logger)
```

with:

```python
    # A strategy that raises is a strategy that did not verify. The ladder below already knows how
    # to answer that — `accuracy is None` — but only for strategies that return; an exception
    # unwinds past it and kills the document although a working fallback sits two lines down.
    # Only TreeParseError is translated: an unavailable or misconfigured model is not evidence
    # about the document, and degrading on it would freeze a transient fault into a poor index.
    try:
        if mode == 'process_toc_with_page_numbers':
            toc_with_page_number = process_toc_with_page_numbers(toc_content, toc_page_list, page_list, toc_check_page_num=opt.toc_check_page_num, model=opt.model, logger=logger)
        elif mode == 'process_toc_no_page_numbers':
            toc_with_page_number = process_toc_no_page_numbers(toc_content, toc_page_list, page_list, model=opt.model, logger=logger)
        else:
            toc_with_page_number = process_no_toc(page_list, start_index=start_index, model=opt.model, logger=logger)
    except TreeParseError as exc:
        logger.info({'mode': mode, 'accuracy': None, 'error': type(exc).__name__, 'detail': str(exc)})
        outcome.setdefault('attempts', []).append(
            {'mode': mode, 'accuracy': None, 'error': type(exc).__name__}
        )
        return await _next_strategy(
            exc, page_list, mode=mode, toc_content=toc_content, toc_page_list=toc_page_list,
            start_index=start_index, opt=opt, logger=logger, outcome=outcome,
        )
```

**Step 2: Verify**
```bash
python -c "import pageindex.page_index; print('imports ok')"
```
Expected: `imports ok` (`_next_strategy` is added in Task 5; run this verification after Task 5
if the import fails on the missing name).

---

## Task 5: Implement `_next_strategy` with the short-circuit — covers AC-1, AC-2

Both TOC-based strategies call `toc_transformer` as their first statement with the same
`toc_content`. The failure is deterministic, so once the transform stage has failed for
`process_toc_with_page_numbers`, running `process_toc_no_page_numbers` is a guaranteed loss of
~12 further LLM calls. Skip it, but record the skip so the trace stays honest.

**Files:**
- Modify: `pageindex/page_index.py` — insert immediately **above** `async def meta_processor`
  (currently line 1175)

**Step 1: Implement**

```python
async def _next_strategy(exc, page_list, mode=None, toc_content=None, toc_page_list=None,
                         start_index=1, opt=None, logger=None, outcome=None):
    """Resume the ladder one step below `mode` after it raised.

    A TocTransformError skips the remaining TOC-based strategy: it calls `toc_transformer` with
    the same input, so it would fail identically after another round of model calls. The skip is
    still recorded, so a reader of `structure_attempts` does not mistake it for a strategy that
    was never reachable.
    """
    if mode == 'process_no_toc':
        # The floor strategy raised; there is nothing below it to degrade to.
        raise exc

    if mode == 'process_toc_with_page_numbers' and not isinstance(exc, TocTransformError):
        return await meta_processor(
            page_list, mode='process_toc_no_page_numbers', toc_content=toc_content,
            toc_page_list=toc_page_list, start_index=start_index, opt=opt, logger=logger,
            outcome=outcome)

    if mode == 'process_toc_with_page_numbers':
        logger.info({'mode': 'process_toc_no_page_numbers', 'accuracy': None, 'error': 'skipped'})
        outcome.setdefault('attempts', []).append(
            {'mode': 'process_toc_no_page_numbers', 'accuracy': None, 'error': 'skipped'}
        )

    return await meta_processor(
        page_list, mode='process_no_toc', start_index=start_index, opt=opt, logger=logger,
        outcome=outcome)
```

**Step 2: Verify**
```bash
python -c "import pageindex.page_index as m; assert callable(m._next_strategy); print('ok')"
```
Expected: `ok`

---

## Task 6: Record `error: None` on the returning path — covers AC-6

`structure_attempts` must have one shape. Strategies that return need the same key set as those
that raised.

**Files:**
- Modify: `pageindex/page_index.py:1216`

**Step 1: Implement**

Replace:
```python
    outcome.setdefault('attempts', []).append({'mode': mode, 'accuracy': accuracy})
```
with:
```python
    outcome.setdefault('attempts', []).append({'mode': mode, 'accuracy': accuracy, 'error': None})
```

**Step 2: Verify**
```bash
grep -n "outcome.setdefault('attempts'" pageindex/page_index.py
```
Expected: three occurrences (Task 4, Task 5, Task 6), every one carrying an `'error'` key.

---

## Task 7: Emit `structure_attempts` from `page_index_main` — covers AC-6

`structure_source` answers *how much of the result passed verification*. It must keep its three
values and its meaning; the derivational history rides in a separate, additive field, so no
consumer branching on `structure_source == 'verified'` breaks.

**Files:**
- Modify: `pageindex/page_index.py:1424`, `:1430`

**Step 1: Implement**

In both return dicts inside `page_index_builder`, add one key after `structure_source`:

```python
                    'structure_source': _structure_source(outcome),
                    'structure_attempts': outcome.get('attempts', []),
```

and

```python
            'structure_source': _structure_source(outcome),
            'structure_attempts': outcome.get('attempts', []),
        }
```

**Step 2: Verify**
```bash
grep -n "structure_attempts" pageindex/page_index.py
```
Expected: exactly two occurrences, one per return path.

---

## Task 8: Run the existing suite — covers AC-7

**Step 1: Verify**
```bash
python -m pytest -q
```
Expected: exit 0, all existing tests pass, zero new failures.

`lint_cmd` and `build_cmd` are empty in `.claude/project.yml` for this service — nothing to run.

---

## Task 9: Manual verification — covers AC-1, AC-3, AC-4, AC-5

No automated tests are added (see Constraints §1), so these checks are run by hand and their
output is pasted into the engineer journal.

**Step 1: AC-3 / AC-4 — the judge, against the real model**

Using `examples/` (see the end-to-end verification script added in `e120212`) run
`check_if_toc_transformation_is_complete` 5 times per direction:
- **positive:** a faithful JSON transform of a TOC whose numbering is broken (merged, repeated
  or backward section numbers) → expect 5/5 `yes`.
- **negative:** the same JSON truncated at ~50% → expect 5/5 `no`.

Record both counts in the journal. **A negative result below 5/5 blocks the change**: it means
the prompt was loosened past the truncation guard.

**Step 2: AC-1 — end-to-end on a failing document**

Index a document whose TOC merges two section numbers on one line. Expect: no exception; a tree
is returned; `structure_attempts` shows `process_toc_with_page_numbers` with
`error: "TocTransformError"`, `process_toc_no_page_numbers` with `error: "skipped"`, and
`process_no_toc` with a numeric accuracy.

**Step 3: AC-5 — error propagation**

Confirm by reading Task 4's `except TreeParseError` clause that `LLMUnavailableError`,
`LLMConfigError` and `UnreadableInputError` are not subclasses of `TreeParseError`
(`pageindex/errors.py` — they descend from `PageIndexError` on sibling branches) and therefore
still propagate. Note the reasoning in the journal.

---

## Task 10: Document the divergence — Definition of Done

**Files:**
- Modify: `FORK_NOTES.md` (append after `### 11`)

**Step 1: Implement**

Append a `### 12.` section covering: the untranslated exception channel, the coverage-only judge
prompt, the `TocTransformError` provenance type and the transform-stage short-circuit, and the
additive `structure_attempts` field. State that `structure_source` is unchanged.

**Keep it generic** — describe the trigger structurally ("a TOC line merging two section
numbers"), never by document type or client (Constraints §2).

**Step 2: Verify**
```bash
grep -n "^### 12" FORK_NOTES.md && grep -ci "duvri\|jungheinrich\|marcallo" FORK_NOTES.md pageindex/page_index.py
```
Expected: the `### 12` heading exists; the second grep reports `0` for both files.

---

## Task 11: Commit

**Step 1: Commit**

Use `gh-commit`. Conventional commit, concise, scope `toc`:
```
fix(toc): route TreeParseError into the degradation ladder
```
Body: the two fixes ([A] judge prompt, [C] exception translation), the additive
`structure_attempts` field, and the ClickUp task link.

**Step 2: Verify**
```bash
git log --oneline -1 && git status --short
```
Expected: the new commit on `fix/strengthen-toc-ladder`; clean tree.

---

## Definition of Done

- [ ] Tasks 1-7 applied; `python -m pytest -q` green (Task 8)
- [ ] Task 9 manual results pasted into `docs/project_context/2026-09-16-toc-parse-degradation/journals/engineer.md`, including the 5/5 negative truncation count
- [ ] `FORK_NOTES.md` § 12 written and free of domain-specific wording (Task 10)
- [ ] Committed on `fix/strengthen-toc-ladder` (Task 11)
- [ ] No new test files (Constraints §1)
- [ ] No new dependency (Constraints §5)

**Out of scope — the consuming backend.** Bumping the fork pin to the merged revision happens in
that repository, after this branch lands on `feature/customizations`.

---

## Unresolved questions

1. `design.md` names the real trigger documents; `FORK_NOTES.md` §scope forbids domain-specific
   wording in the repo. Keep `docs/project_context/` exempt, or scrub it too?
2. Task 9 needs a document with a merged-numbering TOC. Use the real failing PDF locally without
   committing it, or build a synthetic fixture?
3. Should the backend treat `structure_source: "flat_fallback"` as a failure? Backend decision,
   out of scope here — worth raising with the CTO.
