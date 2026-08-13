---
description: Query the global tool registry. Without argument, lists the full registry. With argument (substring), filters and shows matching entries with prior usage.
---

# Known Tools

Read and display the developer's global tool registry. This command
NEVER modifies the registry — only reads it. Modifications happen
automatically via the `first-use-checkpoint` skill when a new tool is
approved.

## Registry Location

`~/.claude/sdlc-harness/known-tools.md`

Use shell expansion of `~` (or `$HOME`) when accessing. Never hardcode
an absolute path.

## Process

1. Read `~/.claude/sdlc-harness/known-tools.md`.
2. If the file does not exist or is effectively empty, respond (in the
   developer's chat language declared in their profile):
   > *"Tu registro de tools está vacío. Se va a poblar automáticamente a medida que uses el harness."*
   ...and stop.
3. Parse the argument (if any).
4. Branch on argument presence.

## With Argument (e.g. `/known-tools mongo`)

1. Match the argument against tool names in the registry — case-insensitive, substring match.
2. If no matches found, respond:
   > *"No encontré ningún tool que matchee `<arg>` en tu registro. Tu registro tiene N tools en total — corré `/known-tools` sin argumento para ver todo."*
3. If matches found, respond with:
   - Header: *"Matches for `<arg>`:"*
   - For each matching tool:
     - Tool name (bold)
     - One-line category / description
     - Docs link
     - History list (`YYYY-MM — project-name`, one per line)
   - Sort matches alphabetically.

## Without Argument (`/known-tools`)

Print the full registry, grouped by category exactly as stored in the file:

- Each category as a section header.
- Tools within the category in alphabetical order.
- For each tool, show name, description, docs link, and history.

Format the output as readable Markdown in chat. Do not paginate unless
the registry is unusually long (over ~50 tools).

## Language Convention

Match the chat language declared in the developer's profile. The
registry contents themselves are stored in English; the framing prose
around them (headings, error messages, conversational summaries)
adapts to the developer's chat language.

## Output Format Example

```
Matches for "mongo":

- **motor** — async MongoDB driver. Docs: https://motor.readthedocs.io/
  Used in:
    - 2025-12 — jungheinrich-02-docriassuntivotecnici
```

## Anti-Patterns

- Do NOT modify the registry. This command is read-only.
- Do NOT search by category name — only by tool name. If the developer wants to browse by category, they run `/known-tools` without argument.
- Do NOT invent or supplement information about tools not in the registry.
- Do NOT cache the registry between invocations. Always re-read from disk.

## Related

- The `first-use-checkpoint` skill (in `skills/first-use-checkpoint/`) is what *writes* to the registry. This command only reads.
- Profile section 5.4 documents the principle behind the registry and the path convention.
