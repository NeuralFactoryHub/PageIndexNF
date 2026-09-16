# Design — TreeParseError must enter the degradation ladder

- **ClickUp:** https://app.clickup.com/t/123y1w8cjwa (reopens https://app.clickup.com/t/86cb9mkne)
- **Service:** `pageindex` (single-service library)
- **Scope decided:** fix **[A]** (judge prompt) + **[C]** (exception enters the ladder). **[B]**
  (replace the LLM judge with a deterministic coverage check) stays deferred.
- **Branch:** `fix/strengthen-toc-ladder`, cut from `feature/customizations` (never from `main` —
  see the PageIndexNF override in `.claude/SDLC.md` §5).

## 1. Problem

The module carries two mutually blind error channels.

The degradation ladder in `meta_processor` decides on **values**: `accuracy: float | None`, where
`None` means "this strategy could not be verified" (`page_index.py:1218`, `verified = accuracy is
not None`). `toc_transformer` reports on **exceptions**: `raise TreeParseError`
(`page_index.py:421`, `:451`).

The exception does not break the ladder — it unwinds past it, before `accuracy` exists. The mode
dispatch at `page_index.py:1184-1192` has no `try/except`; confirmed by inspection.

Everything downstream of that dispatch is already built and tested and is never reached on this
path: the accuracy gate, the partial-structure salvage above 0.6, and the flat-tree floor
(`page_index.py:1218-1270`).

Downstream of the library, the consuming backend classifies `TreeParseError` as permanent and
attributable to the document, so the document is never retried.

### Why the retries cannot help

`toc_transformer` retries five times with an **identical** prompt after a judge rejection. The
failure is deterministic (3/3 identical `no` locally against
`bedrock/eu.anthropic.claude-haiku-4-5`), so the retries cannot converge. They only burn calls —
~12 LLM calls and ~45s per failing document — before raising.

### Trigger

`DUVRI MARCALLO.pdf` and `DUVRI MARCALLO per Stab.di Castenedolo (BS).pdf`. A TOC line collapses
two sections into one:

```
1.- 2. Anagrafica Azienda Committente - Pag. 5
3. Verifica dei requisiti Tecnico-Professionali ... Pag. 6
```

`1.- 2.` is not a value the transformer can copy into a single `structure` field, so it renumbers
sequentially and every later entry shifts by one. The judge compares raw against cleaned, sees the
mismatch, and returns `no`.

Both the searchable and the OCR version of the same document fail identically, which rules out
text quality as a factor.

## 2. Fix [A] — define "complete" for the judge

`check_if_toc_transformation_is_complete` (`page_index.py:222-241`) asks the model to "check if
the table of contents is complete" and never defines *complete*. The word admits two readings:

- **coverage** — no entry is missing (what we want);
- **normative** — the TOC is well formed and correctly numbered (what the model picks, because it
  is the more natural reading of the bare word).

This makes the two prompts contractually incompatible. `toc_transformer` is instructed to
transcribe faithfully, defects included. The judge, unintentionally, is asking for correctness.
The transformer cannot satisfy the judge without falsifying the document — an unsatisfiable loop.

**Change:** define `complete` as coverage only, and state explicitly that reproducing a flaw of
the source (backward, duplicated, merged or skipped numbering) is correct behaviour.

**Constraint — the judge is load-bearing twice.** Besides gating the transform, it is the signal
that detects a response truncated by output limit, which drives the `max_output_reached`
continuation path in `toc_transformer` and in `extract_toc_content`. Loosening it must not make it
accept truncation. The truncation regression guard is mandatory, not optional.

**Prior evidence** (task `86cb9mkne`, 5 runs per direction, real failing document): faithful JSON
with broken numbering reproduced → 5/5 `yes` (was 6/6 `no`); the same JSON truncated at 50% →
5/5 `no`.

## 3. Fix [C] — translate the exception into the ladder's own language

Wrap the mode dispatch and convert `TreeParseError` into the signal the ladder already reads:
an unverified attempt (`accuracy = None`).

This adds **no new recovery mechanism**. It connects an orphaned path to the one that exists.

Ladder behaviour for the trigger document:

| Step | Outcome |
|---|---|
| `process_toc_with_page_numbers` | calls `toc_transformer` → judge `no` → raises → **degrade** |
| `process_toc_no_page_numbers` | calls `toc_transformer` with the same `toc_content` → raises → **degrade** |
| `process_no_toc` | does not use `toc_transformer`; infers structure from the pages → verifies |

The expected landing for the DUVRI is therefore a real tree with `structure_source: "verified"`,
not the flat floor.

**Cost note.** Step 2 is *guaranteed* to fail whenever step 1 failed inside `toc_transformer`:
same function, same `toc_content`, deterministic outcome. Letting it run burns another ~12 LLM
calls for a known-lost cause. The plan must short-circuit from step 1 straight to `process_no_toc`
when the failure originated in the transform stage, while still recording the skipped attempt.

**Boundary.** Only `TreeParseError` is caught. `LLMUnavailableError`, `LLMConfigError` and the
`UnreadableInputError` family must keep propagating — degrading on a throttled model would turn a
retryable, infrastructure-caused failure into a silently poor index.

## 4. Observability — the cost of [C]

[C] trades a **loud** failure for a **silent** one. A document that today raises will tomorrow
return a tree. If the ladder bottoms out at the flat floor, that tree is a single node spanning
the document: technically indexed, with no navigational value. Without a signal, the backend
accepts it and the defect only surfaces later as "search returns nothing for this PDF".

### Already built — no change

`structure_source` exists and is already returned by `page_index_main` (`page_index.py:1350-1365`,
emitted at `:1424` and `:1430`) with three values: `verified`, `partial`, `flat_fallback`. The
distinction cannot be inferred from the tree itself — a genuine single-section document and a
floor result look identical — so it is already part of the returned contract.

**Decision: do not add a fourth value.** `structure_source` answers *how much of the result passed
verification* — an axis of result quality. "The run had to degrade because a stage raised" is a
different axis: derivational history. Collapsing both into one field conflates them and would
break consumers branching on `structure_source == 'verified'`.

### To add — `structure_attempts`

`outcome['attempts']` is already populated per strategy at `page_index.py:1216` with
`{mode, accuracy}`, but it only reaches the log and is then discarded. Add it to the returned
dict, extended with the failure cause:

```python
{
  "structure_source": "verified",          # unchanged, same three values
  "structure_attempts": [
    {"mode": "process_toc_with_page_numbers", "accuracy": None, "error": "TreeParseError"},
    {"mode": "process_toc_no_page_numbers",   "accuracy": None, "error": "skipped"},
    {"mode": "process_no_toc",                "accuracy": 0.94, "error": None}
  ]
}
```

Purely additive: no existing consumer breaks. It answers the audit question — *which documents
were saved by degrading, and why* — without parsing logs.

## 5. Non-goals

- **[B]**, the deterministic coverage check replacing the LLM judge. Deferred; tracked as a
  cost/determinism improvement, not a bug fix.
- Any change in the consuming backend. Bumping the fork pin lives in that repo.
- Retry/backoff policy for `LLMUnavailableError`.

## 6. Acceptance criteria

1. A document whose TOC transform never converges is indexed instead of raising; the run reaches
   `process_no_toc`.
2. `process_toc_no_page_numbers` is skipped — not attempted — when step 1 failed inside the
   transform stage, and the skip is recorded in `structure_attempts`.
3. The judge accepts a faithful transform that reproduces broken source numbering.
4. The judge still rejects a transform truncated mid-way (regression guard for the
   `max_output_reached` continuation path).
5. `LLMUnavailableError`, `LLMConfigError` and `UnreadableInputError` still propagate out of the
   dispatch unchanged.
6. `page_index_main` returns `structure_attempts` alongside `structure_source`; `structure_source`
   keeps its three existing values and its current semantics.
7. Documents that index correctly today still produce an unchanged structure.

## 7. Risks

| Risk | Mitigation |
|---|---|
| Loosening the judge breaks truncation detection | AC 4 is a mandatory regression guard on both call sites |
| Silent degradation goes unnoticed in production | AC 6 — `structure_attempts` in the returned contract |
| Catching too broadly swallows retryable LLM failures | Catch `TreeParseError` only (§3, Boundary) |
| A document that used to raise now returns a one-node tree | Signalled via `structure_source: flat_fallback`; a backend decision, out of scope here |
