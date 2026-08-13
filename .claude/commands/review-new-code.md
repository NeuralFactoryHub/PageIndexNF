---
description: Review recently written code and propose targeted refactors — surgical, not rewrites.
---

# Review New Code

Analyze code from the most recent commits or current uncommitted changes
and propose targeted refactors. The goal is precision: identify where
complexity is excessive, NOT rewrite everything.

This command is distinct from the `reviewer` agent (which validates
completed work against a plan) and from `/gh-review-pr` (which reviews a
finished PR before merge). Use `/review-new-code` for iterative,
in-progress refinement of code you just wrote.

## Process

1. Identify the scope:
   - Recent commits: `git diff --name-only HEAD~3`
   - Uncommitted changes: `git diff --name-only`
   - If unclear, ask the user which scope to inspect
2. Read each touched file in full (not just the diff — context matters)
3. For each file, look for:
   - Functions or classes with too many responsibilities
   - Repeated logic that screams for extraction
   - Names that obscure intent
   - Conditionals or nestings that could be flattened
   - Comments that paper over unclear code instead of clarifying it
   - Hardcoded values that belong in config
4. Propose ONE refactor at a time, with: the specific file and line range, the problem, the suggested change, and the rationale
5. Wait for user approval before applying any change
6. Never propose refactors outside the identified scope
7. Never rewrite a whole file — surgical edits only

## Output Format

For each candidate refactor:

```markdown
### Refactor: <short name>
**File:** `path/to/file.ext:line-range`
**Problem:** <what's complex / unclear / repeated>
**Proposal:** <the specific change>
**Why:** <what this buys us; reference the developer's profile when relevant>
```

## Rules

- **Surgical, not wholesale.** No file rewrites, only targeted improvements.
- **One proposal at a time**, validated before the next.
- **Skip stylistic preferences** that don't pay off in real complexity reduction.
- **Reference `.claude/profile.md` when explaining the *why*.** If the developer has architecture or code-reading as a growth priority, lean into the pedagogical opportunity — explain the principle behind the refactor, not just the mechanics.
- **If nothing needs refactoring, say so.** Don't invent issues to look productive.
