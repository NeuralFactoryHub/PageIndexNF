# Personal SDLC Harness

A `.claude/`-based harness for an opinionated software development lifecycle.
Drops into any project to provide a team of specialized agents, stack-specific
skills, slash-invokable workflows, and a per-developer profile that adapts
agent behavior to the human in the seat.

The harness has two intertwined missions:

1. Ship correct, well-engineered code
2. Grow the developer's technical depth in the process

Both matter equally.

---

## Installation in a project

Per-project copy. Each project has its own `.claude/` folder containing the
harness.

1. Copy the contents of this folder to `.claude/` in the target project
2. Verify `.claude/.gitignore` made it across (it ignores `profile.md`)
3. On first use, the orchestrator will detect that `.claude/profile.md` is missing and prompt you to run `/build-profile`

If multiple developers work on the same project, each one keeps their own
local `.claude/profile.md`. The file is gitignored, so personal profiles
never travel through the team's repo.

---

## What's in the harness

### Agents (`agents/`)

| Agent | Role |
|---|---|
| `orchestrator` | Tech lead — never writes code; decomposes, assigns, monitors |
| `engineer` | The only agent that writes implementation code |
| `reviewer` | 3-layer code review |
| `qa` | Lint, build, integration coherence, acceptance-criteria walkthrough |
| `debugger` | 6-phase systematic debugging when the engineer is blocked |
| `ui-ux-reviewer` | Visual design + UX + WCAG accessibility audit |

Every agent reads `.claude/profile.md` at the start of a session and adapts
its tone, depth, and pedagogical strategy to the active developer.

### Commands (`commands/`)

Slash-invokable workflows. Highlights:

- `/build-profile` — interactively build `.claude/profile.md` via Socratic interview
- `/implement` — run the full SDLC end-to-end (use only for non-trivial features)
- `/brainstorm` — Socratic design refinement
- `/write-plan` and `/execute-plans` — produce and execute bite-sized implementation plans
- `/gh-commit` — conventional-commit-aware commit
- `/gh-review-pr` — pre-PR review (with PR readiness coaching when the profile asks for it)
- `/project-init` — generate `.claude/project.yml` by scanning the codebase

See each file in `commands/` for the full list.

### Skills (`skills/`)

Stack-specific and methodological knowledge bundles. The engineer loads
the appropriate skill on demand based on the work type. Examples:
`backend-python`, `frontend-nextjs`, `brainstorming`, `writing-plans`,
`executing-plans`, `creating-userstories`, `sync-clickup`.

### SDLC (`SDLC.md`)

The end-to-end workflow specification — brainstorm → design → user stories
→ plan → branching → implementation → review → QA → PR → release →
post-release. The orchestrator follows this when running `/implement`.

---

## The developer profile (`.claude/profile.md`)

The single most important file for the harness's teaching mode. It tells
every agent who they are working with so they can adapt their tone, depth
of explanation, and pedagogical strategy.

**Where it lives:** `.claude/profile.md` inside the project. Gitignored.
Each developer maintains their own local copy.

**How to create it:**
- Run `/build-profile` — interactive Socratic interview that produces a profile tailored to you (recommended).
- Or write it by hand using the anatomy below as a guide.

**When to update it:** every 3–6 months, after a significant role change,
or whenever you notice that agents are calibrating to the wrong level.

**Privacy:** the profile contains personal information (background,
technical gaps, frustrations, preferences). Do not commit it. The harness's
`.claude/.gitignore` already enforces this.

---

## Anatomy of a useful profile

There is no fixed template — two developers' profiles can have wildly
different shapes. The dimensions below have proven useful in practice;
skip the ones that do not apply, add new ones as needed, and order them
however makes sense.

**Identity & background.** Who you are, where you come from technically,
what your training and career trajectory have been. Helps agents
understand which assumptions to make and which to drop.

**Strengths to leverage.** What you bring that is distinctive — prior
domain expertise, unusual learned habits, angles that complement pure
technical depth. Agents can reach for these as analogical anchors when
explaining new concepts.

**Technical comfort map.** What you are solid in, what you are
consolidating, what you have not learned yet. The most operational
section — agents calibrate explanation depth directly off this.

**Growth priorities (next 3–6 months).** What you want to deepen. Agents
treat these as bonus pedagogical opportunities: when work touches one of
these areas, they slow down and explain more.

**Learning style.** How concepts land for you — analogies, first
principles, concrete examples, hands-on exploration, reading good code.
Different developers have very different preferences here.

**Friction points.** What frustrates you when being taught — jargon
without definition, code without rationale, walls of text, advancing
without checking comprehension. Agents avoid these proactively.

**Feedback delivery preferences.** How you want corrections — direct,
contextual, Socratic, or a mix calibrated by severity. The reviewer and
debugger tune their voice off this.

**Working context.** Team size, technical lead, how you engage with that
lead, what role you want the harness to play in that relationship.
Especially relevant for agents like the reviewer, which can prepare you
for the lead's PR review questions.

**Output language conventions.** What language to use in chat vs. in
repository artifacts vs. in code comments. Most useful when the
developer's native language differs from the team's working language.

---

## Updating the harness

The harness distributes by per-project copy. When this folder evolves,
sync each project's `.claude/` manually.

Files that should NEVER be overwritten on sync:

- `.claude/profile.md` (personal, gitignored)
- `.claude/project.yml` (project-specific, generated by `/project-init`)

Everything else can be safely overwritten.

---

## Language conventions

| Surface | Language |
|---|---|
| Code and code comments | English |
| Repository artifacts (design.md, plan.md, journals, validation reports) | English |
| Harness files (agents, commands, skills, this README) | English |
| Chat with the developer | The developer's native language, declared in their profile |
