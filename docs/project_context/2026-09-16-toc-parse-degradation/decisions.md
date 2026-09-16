# Decisions — TreeParseError enters the degradation ladder

Decisions the orchestrator took without the user present. Each one is reversible; raise it if you
disagree.

## D-1 — Scope: [A] + [C], [B] deferred
**2026-09-16 — user**
Tighten the judge prompt and route the exception into the ladder. The deterministic coverage
check replacing the LLM judge stays deferred: cost/determinism improvement, not a bug fix.

## D-2 — `structure_source` unchanged; add `structure_attempts`
**2026-09-16 — user**
Result quality and derivational history are two axes. Collapsing them would break consumers
branching on `structure_source == 'verified'`. The new field is purely additive.

## D-3 — No new tests
**2026-09-16 — user**
Root `CLAUDE.md`: *"DO NOT write tests unless explicitly requested."* Confirmed explicitly for
this work item. The existing suite must keep passing; the acceptance criteria are verified
manually (plan Task 9) and walked by QA.

## D-4 — Branch name `fix/strengthen-toc-ladder`
**2026-09-16 — user**
Departs from the `fix/<service>-<issue-id>` convention in `.claude/SDLC.md` §5. Accepted:
traceability is preserved by the ClickUp link in the design, the plan header and the commit body.

## D-5 — Task 9 uses a synthetic fixture, not the real failing PDF
**2026-09-16 — orchestrator, user absent**
Blocking for Task 9; taken autonomously so implementation is not held up.

**Decision:** build a synthetic TOC fixture that reproduces the trigger structurally — a line
merging two section numbers, plus backward and duplicated numbering — and keep it in the session
scratchpad, uncommitted.

**Why:**
- `FORK_NOTES.md` forbids domain- or client-specific content in this repo, and the real documents
  are client material. Committing them is not an option.
- Task 9 Step 1 exercises `check_if_toc_transformation_is_complete`, which takes a raw TOC string
  and a JSON transform. It needs no PDF at all — a synthetic pair reproduces the trigger exactly.
- A synthetic fixture is reusable by the next person; a local-only PDF is not.

**Caveat:** Step 2 (end-to-end) does need a real document. If one with merged TOC numbering is
available locally, use it **without committing it**; otherwise report Step 2 as not executed.

## D-6 — Task 9 must not be faked when credentials are missing
**2026-09-16 — orchestrator, user absent**
Task 9 needs live Bedrock calls, and the credentials for this fork live in the consuming repo,
not here. If they are unavailable, the engineer marks Task 9 **BLOCKED** in the journal and stops;
it must never be reported as passed on reasoning alone. The 5/5 truncation guard is the gate that
protects the `max_output_reached` continuation path — an unverified prompt change is exactly the
silent regression this work item exists to prevent.

## Open — for the user / the CTO
1. `design.md` names the real trigger documents. Scrub `docs/project_context/` too, or keep it
   exempt from the `FORK_NOTES.md` scope rule?
2. Should the backend treat `structure_source: "flat_fallback"` as a failure? Product policy, not
   a technical call — worth raising with the CTO.
