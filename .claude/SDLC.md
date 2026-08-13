## Neural Factory — SDLC

**Goal:** lightweight, repeatable flow that plugs into `.claude/` agents/skills and ClickUp, from idea to production.

---

### 1. Brainstorm & Scope

- **Purpose**: turn a vague idea into a well-bounded task.
- **How**:
  - Use the brainstorming flow (Claude `brainstorm` command + `skills/brainstorming`) to explore approaches, constraints, risks.
  - Identify impacted services from `.claude/project.yml` (`services` and `architecture.service_dependencies`).
  - Define success criteria, non‑goals, and rough impact on UX, APIs, data, and infra.

---

### 2. Architecture & Design Doc

- **Purpose**: agree on how the change will work before coding.
- **Where**: `docs/plans/YYYY-MM-DD-<topic>/design.md`.
- **How**:
  - Use the `create-architecture-documentation` command as the starting point.
  - Capture:
    - Problem statement and constraints.
    - Affected services and data flows (reference `.claude/project.yml.architecture`).
    - API/schema changes and integration contracts.
    - UX changes (screens, flows, copy).
    - Rollout/rollback, observability, and risks.
  - Keep it short and opinionated; update it when scope changes.

---

### 3. Planning in ClickUp (Tasks & User Stories)

- **Purpose**: make work trackable and testable.
- **How**:
  - If a ClickUp task/epic already exists:
    - Use `skills/creating-userstories` (+ `create-user-stories` command) to derive user stories with clear acceptance criteria.
  - If no task exists:
    - Create a ClickUp task in the configured workspace/list (see `.claude/project.yml.integrations.clickup`).
    - Then create user stories under that task.
  - Store user stories in `docs/user-stories/<topic>.md`.
  - Use `skills/sync-clickup` to sync local stories ↔ ClickUp so status and content stay aligned.

---

### 4. Agent Team & Implementation Plan

- **Purpose**: define *who* does *what* across agents and services.
- **Agent**: `orchestrator` owns this phase — decomposes work, assigns agents, never writes code.
- **How**:
  - Use `skills/writing-plans` to generate a concrete implementation plan with:
    - Exact files, functions, and endpoints per service.
    - Commands to run (lint, build, serverless, etc.).
    - Explicit mapping from plan steps → ClickUp user stories.
  - Use `skills/executing-plans` so `engineer`, `reviewer`, `qa`, and `debugger` work in small, reviewable batches.

**Agent roster for the delivery cycle:**

| Phase | Agent | Role |
|-------|-------|------|
| 6. Implementation | `engineer` | Writes all code; loads skill per service |
| 6. Blocked | `debugger` | 6-phase root-cause analysis when engineer is stuck |
| 7. Code Review | `reviewer` | 3-layer review (plan compliance → requirements → quality) |
| 8. QA | `qa` | Lint, build, integration coherence, AC walkthrough |
| 8. UX Review | `ui-ux-reviewer` | Visual design, UX, accessibility audit via screenshots |

---

### 5. Branching & Repo Preparation

- **Purpose**: isolate work per feature and per service.
- **How**:
  - For each affected service in `.claude/project.yml.services`:
    - Create a branch from `main` with a consistent name, e.g.:
      - `feature/<service>-<topic-short>`
      - `fix/<service>-<issue-id>`
  - Ensure local env is ready (`.env`, `.env.example`, AWS credentials, etc.).
  - For infra changes (Serverless, Nginx, h-conf), verify the plan covers:
    - New env vars / SSM params.
    - IAM / permissions.
    - Rollout strategy.

---

### 6. Implementation per Service

