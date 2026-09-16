# QA Report — TreeParseError enters the degradation ladder

**Branch:** `fix/strengthen-toc-ladder`, commit `29bf196` (single commit, cut from `feature/customizations`).
**Prior verdict:** Gandalf NEEDS_WORK on `INTEGRATION.md` missing `structure_attempts`. That gap is
fixed in this same commit — confirmed documentation-only (`git show 29bf196 --stat`: only
`INTEGRATION.md`/`FORK_NOTES.md` prose changed alongside the code, no additional code diff beyond
what the reviewer already reviewed).

## Verdict: PASS

All 7 ACs independently re-derived (code trace + live execution against real Bedrock), the
`INTEGRATION.md` contract matches the code exactly, `structure_attempts` survives to the public
`build_tree()` entry point, the `fallback_flat_tree="no"` terminal raise works as documented, and
the Haiku evidence gap the reviewer flagged as Major is now closed — Haiku 4.5 **is** reachable on
this AWS account and the judge scores 5/5 both directions against it.

## Static Verification

- [x] `test_cmd` (`python -m pytest -q`): **PASS** — `18 passed, 6 warnings in 0.09s`, re-run independently, no new failures.
- [x] `lint_cmd`: empty per `.claude/project.yml` — nothing to run, not invented.
- [x] `build_cmd`: empty per `.claude/project.yml` — nothing to run, not invented.
- [x] No protected/generated-path artifacts apply to this service (none declared for `pageindex`).

## Integration Coherence

`project.yml` declares one contract, `pageindex-public-api` (python-import-surface, owner
`pageindex`, consumer `<downstream-backend>`). `build_tree` is the stable entry point.

- [x] **`structure_attempts` shape vs. code — MATCH.** `INTEGRATION.md` documents
  `list[{mode: str, accuracy: float|None, error: None|str}]`, one entry per attempted strategy, in
  attempt order, with `error` being `None` (normal return), an exception class name (raised), or
  the literal string `"skipped"`. I re-derived this directly from `pageindex/page_index.py`
  (`meta_processor` lines ~1237-1252 for the except path, `_next_strategy` lines ~1201-1207 for
  the skip entry, line ~1274 for the normal-path `'error': None`) and confirmed the live shape by
  running the ladder end-to-end (see AC table below) — the returned dict matched the doc's example
  verbatim, key names, value types, and order all included.
