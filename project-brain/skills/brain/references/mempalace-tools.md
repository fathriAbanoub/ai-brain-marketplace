# MemPalace Tool Reference

This document catalogs all 47 MemPalace MCP tools with their exact schemas, usage policies for project-brain, and verified call recipes.

> Version: 3.11.0 (installed)
> Generated: 2026-10-20

## Tool Summary Table

| Tool | Description | Arguments | Access | Policy |
|------|-------------|-----------|--------|--------|
| status | Verify MemPalace is running and check index health | none | read | **USE** |
| list_wings | List all wings in the palace | none | read | **USE** |
| list_rooms | List rooms within a wing | wing (required) | read | **USE** |
| get_taxonomy | Get wing/room naming conventions | none | read | **USE** |
| get_aaak_spec | Read AAAK spec if configured | none | read | OPTIONAL |
| search | Full-text + semantic search | query, wing?, room?, limit?, max_distance? | read | **USE** |
| get_drawer | Read a specific drawer by ID | drawer_id | read | **USE** |
| get_drawers | Read multiple drawers by ID | drawer_ids (array) | read | **USE** |
| list_drawers | List drawers in a wing/room | wing, room?, limit?, offset? | read | **USE** |
| diary_read | Read diary entries by agent | agent_name, since?, before?, limit? | read | **USE** |
| diary_write | Write a diary entry | agent_name, entry (required), topic? | write | **USE** |
| add_drawer | Write a new drawer | wing, room?, content (required), source_file? | write | **USE** |
| update_drawer | Overwrite existing drawer | drawer_id, content?, wing?, room? | write | ASK FIRST |
| delete_drawer | Delete a drawer by ID | drawer_id | destructive | ASK FIRST |
| delete_drawers | Delete multiple drawers | drawer_ids (array) | destructive | ASK FIRST |
| check_duplicate | Check for near-identical content | content, threshold? | read | **USE** |
| mine | Mine a directory into a wing | source (required), wing?, mode?, include_ignored?, agent?, limit?, dry_run? | write | **USE** (wiki only) |
| sync | Sync palace with gitignored files | project_dir?, wing?, apply? | write | ASK FIRST |
| delete_by_source | Delete drawers from a source_file | source_file, dry_run? | destructive | ASK FIRST |
| hook_settings | Read/write hook config | desktop_toast?, silent_save? | write | MEMPALACE OWNED |
| memories_filed_away | Check recent filing activity | none | read | MEMPALACE OWNED |
| reconnect | Reconnect to palace backend | none | write | MEMPALACE OWNED |
| kg_query | Query knowledge graph facts | entity, direction?, as_of? | read | OPTIONAL |
| kg_add | Add a knowledge graph fact | subject, predicate, object, valid_from?, valid_to?, source_file? | write | OPTIONAL |
| kg_invalidate | Mark a fact as invalid | subject, predicate, object, ended? | write | OPTIONAL |
| kg_supersede | Replace fact with successor | subject, predicate, old_object, new_object, at? | write | OPTIONAL |
| kg_timeline | Show fact history | entity?, limit?, offset? | read | OPTIONAL |
| kg_stats | Get KG statistics | none | read | OPTIONAL |
| traverse | Walk connected drawers from a start | start_room, max_hops? | read | DO NOT USE |
| find_tunnels | Find tunnels to/from a drawer | wing_b?, wing_a? | read | DO NOT USE |
| graph_stats | Get drawer graph statistics | none | read | DO NOT USE |
| create_tunnel | Create cross-wing link | source_wing, source_room, target_wing, target_room, label? | write | DO NOT USE |
| list_tunnels | List all tunnels | wing? | read | DO NOT USE |
| delete_tunnel | Delete a tunnel | tunnel_id | destructive | DO NOT USE |
| list_hallways | List within-wing co-occurrence links | wing?, limit?, offset? | read | DO NOT USE |
| delete_hallway | Delete a hallway | hallway_id | destructive | DO NOT USE |
| follow_tunnels | Traverse tunnel graph | wing, room | read | DO NOT USE |
| mesh_peers | Get sync/peer status | none | read | DO NOT USE |
| event_append | Post event to logstream | type, stream, room, from_agent, body?, metadata?, topic?, status?, to_agent?, correlation_id?, branch?, base_commit?, artifact_ids? | write | DO NOT USE |
| event_list | List logstream events | type?, stream?, room?, topic?, writer?, to_agent?, correlation_id?, status?, since_event_id?, before_event_id?, limit?, order?, preview?, since_created_at? | read | DO NOT USE |
| event_wait | Long-poll for events | type?, stream?, room?, topic?, writer?, to_agent?, correlation_id?, since_event_id?, timeout_ms?, limit? | read | DO NOT USE |
| event_ack | Acknowledge an event | event_id, from_agent, body?, status?, topic? | write | DO NOT USE |
| task_create | Create delegated task | project, from_agent, to_agent, goal, branch, base_commit, done | write | DO NOT USE |
| artifact_put | Store artifact | kind, content, created_by, metadata? | write | DO NOT USE |
| artifact_get | Retrieve artifact | artifact_id | read | DO NOT USE |
| patch_submit | Submit patch to spec | content, stream, from_agent, branch?, topic?, correlation_id?, body?, room?, base_commit?, to_agent?, metadata? | write | DO NOT USE |
| checkpoint | Save session in one call | items (array), diary?, added_by?, dedup_threshold? | write | DO NOT USE |

