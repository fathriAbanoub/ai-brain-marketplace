# MemPalace Tool Reference

This document catalogs all 47 MemPalace MCP tools with their exact schemas, usage policies for project-brain, and verified call recipes.

> Verified against MemPalace 3.11.0 schemas (mcp-tools.json) and behavior tests run 2026-10-21.

## Tool Summary Table

> Argument lists verified against 3.11.0 schemas from mcp-tools.json. **bold** = required (no `?`); plain `name?` = optional.

| Tool | Description | Arguments | Access | Policy |
|------|-------------|-----------|--------|--------|
| status | Check MemPalace is running and vector index health | none | read | **USE** |
| list_wings | List all wings in the palace | none | read | **USE** |
| list_rooms | List rooms within a wing | wing? | read | **USE** |
| get_taxonomy | List all wings and rooms with drawer counts | none | read | **USE** |
| get_aaak_spec | Read AAAK spec if configured | none | read | OPTIONAL |
| search | Full-text + semantic search | **query**, limit?, wing?, room?, source_file?, since?, before?, max_distance?, candidate_strategy?, cli_compatible?, include_media?, query_task?, context? | read | **USE** |
| get_drawer | Read a specific drawer by ID | **drawer_id** | read | **USE** |
| get_drawers | Read multiple drawers by ID | **drawer_ids** | read | **USE** |
| list_drawers | List drawers in a wing/room (max page size 100; paginate with offset until a page returns fewer than the limit) | wing?, room?, since?, before?, limit?, offset? | read | **USE** |
| diary_read | Read diary entries by agent | **agent_name**, last_n?, wing? | read | **USE** |
| diary_write | Write a diary entry | **agent_name**, entry?, topic?, wing?, content? | write | **USE** |
| add_drawer | Write a new drawer | **wing**, **room**, **content**, source_file?, added_by? | write | **USE** |
| update_drawer | Overwrite existing drawer | **drawer_id**, content?, wing?, room? | write | ASK FIRST |
| delete_drawer | Delete a drawer by ID | **drawer_id** | destructive | ASK FIRST — **PROHIBITED in the reset workflow** |
| delete_drawers | Delete multiple drawers (1–500 IDs per call) | **drawer_ids** | destructive | **USE for the reset** (batches ≤ 500) |
| check_duplicate | Check for near-identical content | **content**, threshold? | read | **USE** |
| mine | Mine a directory into a wing | **source**, mode?, wing?, agent?, limit?, dry_run?, extract?, include_ignored?, include_subagents? | write | **USE** (wiki only) |
| sync | Prune drawers whose source files are gitignored, deleted, or moved | project_dir?, wing?, apply? | write | ASK FIRST; never the wiki wing |
| delete_by_source | Delete drawers from a source_file | **source_file**, dry_run? | destructive | ASK FIRST |
| hook_settings | Read/write hook config | silent_save?, desktop_toast? | write | MEMPALACE OWNED |
| memories_filed_away | Check recent filing activity | none | read | MEMPALACE OWNED |
| reconnect | Reconnect to palace backend | none | write | MEMPALACE OWNED |
| kg_query | Query knowledge graph facts | **entity**, as_of?, direction? | read | OPTIONAL |
| kg_add | Add a knowledge graph fact | **subject**, **predicate**, **object**, valid_from?, valid_to?, source_closet?, source_file?, source_drawer_id? | write | OPTIONAL |
| kg_invalidate | Mark a fact as invalid | **subject**, **predicate**, **object**, ended? | write | OPTIONAL |
| kg_supersede | Replace fact with successor | **subject**, **predicate**, **old_object**, **new_object**, at? | write | OPTIONAL |
| kg_timeline | Show fact history | entity?, limit?, offset? | read | OPTIONAL |
| kg_stats | Get KG statistics | none | read | OPTIONAL |
| traverse | Walk connected drawers from a start | **start_room**, max_hops? | read | DO NOT USE |
| find_tunnels | Find tunnels to/from a drawer | wing_a?, wing_b? | read | USE (reset graph inspection) |
| graph_stats | Get drawer graph statistics | none | read | USE (reset diagnostics) |
| mesh_peers | Get sync/peer status | none | read | DO NOT USE |
| create_tunnel | Create cross-wing link | **source_wing**, **source_room**, **target_wing**, **target_room**, label?, source_drawer_id?, target_drawer_id? | write | DO NOT USE |
| list_tunnels | List all tunnels (filter by wing) | wing? | read | **USE (reset cleanup)** |
| delete_tunnel | Delete a tunnel by ID | **tunnel_id** | destructive | **USE (reset cleanup, in-scope records only)** |
| list_hallways | List within-wing co-occurrence links (filter by wing, paginated) | wing?, limit?, offset? | read | **USE (reset cleanup)** |
| delete_hallway | Delete a hallway by ID | **hallway_id** | destructive | **USE (reset cleanup, in-scope records only)** |
| follow_tunnels | Traverse tunnel graph | **wing**, **room** | read | DO NOT USE |
| event_append | Post event to logstream | **type**, **stream**, **room**, topic?, **from_agent**, to_agent?, correlation_id?, branch?, base_commit?, status?, body?, metadata?, artifact_ids? | write | DO NOT USE |
| event_list | List logstream events | stream?, room?, topic?, type?, to_agent?, from_agent?, writer?, correlation_id?, status?, since_event_id?, before_event_id?, since_created_at?, limit?, order?, preview? | read | DO NOT USE |
| event_wait | Long-poll for events | stream?, room?, topic?, type?, to_agent?, from_agent?, writer?, correlation_id?, status?, since_event_id?, since_created_at?, timeout_ms?, limit? | read | DO NOT USE |
| event_ack | Acknowledge an event | **event_id**, **from_agent**, status?, body?, topic? | write | DO NOT USE |
| task_create | Create delegated task | **project**, **from_agent**, **to_agent**, **goal**, **branch**, **base_commit**, **done** | write | DO NOT USE |
| artifact_put | Store artifact | **kind**, **content**, **created_by**, metadata? | write | DO NOT USE |
| artifact_get | Retrieve artifact | **artifact_id** | read | DO NOT USE |
| patch_submit | Submit patch to spec | **content**, **from_agent**, **stream**, room?, topic?, to_agent?, correlation_id?, branch?, base_commit?, body?, metadata? | write | DO NOT USE |
| checkpoint | Save session in one call | **items**, diary?, dedup_threshold?, added_by? | write | DO NOT USE |

