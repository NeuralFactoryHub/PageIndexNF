---
name: gh-review-pr
description: Comprehensive PR review with metadata, diff, CI status, and file-by-file analysis.
---

Review the current PR (or a specified PR number) comprehensively.

## Process

1. Get PR metadata: `gh pr view` (title, body, author, base branch, labels)
2. Get PR diff: `gh pr diff`
3. Get CI status: `gh pr checks`
4. Get PR comments: `gh api repos/{owner}/{repo}/pulls/{number}/comments`
5. Analyze each changed file:
   - Does it follow the service's conventions?
   - Are there security concerns (OWASP)?
   - Are there performance concerns?
   - Is error handling consistent with service patterns?
6. Check cross-service coherence if multiple services changed
7. Present structured review:

```markdown
## PR Review: #<number> — <title>

### Summary
<2-3 sentences>

### File Analysis
| File | Status | Issues |
|------|--------|--------|
| path/to/file.py | OK | - |
| path/to/other.ts | Warning | Missing error handling |

### Issues
#### Critical
- ...
#### Suggestions
- ...

### Verdict: APPROVE | REQUEST_CHANGES | COMMENT
```

## Usage

- `/gh-review-pr` — review current branch's PR
- `/gh-review-pr 42` — review PR #42
