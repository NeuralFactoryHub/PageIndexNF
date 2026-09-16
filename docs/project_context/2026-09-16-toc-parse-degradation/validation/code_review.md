# Code Review — TreeParseError enters the degradation ladder

**Branch:** `fix/strengthen-toc-ladder`, commit `9ad4758`, cut from `feature/customizations`.

## Verdict: NEEDS_WORK

One targeted, non-code fix required before merge (update `INTEGRATION.md`). Everything else —
control flow, exception boundary, prompt contract, regression risk — checks out.

## Plan Compliance

- [x] Task 0: branch cut from `feature/customizations` as `fix/strengthen-toc-ladder`
- [x] Task 1: `TocTransformError(TreeParseError)` added to `errors.py`
- [x] Task 2: both `toc_transformer` max-retry raises switched to `TocTransformError`;
      `extract_toc_content`'s raises left as `TreeParseError` (correct — different stage)
- [x] Task 3: judge prompt redefines "complete" as coverage-only, narrow "no" branch preserved
- [x] Task 4: mode dispatch wrapped in `try/except TreeParseError`, delegates to `_next_strategy`
- [x] Task 5: `_next_strategy` implements the short-circuit
- [x] Task 6: `error: None` added to the returning-path attempt entry
- [x] Task 7: `structure_attempts` added to both `page_index_builder` return dicts
- [x] Task 8: `python -m pytest -q` → 18 passed (independently re-confirmed by orchestrator)
- [x] Task 9: manual verification, all sub-steps run against live Bedrock, results pasted
      verbatim into the journal, deviations self-disclosed
- [x] Task 10: `FORK_NOTES.md` §12 added, generic wording, pre-existing violations correctly
      flagged rather than silently "fixed" out of scope
- [x] Task 11: single clean commit on the correct branch

Journal quality: well above bar (rationale, alternatives, verbatim verification output per task).

## Requirements Compliance (design.md §6)

- [x] AC-1: a document whose transform never converges reaches `process_no_toc` without raising —
      confirmed by code trace and by the engineer's live e2e run (Task 9 Step 2)
- [x] AC-2: `process_toc_no_page_numbers` is skipped, not attempted, on a `TocTransformError` from
      step 1, and the skip is recorded (`error: 'skipped'`) — confirmed in `_next_strategy`
- [x] AC-3: judge accepts a faithful transform reproducing broken source numbering — 5/5 `yes`
      against a live model (see Evidence Gap note below on *which* model)
- [x] AC-4: judge still rejects mid-entry truncation — 5/5 `no`, same caveat
- [x] AC-5: `LLMUnavailableError`/`LLMConfigError`/`UnreadableInputError` still propagate —
      independently verified via `errors.py`'s class hierarchy and `utils.py`'s raise sites, not
      just the journal's claim
- [x] AC-6: `structure_attempts` returned alongside unchanged `structure_source` — confirmed in
      both `page_index_builder` return sites; `_structure_source` untouched and does not read
      `outcome['attempts']`, so its three-value contract is unaffected
- [x] AC-7: happy path is additive-only — the try/except adds no branching on the non-raising
      path, only two new dict keys; existing suite green

## Issues

### Critical
None.

### Major

