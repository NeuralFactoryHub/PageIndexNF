---
name: gh-commit
description: Smart commit with conventional commit standards, branch safety, and logical file grouping.
---

Analyze the current git state and create a well-structured commit.

## Process

1. Run `git status` and `git diff --staged` to understand changes
2. Check current branch — warn if on `main` (direct commits to main are discouraged)
3. Group changed files by logical concern (e.g., all route changes together, all model changes together)
4. Generate a conventional commit message:
   - `feat:` — new feature
   - `fix:` — bug fix
   - `refactor:` — code restructuring
   - `docs:` — documentation
   - `chore:` — maintenance, config
   - `style:` — formatting, no logic change
5. Keep message concise
6. If multiple logical groups exist, suggest multiple commits
7. Show the proposed commit(s) to the user for approval
8. Stage files and commit with the approved message

## Rules

- Never force push
- Never commit `.env` files or secrets
- Always include `Co-Authored-By: Claude <model> <noreply@anthropic.com>` in commit body
- If pre-commit hook fails, fix the issue and create a NEW commit (never --amend)
