# MemPalace Tool Reference

This document catalogs all 47 MemPalace MCP tools with their exact schemas, usage policies for project-brain, and verified call recipes.

> Version: 3.11.0 (installed)
> Generated: 2026-10-20

## Tool Summary Table

> Argument lists verified against 3.11.0 schemas from mcp-tools.json. **bold** = required.

| Tool | Description | Arguments | Access | Policy |
|------|-------------|-----------|--------|--------|
| status | Check MemPalace is running and vector index health | none | read | **USE** |
| list_wings | List all wings in the palace | none | read | **USE** |
| list_rooms | List rooms within a wing | wing? | read | **USE** |
| get_taxonomy | List all wings and rooms with drawer counts | none | read | **USE** |
| get_aaak_spec | Read AAAK spec if configured | none | read | OPTIONAL |
| search | Full-text + semantic search | **query?**, limit?, wing?, room?, source_file?, since?, before?, max_distance?, candidate_strategy?, cli_compatible?, include_media?, query_task?, context? | read | **USE** |
| get_drawer | Read a specific drawer by ID | **drawer_id?** | read | **USE** |
| get_drawers | Read multiple drawers by ID | **drawer_ids?** | read | **USE** |
| list_drawers | List drawers in a wing/room | wing?, room?, since?, before?, limit?, offset? | read | **USE** |
| diary_read | Read diary entries by agent | **agent_name?**, last_n?, wing? | read | **USE** |
| diary_write | Write a diary entry | **agent_name?**, entry?, topic?, wing?, content? | write | **USE** |
| add_drawer | Write a new drawer | **wing?**, **room?**, **content?**, source_file?, added_by? | write | **USE** |
| update_drawer | Overwrite existing drawer | **drawer_id?**, content?, wing?, room? | write | ASK FIRST |
| delete_drawer | Delete a drawer by ID | **drawer_id?** | destructive | ASK FIRST |
| delete_drawers | Delete multiple drawers | **drawer_ids?** | destructive | ASK FIRST |
| check_duplicate | Check for near-identical content | **content?**, threshold? | read | **USE** |
| mine | Mine a directory into a wing | **source?**, mode?, wing?, agent?, limit?, dry_run?, extract?, include_ignored?, include_subagents? | write | **USE** (wiki only) |
| sync | Sync palace with gitignored files | project_dir?, wing?, apply? | write | ASK FIRST |
| delete_by_source | Delete drawers from a source_file | **source_file?**, dry_run? | destructive | ASK FIRST |
| hook_settings | Read/write hook config | silent_save?, desktop_toast? | write | MEMPALACE OWNED |
| memories_filed_away | Check recent filing activity | none | read | MEMPALACE OWNED |
| reconnect | Reconnect to palace backend | none | write | MEMPALACE OWNED |
| kg_query | Query knowledge graph facts | **entity?**, as_of?, direction? | read | OPTIONAL |
| kg_add | Add a knowledge graph fact | **subject?**, **predicate?**, **object?**, valid_from?, valid_to?, source_closet?, source_file?, source_drawer_id? | write | OPTIONAL |
| kg_invalidate | Mark a fact as invalid | **subject?**, **predicate?**, **object?**, ended? | write | OPTIONAL |
| kg_supersede | Replace fact with successor | **subject?**, **predicate?**, **old_object?**, **new_object?**, at? | write | OPTIONAL |
| kg_timeline | Show fact history | entity?, limit?, offset? | read | OPTIONAL |
| kg_stats | Get KG statistics | none | read | OPTIONAL |
| traverse | Walk connected drawers from a start | **start_room?**, max_hops? | read | DO NOT USE |
| find_tunnels | Find tunnels to/from a drawer | wing_a?, wing_b? | read | DO NOT USE |
| graph_stats | Get drawer graph statistics | none | read | DO NOT USE |
| mesh_peers | Get sync/peer status | none | read | DO NOT USE |
| create_tunnel | Create cross-wing link | **source_wing?**, **source_room?**, **target_wing?**, **target_room?**, label?, source_drawer_id?, target_drawer_id? | write | DO NOT USE |
| list_tunnels | List all tunnels | wing? | read | DO NOT USE |
| delete_tunnel | Delete a tunnel | **tunnel_id?** | destructive | DO NOT USE |
| list_hallways | List within-wing co-occurrence links | wing?, limit?, offset? | read | DO NOT USE |
| delete_hallway | Delete a hallway | **hallway_id?** | destructive | DO NOT USE |
| follow_tunnels | Traverse tunnel graph | **wing?**, **room?** | read | DO NOT USE |
| event_append | Post event to logstream | **type?**, **stream?**, **room?**, topic?, **from_agent?**, to_agent?, correlation_id?, branch?, base_commit?, status?, body?, metadata?, artifact_ids? | write | DO NOT USE |
| event_list | List logstream events | stream?, room?, topic?, type?, to_agent?, from_agent?, writer?, correlation_id?, status?, since_event_id?, before_event_id?, since_created_at?, limit?, order?, preview? | read | DO NOT USE |
| event_wait | Long-poll for events | stream?, room?, topic?, type?, to_agent?, from_agent?, writer?, correlation_id?, status?, since_event_id?, since_created_at?, timeout_ms?, limit? | read | DO NOT USE |
| event_ack | Acknowledge an event | **event_id?**, **from_agent?**, status?, body?, topic? | write | DO NOT USE |
| task_create | Create delegated task | **project?**, **from_agent?**, **to_agent?**, **goal?**, **branch?**, **base_commit?**, **done?** | write | DO NOT USE |
| artifact_put | Store artifact | **kind?**, **content?**, **created_by?**, metadata? | write | DO NOT USE |
| artifact_get | Retrieve artifact | **artifact_id?** | read | DO NOT USE |
| patch_submit | Submit patch to spec | **content?**, **from_agent?**, **stream?**, room?, topic?, to_agent?, correlation_id?, branch?, base_commit?, body?, metadata? | write | DO NOT USE |
| checkpoint | Save session in one call | **items?**, diary?, dedup_threshold?, added_by? | write | DO NOT USE |