1. **`INTEGRATION.md` not updated for `structure_attempts`.** This file is the documented
   consumer contract (`tree["structure_source"]` is spelled out with a table of three values).
   `structure_attempts` — the entire observability payoff of fix [C], per design.md §4 ("answers
   the audit question... without parsing logs") — is added to the return dict but never mentioned
   here. The consuming backend team has no reason to discover this field exists unless they read
   `page_index.py` source. Not in the plan's task list (a plan gap, not an engineering error), but
   it undermines the stated purpose of AC-6 if left as-is. **Recommend:** add a short section
   before merging to `feature/customizations`, mirroring the `structure_source` table format:
   `{mode, accuracy, error}` per entry, `error` values (`None`, an exception class name, or
   `"skipped"`), and note it is additive/optional to consume.

### Minor

1. **`extract_toc_content` is dead code.** Grep confirms no call site anywhere in `pageindex/`
   (only referenced from `tests/test_issue_163.py`). design.md and plan.md both describe the
   judge as "load-bearing twice... in `toc_transformer` and in `extract_toc_content`" — true of
   the source text, false of the reachable call graph. This does not affect correctness of this
   branch (the shared judge function was correctly modified once, covering the one call site that
   actually runs), but the design's risk framing overstates the surface tightened. Worth a
   one-line correction next time this file is touched, not a blocker.
2. **The `not isinstance(exc, TocTransformError)` branch in `_next_strategy` is currently
   unreachable.** Every live raiser of `TreeParseError` from inside `process_toc_with_page_numbers`
   is `toc_transformer`, which (post this change) only raises `TocTransformError`. So a plain
   `TreeParseError` from that mode cannot occur today; the branch is defensive/forward-compatible
   code, not exercised by anything in the current codebase. Fine to keep, but flag as untested-by-
   construction if it matters later (no new tests were requested, per D-3).
3. Cosmetic: `_next_strategy`'s parameter continuation line is indented one space short of the
   opening paren (`async def _next_strategy(exc, page_list, mode=None, ...,\n                         start_index=1, ...)`);
   doesn't affect `python -m pytest` or readability meaningfully, PEP8 nit only.

## Control-flow trace — `_next_strategy` (requested focus item 1)

| Caller mode | Exception type | Result |
|---|---|---|
| `process_toc_with_page_numbers` | `TocTransformError` | logs+records `process_toc_no_page_numbers` as `skipped`, recurses into `process_no_toc` |
| `process_toc_with_page_numbers` | `TreeParseError` (non-`TocTransformError`) | recurses into `process_toc_no_page_numbers` normally (currently unreachable in practice — Minor #2) |
| `process_toc_no_page_numbers` | any `TreeParseError` | falls through both `process_toc_with_page_numbers` checks, recurses into `process_no_toc` |
| `process_no_toc` | any `TreeParseError` | `raise exc` — floor exhausted, propagates unchanged, traceback preserved (`exc.__traceback__` carries through) |

No cycle exists: every branch either terminates (`process_no_toc` re-raise) or moves strictly
downward on the ladder (`with_page_numbers` → `no_page_numbers` → `no_toc`), and `mode` is always
passed as a literal at each call site, never derived from `outcome`, so there is no way to loop
back to an earlier mode. `outcome` is threaded by reference through every recursive call and only
ever appended to, never reset or shadowed — no lost state.

## Exception boundary (AC-5, requested focus item 2)

Verified independently, not from the journal:
- `errors.py`: `UnreadableInputError`, `LLMUnavailableError`, `LLMConfigError` all subclass
  `PageIndexError` directly. `TreeParseError` is a sibling branch. `except TreeParseError` cannot
  catch any of them via normal MRO.
- `utils.py` `llm_completion`/`llm_acompletion` (the only place these three are raised) raise them
  directly from the LLM call site — nothing in between wraps or reclassifies them as
  `TreeParseError` before they would reach `meta_processor`'s try block.
- Nothing inside `process_toc_with_page_numbers` / `process_toc_no_page_numbers` / `process_no_toc`
  catches-and-reraises these three types as `TreeParseError`; they propagate straight through the
  try block, out of `meta_processor`, unmodified. Confirmed by reading every function in the call
  chain for the three strategies (`toc_transformer`, `toc_index_extractor`, `generate_toc_init`,
  `generate_toc_continue`, `add_page_number_to_toc`, `process_none_page_numbers`) — none catch
  `PageIndexError` subtypes.

## AC-7 regression risk (requested focus item 3)

The try/except adds zero new branching on the non-raising path: same dispatch, same
`toc_with_page_number` post-processing, same `verify_toc` call, same ladder-below logic (lines
after the try block are byte-identical to before except for the added `'error': None` key).
`_structure_source(outcome)` only reads `outcome.get('flat_fallback')` / `outcome.get('partial')`
— it never inspects `outcome['attempts']`, so the added `'error'` key and the new
`structure_attempts` field cannot change its output. `structure_attempts` is a new top-level key,
additive to both return dicts; no existing key is removed, renamed, or retyped. 18/18 existing
tests green. Risk: low, matches design intent.

## Judge prompt as contract (AC-3/AC-4, requested focus item 4)

The rewritten prompt correctly narrows the "no" branch to exactly two conditions (missing entries,
truncation), both required for the `max_output_reached` continuation path to keep working, and
explicitly enumerates the flaws that must NOT trigger "no" (backward/repeated/merged numbering,
unnumbered entries, inconsistent depth) — directly answering the "unsatisfiable loop" problem in
design.md §2.

**On `check_if_toc_extraction_is_complete` being left untouched:** correct, not an inconsistency —
that function has zero call sites in `pageindex/` (confirmed by repo-wide grep; only
`tests/test_issue_163.py` references it). It is unrelated dead code, not a second live judge that
needed the same fix. The design/plan text describing the modified judge
(`check_if_toc_transformation_is_complete`) as driving continuation in "both `toc_transformer` and
`extract_toc_content`" is also only half-live: `extract_toc_content` itself has no call site
either (Minor #1 above). Net effect: the one judge function that actually runs in production
(inside `toc_transformer`) was the one that needed fixing, and it was fixed once, correctly,
covering its one live call site.

## Evidence gap (requested focus item 5) — severity judgment

Task 9 validated the judge prompt against `bedrock/eu.anthropic.claude-sonnet-4-5-20250929-v1:0`;
design.md's prior evidence (task `86cb9mkne`) and the reported production failure are both
against `claude-haiku-4-5`. The engineer disclosed this rather than hiding it, and the deviation
was forced (no working Haiku inference profile on the AWS account used, which is itself named
`jungheinrich-project-aws-cli` — worth asking whether that account is even representative of the
production Bedrock account for this workload, see CTO questions).

**Judgment: Major, not blocking.** Two reasons:
1. The prompt is a coverage-vs-normative classification instruction, not something that exploits
   Sonnet-specific reasoning depth; a more capable model passing is *some* evidence but not proof
   a materially weaker model will also converge on the "reproduce the flaw, don't fix it" framing.
   This genuinely should be re-run against production's actual model before or shortly after this
   merges.
2. Critically, **fix [C] is model-independent and provides a safety net for fix [A]'s
   uncertainty.** If the judge prompt fails to converge on Haiku the way it did on Sonnet,
   `toc_transformer` still exhausts its 5 retries and raises `TocTransformError` exactly as
   before — but now that exception is caught by the new dispatch wrapper regardless of which
   model produced it, and the ladder still degrades to `process_no_toc`. AC-1 ("indexed instead
   of raising") is satisfied by fix [C] alone, independent of whether fix [A] actually helps on
   the production model. Worst case if the model-evidence gap turns out to matter: the document
   still gets indexed (via the floor), just without recovering the ~12 wasted calls fix [A] was
   meant to save. That is a cost regression risk, not a correctness regression risk.

**Recommendation:** merge is not blocked on this, but re-run Task 9 Step 1 against the actual
`claude-haiku-4-5` production model at the next opportunity (e.g. once the correct account/region
is confirmed with the CTO) and record the result — don't let "5/5 on Sonnet" stand in as the
permanent evidence base for a Haiku-driven production path.

## Likely CTO questions (profile.md §6.2)

1. **"Why does this catch `TreeParseError` broadly instead of only `TocTransformError`?"**
   Because `process_no_toc` and (if it were ever wired in) other stages can still raise a plain
   `TreeParseError` for reasons unrelated to the transform step; catching the base type keeps the
   dispatch wrapper correct even as the ladder gains steps, while `TocTransformError` is only used
   to decide the *short-circuit*, not whether to catch. Point to design.md §3's "Boundary" section.
2. **"Could this now silently paper over a systemically broken document with a useless flat
   node?"** Yes, by design — `structure_source: "flat_fallback"` is the existing, unchanged signal
   for exactly that case (design.md §4, "Already built — no change"). This branch adds no new
   silent-failure surface; it routes a previously-fatal case into a path that already existed and
   was already instrumented.
3. **"You validated the judge on Sonnet, not the Haiku model that's actually failing in
   production — why should I trust this?"** Answered directly under Evidence Gap above: fix [C]
   is the actual guarantee for AC-1 and is model-independent; fix [A] is a cost optimization on
   top of it that needs a follow-up validation run against the real model. Recommend saying this
   proactively rather than waiting to be asked.
4. **"Why is `structure_attempts` not documented in `INTEGRATION.md`?"** Plan gap — flagged as
   Major above. Answer: it will be added before/at merge to `feature/customizations`; not a code
   defect, a docs-completeness gap caught by review.
5. **"Why didn't you fix the pre-existing domain wording in FORK_NOTES.md while you were in
   there?"** Out of scope for this plan — engineer correctly declined to silently rewrite another,
   already-reviewed section's verification history and flagged it upward instead (decisions.md
   already tracks this as `Open — for the user / the CTO` item 1).
6. **"Is `check_if_toc_extraction_is_complete` dead code we should delete?"** Yes, by this
   review's grep — zero production call sites, referenced only by a test. Not in scope for this
   branch (no new cleanup was requested), but worth a follow-up ticket.

## Summary

The control flow, exception boundary, and additive-return-value claims all hold up under
independent code tracing, not just journal review — no infinite recursion, no swallowed
infrastructure errors, no regression risk on the happy path. The one real gap is
`INTEGRATION.md` not documenting the new `structure_attempts` field, which undercuts the
observability goal the whole design is built around; that is the qualifying reason for
NEEDS_WORK rather than APPROVED. The Sonnet-vs-Haiku evidence gap is real and should be closed
with a follow-up run, but it is not blocking because fix [C] guarantees AC-1 independent of
fix [A]'s model generalization.
