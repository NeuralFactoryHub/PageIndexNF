# Engineer Journal — preprocessing

## Skill: backend-python
## Service: pageindex/
## Plan: docs/plans/2026-08-19-preprocessing/plan.md

### Work Log

#### [00:00] Task 1: Error taxonomy (errors.py)

**What:** Creating `pageindex/errors.py` with the full typed error hierarchy.
**Why:** The codebase currently raises bare `Exception` in the tree parser and returns `""` from the LLM retry loop on exhaustion. Both collapse unrelated failure causes into one indistinguishable symptom — a caller cannot tell a throttled model from a broken document, and cannot decide whether retrying is sensible. Typed errors make that distinction part of the public contract.
**Alternatives considered:** Inline exceptions in each module (rejected — callers can't import them for `except` clauses without circular deps). Reusing `litellm`'s own exceptions (rejected — ties the public surface to a dependency).
**Files touched:** `pageindex/errors.py` (created)
