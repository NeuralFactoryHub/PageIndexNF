---
name: sync-clickup
description: Synchronizes user stories from docs/backlog/ to a ClickUp list. Creates new tasks for untracked stories, updates existing tasks when local content changes, and reports sync status. Use when asked to "sync to clickup", "push stories to clickup", "update clickup", or "sync user stories".
---

# Sync User Stories to ClickUp

You are a DevOps automation assistant. Your job is to synchronize user story markdown files from the local repository to a ClickUp task list, keeping both sides in sync.

**Announce at start:** "I'm using the sync-clickup skill to synchronize user stories with ClickUp."

---

## When to Use This Skill

- User says "sync to clickup", "push stories to clickup", "update clickup tasks"
- User wants to create ClickUp tasks from local user story files
- User wants to update ClickUp tasks after editing local user story files
- User asks to check sync status between local stories and ClickUp

---

## Prerequisites

### Sync Config File

The sync config lives at `docs/backlog/.sync-config.json`. It contains ClickUp target coordinates:

```json
{
  "workspace_id": "<your-workspace-id>",
  "workspace_name": "<your-workspace-name>",
  "space_name": "<your-space-name>",
  "list_id": "<your-list-id>",
  "list_name": "<your-list-name>",
  "default_assignee": "user@example.com",
  "default_status": "planning"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `workspace_id` | Yes | ClickUp workspace/team ID |
| `workspace_name` | Yes | Human-readable workspace name for API instructions |
| `space_name` | Yes | Space name for API instructions |
| `list_id` | Yes | Target list ID |
| `list_name` | Yes | Human-readable list name for API instructions |
| `default_assignee` | No | Email to assign all new/updated tasks to |
| `default_status` | No | Status to set on new tasks (e.g. `"planning"`, `"backlog"`) |

If this file doesn't exist, **stop and ask the user** for the ClickUp list URL. Extract IDs from the URL format:
`https://app.clickup.com/{workspace_id}/v/li/{list_id}`

Then create the config file before proceeding.

### Sync State File

The sync state lives at `docs/backlog/.clickup-sync.json`. It tracks which local stories are mapped to ClickUp tasks:

```json
{
  "US-001": {
    "clickup_task_id": "86c8c737r",
    "clickup_url": "https://app.clickup.com/t/86c8c737r",
    "last_synced": "2026-02-20T14:47:44Z",
    "content_hash": "a1b2c3..."
  }
}
```

If this file doesn't exist, create it as `{}` — all stories will be treated as new.

---

## Workflow

### Step 1: Load Configuration

1. Read `docs/backlog/.sync-config.json` — if missing, ask user for ClickUp list URL and create it
2. Read `docs/backlog/.clickup-sync.json` — if missing, initialize as `{}`
3. Glob `docs/backlog/US-*.md` to find all local story files

### Step 2: Parse Each Story File

For each `US-*.md` file, extract:

| Field | How to extract |
|-------|---------------|
| **US ID** | From filename: `US-001-some-slug.md` → `US-001` |
| **Title** | First `###` heading, e.g. `### US-001: Add context menu...` → full heading text |
| **Priority** | Line starting with `**Priority:**` → map: Must=High(2), Should=Normal(3), Could=Low(4) |
| **Size** | Line starting with `**Size:**` → kept in description only |
| **Full content** | The entire file content — used as the task markdown description |
| **Dependencies** | Line starting with `**Dependencies:**` — kept in description only |

### Step 3: Compute Content Hash

For each story, compute a simple content hash to detect changes:

```bash
md5 -q docs/backlog/US-001-*.md
```

Compare against `content_hash` in sync state. If different → needs update.

### Step 4: Classify Stories

Sort each story into one of three buckets:

| Bucket | Condition | Action |
|--------|-----------|--------|
| **New** | US ID not in sync state | Create task in ClickUp |
| **Modified** | US ID in sync state but hash differs | Update task in ClickUp |
| **Unchanged** | US ID in sync state and hash matches | Skip |

