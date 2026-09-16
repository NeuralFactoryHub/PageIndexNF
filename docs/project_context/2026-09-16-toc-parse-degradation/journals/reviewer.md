# Reviewer Journal — TreeParseError enters the degradation ladder

#### [10:00] Review started
**Plan tasks reviewed:** 11 (Task 0-11, plan.md)
**Files reviewed:** `pageindex/errors.py`, `pageindex/page_index.py` (full diff + surrounding
context: `toc_transformer`, `extract_toc_content`, `check_toc`/`toc_extractor`,
`process_no_toc`/`process_toc_no_page_numbers`/`process_toc_with_page_numbers`, `meta_processor`,
`_next_strategy`, `_structure_source`, `page_index_builder`), `pageindex/utils.py`
(`llm_completion`/`llm_acompletion` error taxonomy, `extract_json`), `FORK_NOTES.md` §12,
`INTEGRATION.md`, `docs/project_context/2026-09-16-toc-parse-degradation/{design,plan,decisions,journals/engineer}.md`.

#### [10:05] Layer 1 — plan vs journal
All 11 tasks completed as specified; no scope creep. Journal quality is well above the 3-sentence
bar: every entry has rationale, alternatives considered, verification output pasted verbatim.
Two self-disclosed deviations found in the journal, both flagged by the engineer rather than
hidden: (a) Task 9 ran against `bedrock/eu.anthropic.claude-sonnet-4-5-20250929-v1:0`, not the
`claude-haiku-4-5` named in design.md's prior evidence, because the local AWS profile
(`jungheinrich-project-aws-cli`) has no working Haiku inference profile; (b) Task 10's verify
grep found pre-existing domain wording in FORK_NOTES.md §10a/§11 (lines ~10-316, predates this
branch) and the engineer correctly did not touch it, flagging it upward instead.

#### [10:20] Layer 2 — code vs requirements
Traced every AC against the actual diff, not just the journal's claims. Confirmed independently
(not by re-reading the journal's assertions):
- `TocTransformError` subclasses `TreeParseError`, raised only at the two `toc_transformer`
  max-retry sites; `extract_toc_content`'s two raises at :278/:297 are untouched (correct — but
  see finding below, `extract_toc_content` is dead code).
- `except TreeParseError` in `meta_processor` cannot catch `LLMUnavailableError`,
  `LLMConfigError`, `UnreadableInputError` (and subclasses) — verified via `errors.py`: all three
  inherit directly from `PageIndexError` on sibling branches, never through `TreeParseError`.
  Also verified nothing in `utils.py`'s `llm_completion`/`llm_acompletion` wraps those into
  `TreeParseError` before it reaches the dispatch.
- Traced `_next_strategy` for every mode/exception combination by hand (see report for the table)
  — no infinite recursion, no lost `outcome` state, every path terminates.
- `structure_attempts`/`error: None` additions are purely additive; `_structure_source` only
  reads `outcome['flat_fallback']`/`outcome['partial']`, never `outcome['attempts']` shape, so no
  consumer of that helper breaks.

#### [10:40] Layer 3 — quality and project rules
No CLAUDE.md non-negotiable violated. No new tests (correct per D-3, confirmed no test files in
diff). Found one real gap: `INTEGRATION.md` (the consumer-facing return-dict contract) documents
`structure_source` but was never updated to mention the new `structure_attempts` key, even though
design.md §4 frames it as answering "the audit question" for the consuming backend. Also found
that `extract_toc_content` — one of the two functions design.md says the judge is "load-bearing
twice" for — is dead code (no call site anywhere in `pageindex/`, only referenced by
`tests/test_issue_163.py`), which changes the risk read on AC-3/AC-4 (see report).

Verdict and full findings written to `validation/code_review.md`.