## Policy Definitions

- **USE**: Safe to call in normal project-brain workflows
- **OPTIONAL**: Only where the plugin already uses them today (kg_query, kg_add)
- **ASK FIRST**: Confirm with user before calling (delete, sync, update operations)
- **DO NOT USE**: Not needed for project-brain; may conflict with other uses
- **MEMPALACE OWNED**: Managed by MemPalace's own hooks, never call from project-brain

### Deletion policy (drawers)

- `mempalace_delete_drawers` is the ONLY deletion mechanism of the normal reset
  (`/project-brain:reset`). It accepts `drawer_ids` — an array of **1 to 500**
  IDs — and returns `results` (per-ID outcomes, including individual errors),
  `count`, `deleted`, `errors`, `revisions_deleted`, and `revisions_error`
  (when applicable). A successfully accepted batch is NOT proof that every
  requested drawer was deleted: inspect every per-ID result, treat IDs absent
  from `results` as missing (not deleted), and report `revisions_error` when
  present.
- `mempalace_delete_drawer` (single) is **PROHIBITED in the reset workflow** —
  not even as a fallback when the bulk call fails, and not even when a wing has
  one remaining drawer. The canonical reset algorithm lives in
  `scripts/mempalace_reset.py` (tested; the reset's bulk-delete path has no
  single-drawer capability by construction). Outside the reset,
  `delete_drawer` remains an ASK FIRST tool for other legitimate single-drawer
  cleanup (e.g. removing one duplicate drawer).
- If `mempalace_delete_drawers` itself is unavailable or fails persistently,
  stop the destructive phase and report; when the failure cannot be fixed by
  retrying or by resolving ownership, recommend `/project-brain:hard-reset`
  (the separate database-level operation) instead of switching deletion
  mechanisms silently.