- **Purpose**: implement user stories with the right stack patterns.
- **Agent**: `engineer` — loads the appropriate skill, follows the plan via `skills/executing-plans`, journals to `docs/project_context/<feature>/journals/engineer.md`.
- **If blocked**: spawn `debugger` agent (6-phase methodology). Engineer documents the block in journal; debugger investigates, fixes, and documents root cause.
- **How**:
  - **ClickUp sync:** when starting a user story, invoke `@update-story-status` with status `in progress`.
  - Use the appropriate skill for each service:
    - `frontend-nextjs` for Next.js frontend/BFF.
    - `backend-python` for FastAPI crew / Bedrock services.
    - `backend-nextjs` for Node/TS backends.
    - `hconf-setup` when integrating hierarchical config.
  - Use `.claude/commands/gh-commit.md` (`gh-commit`) for all commits — it enforces conventional commit messages, logical file grouping, and branch safety.
  - Keep the design doc and user stories updated when scope changes.
  - Run the local quality gates for each service:
    - `lint_cmd` from `.claude/project.yml`.
    - `build_cmd` when defined (e.g. frontend build).

---

### 7. Code Review & Integration on `dev`

- **Purpose**: ensure quality and integration before promoting to `main`.
- **How**:
  - **ClickUp sync:** when opening a PR for a user story, invoke `@update-story-status` with status `review`.
  - **Agent**: `reviewer` — 3-layer review (plan vs journal → code vs requirements → code quality). Outputs verdict to `docs/project_context/<feature>/validation/code_review.md`.
    - **APPROVED** → proceed to QA (phase 8).
    - **NEEDS_WORK** → orchestrator creates mini fix-plan, reassigns to `engineer`.
    - **REJECTED** → return to user/orchestrator at plan checkpoint.
  - Use `review-new-code` command to trigger the reviewer on each feature branch.
  - Once a branch is green (lint, build, tests, basic manual checks):
    - Merge it into the `dev` branch for that repo.
  - Deploy `dev` via the existing CI/CD (Serverless / GitHub Actions pattern).
  - Run integration checks:
    - End‑to‑end flows (e.g. ingestion → search → chat → frontend).
    - Contracts from `.claude/project.yml.architecture.integration_contracts`.

---

### 8. System QA & UX Review

- **Purpose**: verify behaviour against user stories and UX expectations.
- **How**:
  - **Agent**: `qa` — runs lint/build, checks integration contracts, walks through each AC. Outputs to `docs/project_context/<feature>/validation/qa_report.md`.
    - Validate each user story against its acceptance criteria.
    - Try negative paths and edge cases (invalid filters, missing docs, failures, etc.).
    - If QA **FAIL** → orchestrator creates fix-plan, reassigns to `engineer`, then re-runs QA.
  - **Agent**: `ui-ux-reviewer` — captures screenshots via browser, audits visual design, UX, and WCAG accessibility. Invoke on any frontend-facing change.
    - Check UX flows, responsiveness, accessibility.
    - Check copy tone and terminology consistency.
  - Open fix branches from `dev` as needed and re‑run QA/UX until both pass.
  - **ClickUp sync:** when a user story passes QA, invoke `@update-story-status` with status `closed`.

---

### 9. PR to `main` & Production Release

- **Purpose**: promote a validated change set to production.
- **How**:
  - Open PR(s) from `dev` (or feature branches if operating trunk‑based) into `main`:
    - Link the relevant ClickUp task and user stories.
    - Link the design doc (`docs/plans/.../design.md`).
    - Summarise impact, risks, and rollback plan.
  - **Agent**: `reviewer` — final review pass before merge. Use `gh-review-pr` command to trigger.
  - Merge to `main` using the standard CI pipeline, which:
    - Deploys to the production AWS account / stage.
    - Runs the agreed test/build steps.

---

### 10. Post‑Release Monitoring & Feedback Loop

- **Purpose**: catch issues early and feed learning back into the system.
- **How**:
  - Monitor:
    - Logs and metrics for all affected services (Lambdas, FastAPI, frontend, Weaviate, S3, Bedrock, Mongo).
    - Error rates, latency, and key business metrics (e.g. search quality, ingestion success).
  - If issues appear:
    - Roll back or apply a focused hotfix (short‑lived branch → `dev` → `main`).
  - Capture lessons learned (DX pain, operational issues, UX friction) and:
    - Update the relevant design doc.
    - Add notes to future brainstorming or architectural docs when patterns repeat.