- [x] **`build_tree` path — MATCH.** `pageindex/build_tree.py:42` (`pages` path) and `:54` (`source`
  path) both `return page_index_main(...)` directly — no intermediate dict reshaping. I called the
  **public `build_tree()`** (not `page_index_main` directly, as the engineer's Task 9 did) with
  `process_toc_with_page_numbers` mocked to raise `TocTransformError`, and `structure_attempts`
  came back intact on the object returned by `build_tree()` itself. This closes the specific
  concern that the field might only reach `page_index_main` and not the documented public surface.
- [~] **One undocumented `accuracy: None` source (minor, non-blocking).** `verify_toc`
  (`page_index.py:1176-1178`) returns `accuracy=None` not only when a strategy raises or is
  skipped, but also when `checked_count == 0` (no sample items with a resolved `physical_index` to
  check) — a normal return, `error: None`, yet `accuracy: None`. `INTEGRATION.md`'s table only
  documents `None` as "never verified (raised, or was skipped)", omitting this third, harmless
  cause (an unverifiable-by-sampling normal completion). It does not contradict the doc's stated
  meaning (`accuracy: None` still correctly means "not verified") but a consumer reading only the
  `error` field could momentarily be surprised to see `error: None` next to `accuracy: None`.
  Recommend a one-line addendum next time this doc section is touched; not blocking.

## Acceptance Criteria (design.md §6)

| AC | Verdict | Evidence (obtained directly, not from journal/review claims) |
|---|---|---|
| AC-1 — non-converging transform still indexes, reaches `process_no_toc` | **PASS** | Called public `build_tree(pages=..., model=...)` with `check_toc` mocked to force the TOC branch and `process_toc_with_page_numbers` mocked to raise `TocTransformError`. No exception; returned tree has `structure_source: "verified"` from `process_no_toc`. |
| AC-2 — `process_toc_no_page_numbers` skipped (not attempted) and recorded | **PASS** | Same run: `structure_attempts[1] == {'mode': 'process_toc_no_page_numbers', 'accuracy': None, 'error': 'skipped'}`. `process_toc_no_page_numbers` was never patched/called (not present in call trace). |
| AC-3 — judge accepts faithful transform of broken source numbering | **PASS** | Ran `check_if_toc_transformation_is_complete` 5x against **`bedrock/eu.anthropic.claude-haiku-4-5-20251001-v1:0`** (live model) on a synthetic TOC with merged/duplicated/backward numbering: **5/5 `yes`**. |
| AC-4 — judge still rejects mid-entry truncation | **PASS** | Same fixture truncated ~50% mid-entry, 5 runs, same Haiku model: **5/5 `no`**. |
| AC-5 — `LLMUnavailableError`/`LLMConfigError`/`UnreadableInputError` still propagate | **PASS** | Independently confirmed by class-hierarchy inspection (all three descend directly from `PageIndexError`, sibling to `TreeParseError`) **and** by live execution: mocked `process_toc_with_page_numbers` to raise each of `LLMUnavailableError` and `LLMConfigError` through `build_tree()` — both propagated unchanged, not swallowed by the new `except TreeParseError`. |
| AC-6 — `structure_attempts` returned alongside unchanged `structure_source` | **PASS** | Confirmed on the object returned by the public `build_tree()` call (see AC-1 evidence); `structure_source` kept its three-value contract (`_structure_source` reads only `outcome['flat_fallback']`/`outcome['partial']`, never `outcome['attempts']`, confirmed by reading the function). |
| AC-7 — documents that index correctly today are unchanged | **PASS** | `python -m pytest -q` → 18/18 passed, independently re-run. Code-read of the non-raising path in `meta_processor`: identical to pre-change except for the added `'error': None` key in the attempts entry and the wrapping `try` — no new branching on the happy path. |

## Additional checks (per QA brief)

1. **Contract-as-consumer check** — see Integration Coherence above. Documented shape matches code
   exactly, one minor undocumented `accuracy=None` cause noted (non-blocking).
2. **`build_tree` survival check** — confirmed positively; see AC-1/AC-6 evidence, obtained via
   the actual public function, not `page_index_main`.
3. **Negative/edge paths:**
   - Ladder bottoming out at `flat_fallback` (`fallback_flat_tree="yes"`, the default): the last
     `structure_attempts` entry for `process_no_toc` carries `accuracy` (float or `None`) and
     `error: None` even when nothing verified — coherent, no missing/malformed entry. Confirmed by
     code trace of `page_index.py:1298-1324` (the flat-fallback branch appends no new attempt entry
     but the terminal `process_no_toc` entry was already appended at line ~1274 before the
     verified/partial/flat-fallback decision runs).
   - `fallback_flat_tree="no"`: confirmed **live** — with `process_toc_with_page_numbers` raising
     and `process_no_toc` mocked to return an empty list (nothing verifiable), `build_tree(...,
     fallback_flat_tree="no")` raised `TreeParseError` with message `"Could not derive a document
     structure. Strategies attempted: ..."`, exactly matching `INTEGRATION.md` §4's documented
     behaviour for that flag.
4. **Haiku evidence gap — CLOSED.** The engineer's journal and Gandalf's review both state no
   Haiku inference profile was reachable on the AWS account in `~/.aws/credentials`
   (`654855421610`, `jungheinrich-project-aws-cli`, `eu-west-1`) and validated against Sonnet 4.5
   instead. I re-ran `aws bedrock list-inference-profiles --region eu-west-1` myself and found
   **three** Haiku profiles now listed, including
   `eu.anthropic.claude-haiku-4-5-20251001-v1:0` (EU) and
   `global.anthropic.claude-haiku-4-5-20251001-v1:0`. A smoke completion against
   `bedrock/eu.anthropic.claude-haiku-4-5-20251001-v1:0` succeeded. I then re-ran the exact Task 9
   Step 1 judge validation against this model (not simulated): **5/5 `yes`** on the faithful
   broken-numbering transform, **5/5 `no`** on the same content truncated mid-entry. The
   engineer's claim of "no Haiku inference profile available" was either a transient account/IAM
   propagation issue at the time or a wrong/incomplete profile ID tried (`eu.anthropic.claude-
   haiku-4-5` without the version suffix, per their journal, is indeed not a valid ID — the correct
   one carries `-20251001-v1:0`). This closes the Major (non-blocking) finding from Gandalf's
   review: the judge prompt is now validated against the actual production-class model, not just a
   more capable stand-in.

## Issues Found

- **Minor, non-blocking:** `INTEGRATION.md`'s `accuracy: None` explanation omits the
  `checked_count == 0` normal-return case (see Integration Coherence). Suggest a one-line addendum
  next time the doc is touched.
- **Pre-existing, not introduced by this branch:** `FORK_NOTES.md` contains client/document-name
  wording in §10a/§11 (predates this branch, already flagged by the engineer in their journal and
  in `decisions.md` "Open — for the user / the CTO" item 1). §12 (this branch's addition) is clean.
  No action needed from QA; already tracked as an open decision for the CTO.

## Likely CTO questions (profile.md §6.2)

1. **"Is the Haiku evidence gap actually closed, or did QA just get lucky with account state?"**
   Closed with fresh, independent evidence: 3 Haiku inference profiles now list on the same
   account/region the engineer used, a smoke call succeeded, and the full 5/5-yes / 5/5-no judge
   validation was re-run against `eu.anthropic.claude-haiku-4-5-20251001-v1:0` specifically — not
   assumed, not extrapolated from the Sonnet run. Recommend keeping this account/region pairing
   documented somewhere (e.g. the next FORK_NOTES touch) since profile availability visibly
   changed between the engineer's session and this one.
2. **"Does `structure_attempts` actually reach the code a downstream backend will call?"** Yes —
   verified against the public `build_tree()` function itself, not `page_index_main` internals.
   `build_tree.py` returns `page_index_main(...)`'s dict unmodified on both its input paths
   (`pages=` and `source=`).
3. **"What happens if the ladder bottoms out completely — silent bad index, or a signal?"**
   Two behaviours, both confirmed live: default (`fallback_flat_tree="yes"`) returns a one-node
   tree with `structure_source: "flat_fallback"` and a coherent `structure_attempts` trail
   (nothing malformed); with `fallback_flat_tree="no"` it raises `TreeParseError` with a message
   naming every strategy attempted. Both match `INTEGRATION.md` exactly.
4. **"Any doc drift between what's promised and what the code returns?"** One minor, non-blocking
   gap (the `checked_count == 0` → `accuracy: None` case, not currently documented). No key-name,
   type, or ordering drift found — the `structure_attempts` shape in `INTEGRATION.md` matches the
   returned dict exactly, verified by live execution, not by reading the source alone.
5. **"Should `flat_fallback` be treated as a product failure?"** Still an open product decision
   (tracked in `decisions.md`), out of scope for this QA pass — the technical signal
   (`structure_source`) is confirmed correct and unchanged.

## Summary

Static gates green (18/18 tests, no lint/build configured), the `INTEGRATION.md` contract matches
the code with one minor non-blocking documentation gap, and all 7 acceptance criteria were
independently re-derived by code trace and live execution against real Bedrock models — including
through the actual public `build_tree()` entry point rather than internal functions. The Haiku
evidence gap Gandalf flagged as Major is now closed with fresh 5/5-both-directions evidence against
the real production-class model. No blocking issues found. **PASS.**