### Graph cleanup policy (tunnels / hallways)

- The reset deletes in-scope records individually with `mempalace_delete_tunnel`
  / `mempalace_delete_hallway`. There is no bulk graph-deletion tool — do not
  invent one.
- Scope rule: a record is in scope when one of its EXACT wing names (tunnel
  `source_wing`/`target_wing`; hallway wing association) is a user-confirmed,
  actually-cleared reset target. Never match by normalized slug; never delete
  every tunnel/hallway in the palace.
- Records of a wing whose drawer deletion failed or was kept stay in place for
  a retry and are reported as remaining.
- Verify with a fresh `mempalace_list_tunnels` / `mempalace_list_hallways` after
  deletion; track tunnel and hallway failures separately from drawer deletion.

The DO NOT USE coordination tools (`event_*`, `task_create`, `patch_submit`) are
governed by MemPalace's own `mempalace rules` command, not by project-brain. If a
user asks about agent coordination, point them at `mempalace rules` rather than
wiring the tools into the brain workflow.

## The `sync` tool — pruning hazard

`sync` **prunes** drawers whose source files are gitignored, deleted, or moved — it never ingests. The
default is a dry-run preview; pass `apply: true` to commit deletions. The real hazard for project-brain
is the opposite of ingestion: if `.brain/` is gitignored, a sync of the wiki wing will show every
`.brain/wiki/` page as "would remove" and delete them all with `apply: true`.

Rules:

- Never run `mempalace sync` or the `mempalace_sync` tool against the wiki wing, regardless of gitignore state.
- `sync` may be used on other wings only with a dry run first and the user's explicit approval.
- To delete the drawers of a single deleted wiki page, use `mempalace_delete_by_source` (ASK FIRST
  policy) — it targets one source file and has its own dry-run default.

For normal wiki-to-memory updates use Recipe 3 (`mempalace mine .brain/wiki`), not `sync`.

## Concurrency

MemPalace has no compare-and-swap on drawers. Two sessions writing at the same
time can both pass `check_duplicate` and then both write, leaving near-identical
drawers. It is last-write-wins on `update_drawer`.

- Treat `check_duplicate` as advisory, not a lock.
- Do not run two sessions against the same wing concurrently.
- If a duplicate slips through, delete the extra drawer (ASK FIRST) rather than
  editing both.

## Verified Behaviors (3.11.0)

These behaviors were confirmed by running MemPalace 3.11.0 against scratch palaces on 2026-10-21.

**Concurrent writes (lock contention):** A second writer on the same palace exits immediately with
exit code 1 and prints `palace <path> is held by PID <n> (...); wait for it to finish or stop the
holder before retrying`. Never run two `mine`/`add_drawer`/`checkpoint` calls against the same palace
concurrently. Never retry in a loop — wait for the holder to finish. The ONE exception is the
session diary write (`mempalace_diary_write`): after the holder finishes it may retry once, and if
that still fails, append the diary text to `.brain/log/<YYYYMMDD>.md` and tell the user — see
"Diary writes and the palace lock" in `references/mempalace-workflow.md`.

**Page length cutoff:** Pages with a body of 51 characters or fewer are silently skipped by mining
(verified: 60-char pages are filed, sub-51 pages are skipped). The exact boundary is between 51 and 59
chars. The dry run prints one `[DRY RUN] <file> -> room:<room>` line per file that would be filed;
skipped files appear in "Files skipped (read error or too short)".

**Wing renaming by re-mining is impossible:** A file already filed under one wing is skipped when mined
into a second wing ("skipped (already filed or other)"). A wing cannot be renamed by re-mining the same
files under a new wing name. To rename a wing, use `mempalace_update_drawer` (it accepts a `wing`
argument) to move drawers one at a time, or delete the drawers and re-mine. Either approach requires
the user's decision.

**Room assignment:** All pages land in room `general` during mining unless `mempalace init` has been
run to detect rooms from folder structure. Whether `init` changes room assignment is UNVERIFIED.

**Recipe requiring `room`:** Any direct `mempalace_add_drawer` call must pass a `room` argument — the
schema requires it.

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