## Policy Definitions

- **USE**: Safe to call in normal project-brain workflows
- **OPTIONAL**: Only where the plugin already uses them today (kg_query, kg_add)
- **ASK FIRST**: Confirm with user before calling (delete, sync, update operations)
- **DO NOT USE**: Not needed for project-brain; may conflict with other uses
- **MEMPALACE OWNED**: Managed by MemPalace's own hooks, never call from project-brain

The DO NOT USE coordination tools (`event_*`, `task_create`, `patch_submit`) are
governed by MemPalace's own `mempalace rules` command, not by project-brain. If a
user asks about agent coordination, point them at `mempalace rules` rather than
wiring the tools into the brain workflow.

## The `sync` tool is dangerous

`sync` bulk-ingests **gitignored** files into the palace. That is the opposite
of what project-brain needs: the brain mines `.brain/wiki/` deliberately, but
`sync` sweeps in whatever git is ignoring — `.env` files, local caches, build
output, credentials, scratch notes.

Rules:

- Never call `sync` without explicit user confirmation.
- Always pass a scoped `wing` (and `project_dir`) — never sync the repo root implicitly.
- Preview first: `apply: false` (or `dry_run`) and show the user what would be ingested.
- If `sync` already ran, treat it as a possible secret leak and tell the user immediately.

For normal wiki-to-memory updates use Recipe 3 (`mempalace mine .brain/wiki`), not `sync`.

## Concurrency

MemPalace has no compare-and-swap on drawers. Two sessions writing at the same
time can both pass `check_duplicate` and then both write, leaving near-identical
drawers. It is last-write-wins on `update_drawer`.

- Treat `check_duplicate` as advisory, not a lock.
- Do not run two sessions against the same wing concurrently.
- If a duplicate slips through, delete the extra drawer (ASK FIRST) rather than
  editing both.

## Call Recipes

### 1. Preflight Check (before any MemPalace write)

```
mempalace_status
```

If `vector_disabled` is true:
- Stop writing to MemPalace
- Tell the user: "Run `mempalace repair rebuild-index` in a terminal with agents closed"
- Continue brain work without MemPalace

When MCP is unavailable, use the CLI fallback (Recipe 6): `mempalace repair-status`
for index health and `mempalace status` for server health.

### 2. Recall Before Claims (at wake-up/orient)

```
mempalace_search({
  query: "<project-name> decisions preferences",
  limit: 10
})
```

### 3. Sync the Wiki (after wiki edits)

```
mempalace mine .brain/wiki --wing wiki-<project-slug> --mode projects
```

If `.brain/` is gitignored, add `--include-ignored .brain/wiki`:

```
mempalace mine .brain/wiki --wing wiki-<project-slug> --mode projects --include-ignored .brain/wiki
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
  last_n: 5
})
```

### 6. Preflight Index Health (CLI fallback)

When MCP is unavailable, use the CLI for preflight checks:

```
mempalace repair-status
mempalace status
```

## Wing Naming Constants

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
- Re-mining a directory replaces old drawers with new content (same wing/room). [unverified]
- Deleted wiki pages leave stale drawers; deleting them requires user confirmation (ASK FIRST policy).
- The vector index health check uses `vector_disabled` and `hnsw_capacity` from `mempalace_status`.
