# MemPalace Workflow

MemPalace is available as a connected plugin (mempalace 3.12.0, 47 MCP tools). Use its MCP tools directly — do not install or re-init.

## Wing namespacing (critical)

Every project has a dedicated MemPalace wing. The wing name is recorded in `.brain/CLAUDE.md` frontmatter as `mempalace_wing`. Always read that value and use it — never write to a generic or guessed wing name.

```bash
# Read the wing name for the current project:
grep "mempalace_wing" .brain/CLAUDE.md
# Output: mempalace_wing: wiki-ambient-mixer
```

Wing names follow the `wiki-<slug>` convention (e.g. `wiki-ambient-mixer`, `wiki-my-project`). The scaffold writes this automatically. If `.brain/CLAUDE.md` does not exist yet, derive the wing name as `wiki-` + `sanitize_wing_name(title)` where `sanitize_wing_name` is defined in `scaffold_brain.py`: lowercase, replace runs of characters outside `[a-z0-9._-]` with a single hyphen, collapse repeated hyphens, strip leading/trailing `-._`, preserve underscores. Write that name into `.brain/CLAUDE.md` frontmatter once the brain is initialized.

If the derived name doesn't exist, call `mempalace_list_wings` and match on a distinctive substring of the project directory name before concluding the wing is empty.

**Why this matters:** MemPalace is a global store shared across all projects in a session. Without namespacing, the model writes project A's context into project B's wing, or pollutes a shared wing with mixed content from every project it touches. The wing is the namespace — stay inside it.

## Finding the binary

If you need to check or restart the server:

```bash
which mempalace-mcp          # usually ~/.local/bin/mempalace-mcp or ~/.pyenv/shims/mempalace-mcp
mempalace --version          # verify installed version
mempalace status             # CLI health check (separate from MCP)
```

The MCP server is registered in the OpenClaude mempalace plugin — it launches automatically when OpenClaude starts. If the tools are not present in the current session, the plugin is either disabled or the binary is not on PATH.

## Tool categories

### Core palace tools

- `mempalace_status` — verify the memory layer before making claims about availability or prior sessions. Call this at the start of serious work.
- `mempalace_search` — full-text + semantic search across all wings, rooms, and drawers. Primary way to find prior context.
- `mempalace_list_wings` — list all wings in the palace.
- `mempalace_list_rooms` — list rooms in a wing.
- `mempalace_list_drawers` — list drawers in a wing/room.
- `mempalace_get_drawer` — read a specific drawer by ID.
- `mempalace_add_drawer` — write a new drawer to a wing/room.
- `mempalace_update_drawer` — overwrite an existing drawer.
- `mempalace_delete_drawer` — delete a drawer by ID.
- `mempalace_check_duplicate` — check if near-identical content already exists before writing.
- `mempalace_memories_filed_away` — surface what was recently filed across the palace.
- `mempalace_traverse` — walk the graph of connected drawers from a starting point.
- `mempalace_graph_stats` — statistics on the drawer graph (node count, edge count, etc).
- `mempalace_get_taxonomy` — read the palace taxonomy (wing/room naming conventions).
- `mempalace_reconnect` — reconnect to the palace backend if the server restarted.
- `mempalace_hook_settings` — read/write hook configuration (session-end, pre-compact, stop).

### Diary tools

- `mempalace_diary_write` — write a session diary entry. Call after substantial work, decisions, or context changes.
- `mempalace_diary_read` — read past diary entries by date range or count.

### Knowledge graph tools (kg_*)

The KG layer stores structured facts as timestamped assertions — more structured than free-text drawers.

- `mempalace_kg_add` — add a knowledge graph fact (subject, predicate, object, confidence, source).
- `mempalace_kg_query` — query facts by subject, predicate, or object pattern.
- `mempalace_kg_invalidate` — mark a fact as no longer valid.
- `mempalace_kg_supersede` — replace an old fact with a new one, linking them.
- `mempalace_kg_timeline` — show how a fact or entity changed over time.
- `mempalace_kg_stats` — statistics on the KG layer.

Use KG tools when facts have a clear source and confidence level, when you want to track how something changed over time, or when you need structured retrieval (e.g. "what do I know about X's architecture?").

### Tunnel tools

Tunnels are bidirectional links between drawers across wings/rooms — useful for relating decisions to their context.

- `mempalace_create_tunnel` — create a labeled link between two drawers.
- `mempalace_delete_tunnel` — delete a tunnel by ID.
- `mempalace_find_tunnels` — find all tunnels to/from a drawer.
- `mempalace_list_tunnels` — list all tunnels in the palace.
- `mempalace_follow_tunnels` — traverse the tunnel graph from a starting drawer.

