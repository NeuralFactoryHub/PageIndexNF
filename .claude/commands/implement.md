---
description: Full SDLC implementation workflow — from brainstorm to release
---

Follow the SDLC defined in `.claude/SDLC.md` step by step for the given task.

## Workflow

Execute each phase sequentially. Do NOT skip steps. Ask for user confirmation before advancing to the next phase.

### Phase 1 — Brainstorm & Scope (SDLC §1)
- Use `@brainstorming` skill to explore approaches, constraints, risks.
- Identify impacted services from `.claude/project.yml`.
- Define success criteria and non-goals.
- **Checkpoint:** confirm scope with user before proceeding.

### Phase 2 — Architecture & Design Doc (SDLC §2)
- Write design doc to `docs/plans/YYYY-MM-DD-<topic>/design.md`.
- Capture: problem, affected services, API/schema changes, UX changes, risks.
- **Checkpoint:** confirm design with user.

### Phase 3 — Planning in ClickUp (SDLC §3)
- Use `@create-user-stories` to derive user stories with acceptance criteria.
- Store in `docs/backlog/`.
- Use `@sync-clickup` to push stories to ClickUp.
- Use `@update-story-status` to mark stories `in progress` as work begins.
- **Checkpoint:** confirm stories with user.

### Phase 4 — Implementation Plan (SDLC §4)
- Use `@write-plan` to generate concrete implementation plan.
- Map plan steps → ClickUp user stories.
- **Checkpoint:** confirm plan with user.

### Phase 5 — Branch & Repo Prep (SDLC §5)
- Create feature branch: `feature/<service>-<topic>` from `main`.
- Verify env setup.

### Phase 6 — Implementation (SDLC §6)
- Use `@execute-plans` to implement in batches.
- Use appropriate stack skill (`frontend-nextjs`, `backend-nextjs`, `backend-python`, etc.).
- Commit with `gh-commit` command (conventional commits).
- Run `lint_cmd` and `build_cmd` from `.claude/project.yml` after each batch.
- Update `@update-story-status` as stories complete.

### Phase 7 — Code Review (SDLC §7)
- Use `review-new-code` command for code review.
- Fix issues, re-review until green.

### Phase 8 — QA & UX Review (SDLC §8)
- Use `qa` agent to validate acceptance criteria.
- Use `ui-ux-reviewer` agent for UX/accessibility checks.
- Fix issues and re-run until both pass.

### Phase 9 — PR & Release (SDLC §9)
- Open PR to `main` linking ClickUp tasks and design doc.
- Use `gh-review-pr` for final review.
- Update `@update-story-status` to `closed` on merge.

### Phase 10 — Post-Release (SDLC §10)
- Summarize what to monitor.
- Note any lessons learned.

## Rules
- One phase at a time. Wait for user go-ahead between phases.
- Keep ClickUp status in sync throughout (see CLAUDE.md Auto Status Sync).
- If scope changes mid-flight, update design doc and user stories before continuing.
