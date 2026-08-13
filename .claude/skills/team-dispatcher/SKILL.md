---
name: team-dispatcher
description: Dispatch complex work to the right subagent(s). Routes tasks to existing agents first, uses parallel delegation when work decomposes cleanly, escalates to orchestrator team mode only when active coordination is needed.
---

# Team Dispatcher

**Announce at start:** "I'm using the team-dispatcher skill to route this work."

## Purpose

Decide the optimal dispatch strategy for a task: single agent, parallel agents, or full orchestrator team. Prefer the smallest effective configuration.

## Available Agents

Defined in `.claude/agents/`. Spawned via **Task tool** or **TeamCreate + SendMessage** in teammate mode.

| Agent | File | Capability |
|-------|------|------------|
| `Dexter (engineer)` | `agents/engineer.md` | Writes all implementation code; loads skills dynamically per stack |
| `WaLead (orchestrator/Tech Lead)` | `agents/orchestrator.md` | Decomposes, assigns, monitors, validates; never writes code |
| `reviewer` | `agents/reviewer.md` | 3-layer code review (plan compliance, requirements, quality + security) |
| `qa` | `agents/qa.md` | Lint, build, integration coherence, AC walkthrough |
| `debugger` | `agents/debugger.md` | 6-phase systematic debugging; can write fix code |
| `ui-ux-reviewer` | `agents/ui-ux-reviewer.md` | Visual design, UX, WCAG accessibility audit via browser |

## Dispatch Policy — Order of Preference

1. **Single existing agent** — task is narrow, one specialty dominates.
2. **Multiple existing agents in parallel** — work splits into independent tracks; main session aggregates results.
3. **Orchestrator team mode** — work requires active cross-agent coordination, synthesis from a lead, or the full SDLC workflow (design → plan → deliver → review → QA).
4. **New specialist** — only when no existing agent is a reasonable fit. See [New Specialist Policy](#new-specialist-policy).

Match by **capability**, not exact wording. Do not create new agents when an existing one covers the need.

## Decision Rubric

### Use a single agent when:
- One specialty dominates the task
- Work is sequential, no cross-checking needed
- Examples: "fix this bug" → `debugger`, "review this PR" → `reviewer`, "add a button" → `Dexter (engineer)`

### Use multiple agents in parallel when:
- Work splits into independent tracks with no inter-agent dependencies
- Main session can aggregate the results
- Examples:
  - PR review: `reviewer` (code quality) + `qa` (lint/build) + `ui-ux-reviewer` (visual check) — all in parallel
  - Bug triage: `debugger` (root cause) + a second agent searching for similar patterns
  - Post-implementation: `reviewer` + `qa` in parallel after engineer completes

### Escalate to orchestrator team when:
- Full SDLC workflow needed (design → plan → implement → review → QA)
- Agents need to coordinate directly (reviewer findings feed back to engineer)
- Parallel investigation needs synthesis from a lead
- Architecture, implementation, and validation should proceed with active coordination
- Use `WaLead (orchestrator/Tech Lead)` as the entry point — it handles the team lifecycle

### Create a new specialist only when:
- No existing agent is a reasonable fit (see full list above)
- Forcing an existing agent would materially reduce quality
- The new role is clearly scoped and justified
- The task is important enough to justify extra complexity

## Capability Mapping

Common task types → agent routing:

| Task | Primary Agent | Supporting Agents |
|------|--------------|-------------------|
| Bug fix (simple) | `Dexter (engineer)` | — |
| Bug fix (complex/blocked) | `debugger` | — |
| Code review | `reviewer` | `qa` for static checks |
| New feature (small) | `Dexter (engineer)` | `reviewer` after |
| New feature (large) | `WaLead (orchestrator/Tech Lead)` | Full team via orchestrator |
| UI change | `Dexter (engineer)` | `ui-ux-reviewer` after |
| Performance issue | `debugger` | — |
| Security audit | `reviewer` | — |
| Production incident | `debugger` | `reviewer` if auth/data angle |
| Refactoring | `Dexter (engineer)` | `reviewer` + `qa` after |
| Design + implement | `WaLead (orchestrator/Tech Lead)` | Uses @brainstorming, @writing-plans |

## Required Output

Before dispatching, produce this plan:

```markdown
### Dispatch Plan
- **Mode:** single agent | parallel agents | orchestrator team
- **Why:** <1-2 sentences justifying the mode>
- **Agents:** <list agent names>
- **Capability gaps:** none | <description>
- **New specialist needed:** no | yes — <justification>

### Execution
- **Lead:** <agent name>
- **Supporting:** <agent names or "none">
- **Coordination required:** yes/no
- **Expected deliverable:** <what comes back>
```

## Integration with Existing Workflow

- When dispatching to `Dexter (engineer)`, specify the **skill to load** and **target service** (from `project.yml` → `services[]`).
- When dispatching to `WaLead (orchestrator/Tech Lead)`, provide the brief — it handles the full SDLC internally using @brainstorming, @creating-userstories, @writing-plans, and @executing-plans.
- When dispatching to `reviewer` or `qa`, provide the feature directory path and target service path.
- When dispatching to `debugger`, provide the feature directory, engineer journal, and target service path.
- After any `Dexter (engineer)` dispatch, consider following up with `reviewer` → `qa` (the standard quality gate sequence).

## Hard Constraints

- Prefer existing agents over creating new ones.
- Prefer capability overlap over exact name matching.
- Keep the number of agents as small as effective.
- Do not create agents with vague or overlapping responsibilities.

## New Specialist Policy

If truly unavoidable, define:
- **name**: kebab-case
- **scope**: exact responsibilities
- **gap**: why existing agents are insufficient
- **tools**: what it needs
- **lifetime**: temporary (this task only) or persistent (add to `.claude/agents/`)

## Examples

**Example 1: "Review this PR"**
```
Mode: parallel agents
Agents: reviewer, qa
Why: independent review tracks, no coordination needed
```

**Example 2: "The login page is broken after the last deploy"**
```
Mode: single agent
Agent: debugger
Why: narrow bug, one specialty dominates
```

**Example 3: "Build a new admin dashboard for shift analytics"**
```
Mode: orchestrator team
Agent: WaLead (orchestrator/Tech Lead)
Why: large feature needs design → plan → implement → review → QA cycle
```

**Example 4: "I just restyled the requests page, check it looks good"**
```
Mode: parallel agents
Agents: ui-ux-reviewer, reviewer
Why: visual review + code quality in parallel, no coordination needed
```