Always pass the project's wiki wing. Without `wing`, the search scans the
whole palace — other projects' transcript wings included. If `.brain/CLAUDE.md` is missing or does not define a non-empty `mempalace_wing`, skip the MemPalace search, tell the user the brain is not initialized or configured and to run project-brain-init (or fix the file), and never infer a wing or search without one.

```
mempalace_search({
  query: "<project-name> decisions preferences",
  wing: "wiki_<project-slug>",
  limit: 10
})
```

Read the exact wing from `mempalace_wing:` in `.brain/CLAUDE.md` (it names
the WIKI wing — wiki mining and wiki search only).

### 3. Sync the Wiki (after wiki edits)

Mine the wiki directory directly — gitignore does not apply when you name the path explicitly:

```
mempalace mine .brain/wiki --wing wiki_<project-slug>
```

Always do a dry run first and confirm with the user:

```
mempalace mine .brain/wiki --wing wiki_<project-slug> --dry-run
```

**IMPORTANT**: Mine only `.brain/wiki/` directory, not `.brain/raw/`, `.brain/state/`, `.brain/log/`, or the repo itself. Never mine the project root into the wiki wing. Never mine without an explicit `--wing`: a wingless mine derives the wing from the directory name (MemPalace's `normalize_wing_name`), which puts wiki pages in the directory-derived wing instead of the project's wiki wing.

### 4. Write Session Diary (at handoff)

```
mempalace_diary_write({
  agent_name: "<mempalace_diary_agent>",
  entry: "[DATE] | [PROJECT] | [ACTION]\nSummary: ...\nKey finding: ...\nContradictions: ...\nLog: ...\nNext: ...",
  topic: "session-diary"
})
```

The `agent_name` is read from `mempalace_diary_agent` in `.brain/CLAUDE.md` (for
an older brain without that field, from the agent named in the diary sentence of
that file; if neither exists, skip the diary and tell the user). With no `wing`
argument, MemPalace stores diary entries under `wing_<agent_name>` (its own
default), i.e. `wing_<mempalace_diary_agent>` — a different wing from the mined
wiki wing. That split is intentional; see "Diary wing" in
`references/mempalace-workflow.md`.

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

Session-continuity recall — the diary is stored under `wing_<agent_name>`;
`mempalace_diary_read` finds it via the agent name:

```
mempalace_diary_read({
  agent_name: "<mempalace_diary_agent>",
  last_n: 5
})
```

The `agent_name` is read from `mempalace_diary_agent` in `.brain/CLAUDE.md` (for
an older brain without that field, from the agent named in the diary sentence of
that file; if neither exists, skip the diary and tell the user).

If this read is empty for an older brain, follow [Existing brains: older diary entries](mempalace-workflow.md#existing-brains-older-diary-entries) in mempalace-workflow.md, which does the read-only legacy-wing lookup.

### 6. Preflight Index Health (CLI fallback)

When MCP is unavailable, use the CLI for preflight checks:

```
mempalace repair-status
mempalace status
```

## Wing Naming Constants

- Wiki wing (NEW brains, 0.9.4+): `wiki_<project-slug>_<UTC-timestamp>` — e.g.
  `wiki_ambient_studio_20261026T164600Z` (format `%Y%m%dT%H%M%SZ`, UTC). The
  timestamp is generated at creation time and the name is checked against the
  actual palace (wings + tunnels + hallways) before it is committed; collisions
  resolve by higher precision or a deterministic numeric suffix — an existing
  identity is never silently reused. The exact generated name is recorded in
  `mempalace_wing` in `.brain/CLAUDE.md` and never regenerated on re-init.
- Wiki wing (legacy): bare `wiki_<project-slug>` (0.9.3) or hyphenated
  `wiki-<slug>` (pre-0.9.3), recorded in `mempalace_wing` in `.brain/CLAUDE.md`.
  Legacy names stay supported: they are never deleted, renamed, or treated as
  the same wing as a differently-spelled name with a similar normalized form.
- Diary agent: `<mempalace_diary_agent>` (recorded in `mempalace_diary_agent`
  in `.brain/CLAUDE.md`); its diary wing is `wing_<agent>`.

Read both values from `.brain/CLAUDE.md` frontmatter. For an older brain without
the `mempalace_diary_agent` field, extract it from the diary sentence in that file;
if neither exists, skip the diary and tell the user.

`<project-slug>` follows **MemPalace's own wing convention** (its
`normalize_wing_name`): lowercase, `-` and space map to `_`, edge separators
stripped. Note that runs of separators are NOT collapsed by that rule, so
distinct actual wings can normalize to different keys while other distinct
names (hyphenated vs underscored) normalize identically — which is why the
reset's candidate matching shows every actual wing separately and asks for
ownership instead of deleting on normalized equality.

### Empty-wing lookups (reset / wing cleanup)

An empty or missing result from `mempalace_list_rooms` is **not** proof a wing
is empty. MemPalace normalizes wing names — lowercase, `-` and space → `_` —
so the recorded name and the actual wing can differ. Before concluding a wing
is empty or missing:

1. Call `mempalace_list_wings` (or `mempalace_get_taxonomy` for drawer counts).
2. Compare candidates against actual wings using the same normalize rule, not
   raw equality. Candidates for a project: the `mempalace_wing` value, the
   directory-derived wing (`normalize(<project-root dirname>)`), and the diary
   wing (`wing_<diary_agent>` and its normalized form).
3. Show every candidate with its drawer count — one row per ACTUAL wing, exact
   names preserved — and ask the user before deleting. Normalized equality is
   candidate discovery, never ownership proof or identity proof.

Also note: MemPalace's session stop hook re-mines `MEMPAL_DIR` without
`--wing`, so the directory-derived wing is re-created automatically when that
variable is set. See the reset skill's "re-creation hazard" section.

### Reset drawer enumeration and deletion (the only supported loop)

1. Enumerate IDs per confirmed wing: `mempalace_list_rooms` → for each room
   `mempalace_list_drawers` with `limit: 100` (the documented maximum page
   size) and `offset` advancing by 100 until a page returns fewer than 100.
   Never re-fetch the first page or skip offsets. Deduplicate and cross-check
   the collected count against `mempalace_get_taxonomy`'s `drawer_count` for
   the wing; a mismatch stops the destructive phase.
2. Delete with `mempalace_delete_drawers` in batches of at most 500 IDs.
   1,200 drawers = 3 accepted bulk calls for those IDs (500 + 500 + 200), not
   1,200 calls and not per-drawer calls.
3. Inspect every batch result per ID (see "Deletion policy" above), then
   verify: `mempalace_list_wings` must show the wing absent (the expected
   success state) or with zero drawers.
4. Continue with the remaining confirmed wings, then clean up in-scope
   tunnels (`mempalace_list_tunnels` → `mempalace_delete_tunnel`) and
   hallways (`mempalace_list_hallways` → `mempalace_delete_hallway`), then
   re-verify. Paginate `mempalace_list_hallways` exactly like
   `mempalace_list_drawers` — `limit: 100`, `offset` advancing by 100 until a
   page returns fewer than 100 — in BOTH the collection pass and the
   re-verification pass, so later-page hallways are included. A vanished wing
   never aborts the reset.

The canonical, tested implementation of this loop is
`scripts/mempalace_reset.py`; the `/project-brain:reset` skill mirrors it step
for step.

## Uninstalled Tools (NOT available)

These tools were referenced in older documentation but are NOT in the 47-tool set:

- `mempalace_preferences_get` — Use `.brain/wiki/` pages or `.brain/CLAUDE.md` instead
- `mempalace_preferences_set` — Use `.brain/wiki/` pages or `.brain/CLAUDE.md` instead

## Notes

- The mine tool respects .gitignore by default. Use `include_ignored` if `.brain/` is gitignored.
- Re-mining a directory replaces old drawers with new content (same wing/room). Verified: round 1, section 4 (scratch palace held only the new text after re-mine).
- Deleted wiki pages leave stale drawers; deleting them requires user confirmation (ASK FIRST policy).
- The vector index health check uses `vector_disabled` and `hnsw_capacity` from `mempalace_status`.
