---
name: gh-fix-ci
description: Auto-detect and fix CI/CD failures from GitHub Actions.
---

Detect and fix CI failures on the current branch.

## Process

1. Get current branch: `git branch --show-current`
2. List recent workflow runs: `gh run list --branch <branch> --limit 5`
3. Find the latest failed run
4. Get failure logs: `gh run view <run-id> --log-failed`
5. Analyze the error:
   - **Deploy failure**: Check deployment config syntax, build steps, env vars
   - **Build failure**: Check TypeScript errors, missing dependencies
   - **Lint failure**: Check ESLint, Ruff, or other linter issues
   - **Docker build failure**: Check Dockerfile, dependencies
   - **Test failure**: Check test output, missing fixtures
6. Propose and apply the fix
7. Commit the fix with `fix(ci): <description>`
8. Ask user if they want to push to trigger a new CI run
