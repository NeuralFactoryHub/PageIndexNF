---
description: Interactively build .claude/profile.md from scratch via a Socratic interview.
---

# Build Developer Profile

Conduct a Socratic interview with the developer to produce a personalized
`.claude/profile.md` that the harness's agents will read at the start of
every session.

## When to Use

- Onboarding a developer to a project that uses this harness for the first time
- An existing developer wants to rebuild or update their profile
- The orchestrator detected that `.claude/profile.md` is missing and prompted the developer to run this command

## Pre-Check

1. Check whether `.claude/profile.md` already exists.
2. If it exists:
   - Summarize its top-level structure (section headings) for the developer
   - Ask: "An existing profile was found. What do you want to do?"
     - **Replace** — overwrite at the end with a fresh profile
     - **Extend** — add new sections or refine existing ones without discarding what's already there
     - **Cancel** — exit without changes
3. If it does not exist, proceed to the announcement.

## Announcement (first turn)

Before asking any question, announce the following to the developer:

> I'm going to interview you to build your developer profile. Expect about
> 8–10 questions, asked one at a time. After every few answers I'll show you
> a validated block in English (the file format) for you to approve before
> I move on. You can pause, edit, or course-correct at any moment. The
> interview happens in your native language; the file content is in English
> by harness convention. Ready to start?

Wait for explicit confirmation before asking the first question.

## Interview Rules

- **One question per message.** Never bundle two questions into one turn.
- **Prefer multiple-choice when meaningful;** open-ended only when discrete options would feel artificial.
- **Reflect back what you heard.** After each substantive answer, summarize in one or two sentences before moving on, so the developer can correct misinterpretations.
- **Show validated blocks in English progressively.** Do NOT wait until the end. The developer approves each block before you move on.
- **Adapt depth.** If the developer is clearly senior, do not invent gaps or over-explain. If they are newer to the field, slow down and add scaffolding.
- **Respect declines.** If a developer does not want to cover a dimension, drop it without pressure.

## Suggested Dimensions to Cover

These are *suggestions*, not a fixed schema. Use them as a starting menu
and adapt to what each developer brings. Skip dimensions that do not
apply, add new ones the developer raises, and reorder freely.

1. **Identity & background** — name, age, education, career trajectory, current role
2. **Strengths to leverage** — what the developer brings that is distinctive (prior domain expertise, learned habits, unusual angles)
3. **Technical comfort map** — what they are solid in, what they are consolidating, what they do not know yet
4. **Growth priorities (next 3–6 months)** — areas to deepen, with formal-study legs if any (courses, books, mentors)
5. **Learning style** — what makes a concept land for them (analogies, first principles, concrete examples, hands-on, reading good code)
6. **Friction points** — what frustrates them when being taught (jargon without definition, code without rationale, walls of text, no comprehension checks, etc.)
7. **Feedback delivery preferences** — how they want corrections delivered (direct, contextual, Socratic, mix by severity)
8. **Working context** — team size, technical lead, how they currently engage with that lead, where the harness should fit in that relationship
9. **Output language conventions** — chat vs. repository artifacts vs. code comments

After the standard set, always ask:

> "Is there any dimension you want to capture that I haven't asked about?"

## Building the File Incrementally

Maintain a working draft as the interview progresses. After all blocks are
validated, assemble the final file with:

- A short header explaining the file's purpose ("This file describes the developer all agents in this harness are working with. Read this before starting any work...")
- The validated blocks in the order the developer settled on
- A short closing section with operational rules for agents (how they should use the file)
- A footer with version status ("living document — revise as the developer grows or as work patterns shift") and the current date

## Output

Write the final file to `.claude/profile.md` in the current project. Then
confirm to the developer:

> Profile written to `.claude/profile.md`. The harness will load it at the
> start of every agent session. You can edit it manually anytime, or run
> `/build-profile` again and choose "Extend" to add more.

## Behavior Guidelines

- **File content is in English** regardless of the interview language — harness convention for agent-readable artifacts
- **No structural template is imposed** — two developers' profiles can have wildly different shapes
- **Never commit the resulting file** — it is gitignored by harness convention (`.claude/.gitignore` declares `profile.md`)
- **The interview itself is part of the product** — a good interview teaches the developer which dimensions matter, even if they later edit the file by hand

## Anti-Patterns to Avoid

- Bundling multiple questions in one turn
- Copying another developer's profile shape verbatim onto a new developer
- Skipping incremental validation ("I'll show you everything at the end")
- Pushing a developer to cover dimensions they explicitly declined
- Producing a wall-of-text final file without sectioning
- Asking the developer to fill a fixed template — always derive structure from what they say
