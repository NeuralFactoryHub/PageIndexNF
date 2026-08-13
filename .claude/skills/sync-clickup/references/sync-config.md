# Sync Configuration Reference

## Config File Location

`docs/backlog/.sync-config.json`

## Extracting IDs from ClickUp URL

Given a ClickUp list URL like:
```
https://app.clickup.com/{workspace_id}/v/li/{list_id}
```

Extract:
- **workspace_id**: first number after `app.clickup.com/`
- **list_id**: number after `/v/li/`

The `workspace_name`, `space_name`, and `list_name` are human-readable labels used in ClickUp API instructions to help Zapier resolve the correct targets.

## ClickUp API via Zapier MCP

The sync skill uses these Zapier MCP tools:

| Tool | Purpose |
|------|---------|
| `clickup_create_task` | Create new tasks from untracked stories |
| `clickup_update_task` | Update existing tasks when local content changes |
| `clickup_find_task_by_id` | Verify a task exists before updating |

### Create Task — Required Fields

The `clickup_create_task` tool requires these fields to be resolved (either via params or LLM guess from instructions):

| Field | How to provide |
|-------|---------------|
| **Workspace** (`team_id`) | Pass as `team_id` parameter |
| **Space** (`space_id`) | Mention space name in `instructions` — Zapier resolves it |
| **List** (`list_id`) | Mention list name AND ID in `instructions` — Zapier resolves it |
| **Task Name** (`name`) | Pass as `name` parameter |
| **Priority** (`priority`) | Pass as `priority` parameter (1=Urgent, 2=High, 3=Normal, 4=Low) |
| **Description** (`markdown`) | Pass as `markdown` parameter with full story content |

### Key Instruction Pattern

Always include workspace name, space name, list name, and list ID in the `instructions` field:

```
"Create a task in the {workspace_name} workspace. Space: {space_name}. List: {list_name} (list ID {list_id})."
```

This pattern has been tested and reliably resolves all required fields.

## Sync State File

`docs/backlog/.clickup-sync.json`

### Schema

```json
{
  "US-{NNN}": {
    "clickup_task_id": "string — ClickUp task ID (e.g., '86c8c737r')",
    "clickup_url": "string — full URL to the task",
    "last_synced": "string — ISO 8601 timestamp of last sync",
    "content_hash": "string — MD5 hash of the local .md file at sync time"
  }
}
```

### Content Hash

Generated via:
```bash
md5 -q <filepath>
```

On Linux use `md5sum <filepath> | cut -d' ' -f1` instead.

The hash detects local changes since last sync. If the hash matches, the story is skipped.
