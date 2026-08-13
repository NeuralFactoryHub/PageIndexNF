---
name: first-use-checkpoint
description: Pause before applying a proposal that uses an unfamiliar library, framework, or CLI tool. Read the developer's global tool registry, surface prior usage if the tool is known, request explicit approval if not, and append the registry on approval.
---

# First-Use Checkpoint

## Overview

Defends the ownership principle stated in the developer's profile: the
developer must understand the tools that ship in code they own.
Accepting unfamiliar tooling unread feels fast but generates conceptual
debt. This skill enforces a pause-and-read moment before the agent
applies a proposal that introduces a new tool.

**Announce at start:** "I'm using the first-use-checkpoint skill to
verify familiarity with the proposed tooling."

## When to Invoke

An agent must invoke this skill when **about to propose** code or a
command that introduces:

- A new library (Python, JS/TS, or any other language)
- A new framework
- A new CLI tool the developer would run on their machine

Do NOT invoke for:

- Concepts or protocols (REST, JWT, OAuth, etc.)
- Standard-library imports of the language already in use (`os`, `sys`, `json`, `typing` in Python; `fs`, `path` in Node)
- Idioms or patterns of a framework the developer already uses
- Tools already used earlier in the same session — surface prior usage if registered, but do not re-checkpoint

## Grouping

When a single proposal introduces multiple new tools at once, present
them **as a block** for a single approval cycle rather than running the
checkpoint tool-by-tool. The developer can pick which tools to read
about and which to skip. This reduces friction without sacrificing the
principle.

## Identify the Current Project

Before reading or writing the registry, determine the canonical project
name (used to record where each tool was used):

1. Read `.claude/project.yml` → `project.name`. If present, use that.
2. Otherwise, derive the name from the basename of the repository root directory.
3. If neither is determinable, ask the developer: *"How would you like me to record this project in your tool registry?"*

## Read the Registry

The registry lives at `~/.claude/sdlc-harness/known-tools.md` (path
declared in the developer's profile, section 5.4).

- If the file does not exist, treat the registry as empty. Do NOT raise
  an error — proceed to the bootstrap flow described below.
- If the `~/.claude/sdlc-harness/` directory does not exist, create it
  when first writing to the registry.
- Use `$HOME` or shell expansion of `~` when accessing the file;
  hardcoded `/home/...` or `/Users/...` paths will not work for other
  developers.

## Pre-Check Logic

For each proposed tool:

1. Normalize the tool name (lowercase) for matching.
2. Search the registry for an exact name match (case-insensitive).
3. If found → branch to "Tool IS in the registry".
4. If not found → branch to "Tool NOT in the registry".

## Branch A — Tool IS in the Registry (surface actively)

Before applying the proposal, surface the prior usage to the developer:

> Example output (Spanish — match the developer's chat language as declared in their profile):
>
> *"`motor` ya está en tu registro: lo usaste en `jungheinrich-02-docriassuntivotecnici` en 2025-12. ¿Avanzo, o querés repasar la doc primero?"*

Then:

1. Wait for the developer's response.
2. If they approve advancing → proceed with the original proposal.
3. If they want to re-read the docs → surface the registered doc link, wait until they confirm they have read.
4. If the current project is NOT yet listed in this tool's history, append it with the current month-year — even if the developer skipped re-reading. Registries reflect usage, not re-reading.

## Branch B — Tool NOT in the Registry (full checkpoint)

1. Pause before applying the proposal.
2. Present to the developer:
   - The tool being proposed (name + one-line category)
   - What it will be used for in this specific case (1–2 sentences)
   - A direct link to the official documentation. Use the canonical entry point (homepage, "getting started", or quickstart). Do NOT invent links — if you do not know the official URL with confidence, say so and ask the developer to provide it.
3. Ask: *"¿Querés leer la doc primero o ya estás cómodo para avanzar?"* (or the equivalent in the developer's chat language).
4. Wait for the developer's explicit decision before proceeding. Do NOT advance based on assumptions.
5. Once the developer approves (either after reading or because they confirm familiarity), append a new entry to the registry:
   - Add a category header (e.g. `## Libraries / Frameworks`) if it does not yet exist.
   - Add the tool entry with name, one-line description, doc link, and current `YYYY-MM — project-name`.

## Bootstrap (First Invocation, Registry Does Not Exist)

If the registry file does not exist when this skill is first invoked:

1. Inform the developer: *"Your tool registry has not been created yet. Want me to populate it with the tools your profile already mentions, so we start from a useful baseline?"*
2. If yes:
   - Read the developer's profile, sections "Technical Comfort Map" and "Working Context — Stack" (names may vary by developer).
   - Extract every named library, framework, or CLI tool from those sections.
   - Present the inferred list to the developer in a single message for one-shot approval. Ask them to confirm, correct, or remove entries.
   - Create `~/.claude/sdlc-harness/` if it does not exist.
   - Write the validated entries to `~/.claude/sdlc-harness/known-tools.md`.
3. If no: create the file with only the top-level header and proceed with the current checkpoint normally.

## Registry File Format

```markdown
# Developer's Known Tools

Personal registry of libraries, frameworks, and CLI tools the developer
has confirmed familiarity with. Updated automatically by the
first-use-checkpoint skill and readable by the /known-tools command.

## Libraries / Frameworks

- **fastapi** — Python web framework. Docs: https://fastapi.tiangolo.com/
  - 2025-12 — jungheinrich-02-docriassuntivotecnici
- **pydantic** — Python data validation. Docs: https://docs.pydantic.dev/
  - 2025-12 — jungheinrich-02-docriassuntivotecnici

## CLI tools

- **docker** — containerization. Docs: https://docs.docker.com/
  - 2026-02 — some-project

## AI / ML

- **bedrock** — AWS LLM API. Docs: https://docs.aws.amazon.com/bedrock/
  - 2026-03 — some-project
```

**Categories.** Use natural-language category headings the developer will
recognize. Suggested defaults: `Libraries / Frameworks`, `CLI tools`,
`AI / ML`, `Databases`, `Infrastructure / Cloud`. The developer can
re-organize manually anytime; the skill respects any custom category
the developer has introduced.

**Entries.** One bullet per tool, with name, one-line description, doc
link. Sub-bullets list `YYYY-MM — project-name`, one per project where
the tool was used. Granularity: one entry per (tool, project), NOT per
(tool, project, feature).

**Sorting.** Within each category, entries are sorted alphabetically
by tool name. New entries are inserted in alphabetical position, not
appended at the end. Sub-bullets (project history) are sorted
chronologically, oldest first.

## Anti-Patterns

- Do NOT checkpoint standard-library imports of the language already in use.
- Do NOT checkpoint conceptual things (REST, JWT, OAuth, "an enum") — only concrete tools.
- Do NOT ask twice about the same tool in the same session.
- Do NOT write to the registry without explicit developer approval.
- Do NOT invent doc links. If unsure of the canonical official URL, say so and ask.
- Do NOT block trivial commits or routine operations — this skill is for *new* tooling, not for re-using a tool already used in the same session.
- Do NOT silently skip when a known tool reappears. The profile mandates "surface actively" — always mention prior usage so the developer is reminded.

## Related Skills / Commands

- The `/known-tools` command lets the developer query the registry manually (by name match or full listing).
- Profile section 5.4 contains the principle and the operational rules that this skill materializes.