Report the classification to the user before proceeding:

```
Sync plan:
  - CREATE: US-005, US-006 (2 new stories)
  - UPDATE: US-002 (content changed)
  - SKIP: US-001, US-003, US-004 (unchanged)

Proceed?
```

**Wait for user confirmation before executing.**

### Step 5: Resolve Assignee

If `default_assignee` is set in config, resolve the email to a ClickUp user ID using `mcp__claude_ai_ClickUp__clickup_resolve_assignees`:

```
assignees: ["{default_assignee_email}"]
workspace_id: "{workspace_id}"
```

Cache the returned `userIds[0]` for all subsequent create/update calls.

### Step 6: Execute Sync

Read `default_assignee` and `default_status` from the sync config. These are optional — if present, include them in every create/update call.

**Prefer the native ClickUp MCP tools** (`mcp__claude_ai_ClickUp__*`) over Zapier tools — they accept structured parameters directly and are more reliable.

#### For NEW stories — use `mcp__claude_ai_ClickUp__clickup_create_task`:

```
name: "{title}"
list_id: "{list_id}"
priority: "{priority}"          # "urgent" | "high" | "normal" | "low"
status: "{default_status}"      # from config, e.g. "planning"
assignees: ["{user_id}"]        # resolved user ID
markdown_description: "{full file content}"
workspace_id: "{workspace_id}"
```

After creation, capture `task_id` and `task_url` from the response.

#### For MODIFIED stories — use `mcp__claude_ai_ClickUp__clickup_update_task`:

```
task_id: "{clickup_task_id}"
status: "{default_status}"
assignees: ["{user_id}"]
markdown_description: "{full file content}"
workspace_id: "{workspace_id}"
```

### Step 7: Update Sync State

After each successful create/update, update `docs/backlog/.clickup-sync.json`:

```json
{
  "US-001": {
    "clickup_task_id": "86c8c737r",
    "clickup_url": "https://app.clickup.com/t/86c8c737r",
    "last_synced": "2026-02-20T15:30:00Z",
    "content_hash": "d4e5f6..."
  }
}
```

Write the updated sync state file after all operations complete.

### Step 8: Report

Print a summary table:

```
Sync complete:

| Story | Action | ClickUp Task | URL |
|-------|--------|-------------|-----|
| US-001 | skipped | 86c8c737r | https://app.clickup.com/t/86c8c737r |
| US-005 | created | 86c8c79xx | https://app.clickup.com/t/86c8c79xx |
| US-002 | updated | 86c8c73ty | https://app.clickup.com/t/86c8c73ty |
```

---

## Priority Mapping

| Local Priority | ClickUp Priority | Value |
|---------------|-----------------|-------|
| Must | Urgent | 1 |
| Should | High | 2 |
| Could | Normal | 3 |
| Won't | Low | 4 |

---

## Error Handling

- **ClickUp API fails for one story:** Log the error, skip it, continue with remaining stories. Report failures at the end.
- **Config file missing:** Stop and ask user — never guess workspace/list IDs.
- **Story file has no parseable title:** Use filename as fallback title, warn user.
- **Sync state corrupted:** Re-initialize as `{}` (all stories re-created — ClickUp handles duplicates by different task IDs).

---

## Behavior Guidelines

- **Always confirm before executing** — show the sync plan first
- **Never delete ClickUp tasks** — sync is additive only (create + update, never delete)
- **Preserve sync state** — always write the updated state file after operations
- **One story = one ClickUp task** — never merge or split stories during sync
- **Idempotent** — running sync twice with no local changes should produce no ClickUp API calls
- **Git-friendly** — the `.clickup-sync.json` file should be committed so the team shares sync state

---

## Related Skills

- `@creating-userstories` — generates the user story files that this skill syncs
- `@writing-plans` — plans may reference user stories by US-ID

---

## Keywords

sync, clickup, user stories, push, synchronize, tasks, backlog, project management
