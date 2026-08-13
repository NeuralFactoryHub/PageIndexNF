---
name: de-slop
description: Remove AI-generated artifacts from code (redundant comments, unnecessary markdown, generic TODOs).
---

Scan recently changed files and remove AI-generated artifacts.

## What to Remove

1. **Redundant comments** — Comments that restate what the code does:
   ```python
   # Get the user ID
   user_id = request.headers.get("x-user-id")
   ```
   → Remove the comment

2. **Generic TODOs** — AI-generated placeholders:
   ```python
   # TODO: Add error handling
   # TODO: Implement this function
   ```
   → Remove (unless the TODO is specific and actionable)

3. **Unnecessary type annotations on obvious code** — Added by AI but not needed

4. **Excessive docstrings** — On simple/obvious functions

5. **Markdown formatting in code comments** — Bold, headers in inline comments

## Process

1. Get recently changed files: `git diff --name-only HEAD~5`
2. Read each file
3. Identify AI artifacts
4. Show proposed removals to user
5. Apply approved removals
6. Commit with `chore: de-slop — remove AI artifacts`

## Rules

- Only touch files changed in recent commits (not the whole codebase)
- Preserve meaningful comments (especially "why" comments)
- When in doubt, keep the comment
