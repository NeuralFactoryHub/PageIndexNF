---
name: update-story-status
description: Updates a ClickUp task status for a user story. Use when starting, completing, or changing the status of a user story (e.g. "mark US-005 in progress", "close US-003"). Automatically invoked by other skills when story status changes.
---

# Update Story Status

Lightweight skill to push status changes for user stories to ClickUp.

**Announce at start:** "Updating ClickUp status for {US-ID}..."

---

## When to Use This Skill

- Agent starts implementing a user story → set **in progress**
- Agent finishes implementing a user story → set **closed**
- Agent or user explicitly changes story status
- Called automatically by `@executing-plans` at task boundaries

---

## Accepted Statuses

| Status keyword | ClickUp status | When to use |
|---------------|----------------|-------------|
| `planning` | planning | Story defined, not started |
| `in progress` | in progress | Implementation started |
| `review` | review | PR open / awaiting review |
| `closed` | closed | Implemented and verified |

---

## Workflow

### Step 1: Parse Input

Extract from the invocation:
- **US-ID**: e.g. `US-005` (required)
- **New status**: one of the accepted statuses above (required)

If either is missing, ask the user.

### Step 2: Look Up ClickUp Task ID

1. Read `docs/backlog/.clickup-sync.json`
2. Find the entry for the given US-ID
3. Extract `clickup_task_id`

If the US-ID is not found in sync state, **stop and warn** — the story hasn't been synced to ClickUp yet. Suggest running `@sync-clickup` first.

### Step 3: Get Workspace ID

Read workspace_id from `.claude/project.yml` under `integrations.clickup.workspace_id`.

### Step 4: Update ClickUp

Use `mcp__claude_ai_ClickUp__clickup_update_task`:

```
task_id: "{clickup_task_id}"
status: "{new_status}"
workspace_id: "{workspace_id}"
```

### Step 5: Update Sync State

Update the entry in `docs/backlog/.clickup-sync.json`:
- Set `last_synced` to current ISO 8601 timestamp
- Add or update `status` field with the new status

Write the updated file.

### Step 6: Confirm

Print a one-liner:
```
✓ {US-ID} → {new_status} (https://app.clickup.com/t/{task_id})
```

---

## Batch Mode

When updating multiple stories at once (e.g. closing an entire epic), accept a list of US-IDs and process them all. Make parallel ClickUp API calls when possible.

---

## Error Handling

- **Task not in sync state:** Warn and skip
- **ClickUp API error:** Log error, don't crash — report failed updates at the end
- **Invalid status:** Show accepted statuses and ask again

---

## Keywords

status, update, clickup, in progress, closed, review, planning, story status