### Artifact tools

- `mempalace_artifact_get` — retrieve a stored artifact (file, blob, or structured data) by ID.

### AAAK / spec tools

- `mempalace_get_aaak_spec` — read the palace's AAAK (Agent Architecture Alignment Kit) spec if one is configured.
- `mempalace_patch_submit` — submit a patch proposal to the palace spec.

### Collaboration / event tools (may not be present in all sessions)

These are active when shared-brain mode is enabled:

- `mempalace_event_append` — post an event to the logstream.
- `mempalace_event_list` — list recent logstream events.
- `mempalace_event_wait` — long-poll for new events (remote clients).
- `mempalace_event_ack` — acknowledge/close an event.
- `mempalace_task_create` — create a delegated task for another agent.

## Wing Lifecycle

Wings are labels on drawers, not independent objects. A wing is created implicitly when the first drawer is written with that wing name, and deleted implicitly when its last drawer is removed. There is no `delete_wing` tool.

Correct wing deletion loop:

1. Call `mempalace_list_rooms` with the target wing name.
2. For each returned room, call `mempalace_list_drawers` with the wing and room.
3. For each returned drawer ID, call `mempalace_delete_drawer` once.
4. Continue deleting remaining drawers if one fails, then report failures at the end.
5. After the last drawer is deleted, the wing no longer exists.

## When to call each tool

### Wake-up

Call `mempalace_status` at the start of serious project-brain work and before any claim about previous sessions.

### Finding prior context

Call `mempalace_search` before summarizing past project decisions, prior work, user preferences, remembered constraints, or unresolved threads. Search with the project name, current task, important entities, and decision terms.

### Writing a new memory

1. Call `mempalace_check_duplicate` first to avoid near-identical drawer pollution.
2. Call `mempalace_add_drawer` to write to the appropriate wing/room.

### Diary writes

Call `mempalace_diary_write` after substantial work, decisions, or context changes.

**Required diary entry format:**

```
[DATE] | [PROJECT] | [ACTION]
Summary: [1-2 plain English sentences describing what happened]
Key finding: [the most important thing discovered]
Contradictions: [any source conflicts found, or "none"]
Log: [path to session log file]
Next: [top priority action for next session]
```

**Example:**

```
2026-05-09 | ambient-mixer | brain-init
Summary: Initialized project brain and ingested GEMINI.md and critic_report.md as first sources.
Key finding: audio-renderer.js is imported by index.html at line 1750 — it is NOT orphaned despite GEMINI.md claiming otherwise.
Contradictions: GEMINI.md says port 8080 but server.js uses 3000.
Log: .brain/log/20260509.md
Next: Check if graphify-out/GRAPH_REPORT.md commit matches HEAD; run /graphify . only if commits differ or no graph exists.
```

### Knowledge graph

Use `mempalace_kg_add` when a fact has a clear source and should be tracked over time. Use `mempalace_kg_query` before adding to check for conflicts.

## What belongs in MemPalace vs wiki

| MemPalace | `.brain/wiki/` |
|-----------|---------------|
| Verbatim memory from prior conversations | Durable project facts |
| User preferences | Source summaries |
| Diary entries | Architecture pages |
| Recurring working style | Decisions |
| Context that should survive model switches but isn't yet polished knowledge | Concepts, entities, contradictions |

Use `.brain/state/session-brief.md` for the short current handoff, next read targets, active workstream, and exact next actions.

## Compile-to-wiki flow

MemPalace is not the final source of project truth. When memory contains stable facts:

1. Search MemPalace for the relevant context.
2. Verify against raw sources, repo files, or existing wiki pages.
3. Promote durable findings into `.brain/wiki/` pages.
4. Add or update decision records when the memory captures a decision.
5. Add wikilinks and update `.brain/wiki/index.md`.
6. Write a short diary entry saying what was compiled.
7. Update `.brain/state/session-brief.md` if the compiled memory changes current work.

## What NOT to mine into MemPalace

Mine `.brain/wiki/` pages into MemPalace — not the project source code. Source code is on disk and greppable; mining it bloats the palace with redundant drawers. Graphify runs on source code, not on the wiki.

## Failure handling

If `mempalace_status` fails or the tools are not in the current session:

- Say the MemPalace layer is not active in this session.
- Continue from `.brain/wiki/`, `.brain/log/`, graphify output, raw sources, and the current chat.
- Do not invent memories.
- To diagnose: run `mempalace status` in bash. Check that `mempalace-mcp` is on PATH. Check that the mempalace plugin is enabled in OpenClaude settings.
