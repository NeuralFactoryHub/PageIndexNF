# Engineer Journal — toc-continuation
## Skill: backend-python
## Service: pageindex/
## Plan: (inline task spec from orchestrator)

### Work Log

#### [start] Task 1: Fix TOC continuation loop in extract_toc_content and toc_transformer

**What:** Both functions use the same wrong branching logic: they fall through to the
continuation loop whenever `if_complete == 'no'`, regardless of whether `finish_reason`
is `'finished'` or `'max_output_reached'`. The continuation loop sends "continue from
where you left off" with accumulated chat history — correct only for truncated responses.
For a finished response, re-prompting with "continue" makes the model emit a NEW JSON object;
concatenating that to the previous complete JSON produces malformed input that the checker
correctly rejects, forever.

**Why:** The fix separates the two control paths. `max_output_reached` → keep existing
continuation loop unchanged. `finished` + checker says no → fresh single-shot retries of
the original prompt (no chat history, no concatenation), up to 5 attempts. Bare `Exception`
on retry exhaustion upgraded to `TreeParseError` so consumers can distinguish structured
failures from bugs.

**Alternatives considered:** patching the checker to be more lenient (wrong — the checker
is correct, the problem is the prompt being sent to the model). Merging both cases into one
fresh-retry path (not done — the truncation continuation is semantically meaningful and
correct for that case).

**Files touched:** pageindex/page_index.py

#### [after task 1] Task 2: Name each generation in Langfuse traces

**What:** `llm_completion` and `llm_acompletion` in utils.py now derive a default
`generation_name` from `sys._getframe(1).f_code.co_name` (the name of the function that
called them). The ContextVar dict is copied before mutating so the name for one call doesn't
leak into all subsequent calls. The consumer's own `generation_name`, if present, wins.
`import sys` added to utils.py imports.

**Why:** Without per-call names, all ~40 Langfuse generations per document are labeled
`litellm-completion`, making traces unreadable. The frame approach names generations
automatically with no upstream file edits — any new call site added later is named for free.
The ContextVar copy is the load-bearing correctness requirement: the ContextVar value is
shared across the lifetime of a document run; mutating it in place would corrupt the name
for every call after the first.

**Alternatives considered:** threading a `name=` parameter through all ~20 upstream call
sites (rejected — ~24 extra hunks, future merge conflicts). Reading a thread-local instead
of ContextVar (rejected — asyncio tasks share threads).

**Files touched:** pageindex/utils.py