## Policy Definitions

- **USE**: Safe to call in normal project-brain workflows
- **OPTIONAL**: Only where the plugin already uses them today (kg_query, kg_add)
- **ASK FIRST**: Confirm with user before calling (delete, sync, update operations)
- **DO NOT USE**: Not needed for project-brain; may conflict with other uses
- **MEMPALACE OWNED**: Managed by MemPalace's own hooks, never call from project-brain

## Call Recipes

### 1. Preflight Check (before any MemPalace write)

```
mempalace_status
```

If the vector index is disabled or diverged:
- Stop writing to MemPalace
- Tell the user: "Run `mempalace repair rebuild-index` in a terminal with agents closed"
- Continue brain work without MemPalace

### 2. Recall Before Claims (at wake-up/orient)

```
mempalace_search({
  query: "<project-name> decisions preferences",
  limit: 10
})
```

### 3. Sync the Wiki (after wiki edits)

```
mempalace_mine({
  source: "<project-root>/.brain/wiki",
  wing: "wiki-<project-slug>",
  mode: "projects",
  include_ignored: [".brain/wiki"],  # if .brain is gitignored
  dry_run: false
})
```

**IMPORTANT**: Mine only `.brain/wiki/` directory, not `.brain/raw/`, `.brain/state/`, `.brain/log/`, or the repo itself.

### 4. Write Session Diary (at handoff)

```
mempalace_diary_write({
  agent_name: "brain-<project-slug>",
  entry: "[DATE] | [PROJECT] | [ACTION]\nSummary: ...\nKey finding: ...\nContradictions: ...\nLog: ...\nNext: ...",
  topic: "session-diary"
})
```

The diary entry format follows `references/mempalace-workflow.md`:
```
[DATE] | [PROJECT] | [ACTION]
Summary: [1-2 sentences]
Key finding: [most important discovery]
Contradictions: [source conflicts or "none"]
Log: [path to session log]
Next: [priority action]
```

### 5. Read Diary at Wake-up

```
mempalace_diary_read({
  agent_name: "brain-<project-slug>",
  limit: 5
})
```

## Wing Naming Constants

Per D3 in the specification:
- Wiki wing: `wiki-<project-slug>`
- Diary agent: `brain-<project-slug>`

`<project-slug>` is derived from `sanitize_wing_name(title)` in `scaffold_brain.py`:
- Lowercase
- Replace runs of `[^a-z0-9._-]` with `-`
- Collapse repeated hyphens
- Strip leading/trailing `-._`
- Underscores are preserved

## Uninstalled Tools (NOT available)

These tools were referenced in older documentation but are NOT in the 47-tool set:

- `mempalace_preferences_get` — Use wiki page or diary instead
- `mempalace_preferences_set` — Use wiki page or diary instead

## Notes

- The mine tool respects .gitignore by default. Use `include_ignored` if `.brain/` is gitignored.
- Re-mining a directory replaces old drawers with new content (same wing/room).
- Deleted wiki pages leave stale drawers; deleting them requires user confirmation (ASK FIRST policy).
- The vector index health check is in `mempalace_status` response under `index_enabled` and `index healthy`.
