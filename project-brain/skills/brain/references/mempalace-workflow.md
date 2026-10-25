# MemPalace Workflow

MemPalace is available as a connected plugin (mempalace 3.11.0, 47 MCP tools). Use its MCP tools directly — do not install or re-init.

**Do not run `mempalace init` from this skill.** Init is an LLM-assisted operation that inspects the repository and writes palace structure; running it unattended inside a project-brain flow can rewrite wing/room taxonomy the brain depends on. If the palace is not initialized, stop and ask the user to run it themselves.

## MemPalace's own hooks already write — one writer at a time

MemPalace ships its own harness hooks (stop, session-end, precompact) that
automatically write session transcripts and diary checkpoints into the
palace, plus a transcript miner. Never duplicate that work: the brain's own
diary entry (`mempalace_diary_write` with the agent named by `mempalace_diary_agent`
in `.brain/CLAUDE.md`) is a separate, deliberate record — it coexists with the
automatic checkpoints.

- Never run two palace writers concurrently. A second writer exits 1 with
  `palace <path> is held by PID <n> ...` and there is no waiting.
- The `mine` CLI accepts `--daemon/--direct/--background` write routing and
  honors `MEMPALACE_WRITE_ROUTING`; hooks never cold-start the daemon. The
  default routing is fine for the brain's recipes — do not add flags unless
  the user runs a daemon deliberately.
- Never call the `checkpoint` MCP tool from the brain: that is MemPalace's own
  hooks' job (see `mempalace-tools.md`, MEMPALACE OWNED). (The CLI has no
  `checkpoint` subcommand in 3.11.0; the tool is MCP-only.)

### Diary writes and the palace lock

A diary write near the end of a session can collide with MemPalace's own
hooks (stop, session-end, precompact), which write at session end. Rules:

- Never write the diary while the brain's own mine is running — do the mine
  and the diary write one after another, never interleaved.
- If `mempalace_diary_write` fails with `palace <path> is held by PID <n> ...`,
  wait for the holder to finish, retry ONCE, and if the retry still fails,
  append the diary text to `.brain/log/<YYYYMMDD>.md` (the plugin's existing
  daily log) and tell the user the MemPalace write failed.
- "Never retry in a loop" still applies to every OTHER palace write (mine,
  add_drawer, update_drawer): one failure means wait for the holder to finish
  and let the user decide; do not retry automatically.

## Diary wing (how `diary_write` actually lands)

`mempalace_diary_write` stores to wing `wing_<agent_name>` unless an explicit
`wing` is passed (MemPalace's diary tool default). With the brain's agent
name from `mempalace_diary_agent` in `.brain/CLAUDE.md` and no wing override,
diary entries land in `wing_<that-agent>` — NOT in the `wiki_<project-slug>`
wiki wing. That is the intended layout: the wiki wing holds mined wiki pages;
the diary wing holds session continuity. The `mempalace_wing:` frontmatter in
`.brain/CLAUDE.md` names the WIKI wing for mining and search; diary recipes
use the agent from `mempalace_diary_agent` in that same file.

### Existing brains: older diary entries

Brains scaffolded by plugin versions before the diary-wing split were told
that ALL MemPalace operations use the project wing, so their diary entries may
sit in the project's wiki wing (the one named in `.brain/CLAUDE.md`) instead
of the diary wing. If `mempalace_diary_read` with the agent from
`mempalace_diary_agent` in `.brain/CLAUDE.md` (or for older brains without that
field, the agent named in the diary sentence of that file) looks empty:

1. Verify the diary wing actually does not exist before concluding it is
   empty: `mempalace_list_wings`, comparing normalized names (lowercase,
   `-` and space → `_`). An empty read is not proof by itself.
2. Read the old entries ONCE, read-only: `mempalace_list_drawers` with
   `wing` = the old wing named in `.brain/CLAUDE.md` and `room: "diary"`.
3. Moving them to the new diary wing is possible with
   `mempalace_update_drawer` (it accepts a `wing` argument) — ONLY after
   asking the user. UNVERIFIED: this move has never been tested.
4. There is no automatic migration, and none should be written.

During a **reset**, the diary wing (`wing_<diary_agent>` and its normalized
form) must be cleared together with the wiki wing — see the
`/project-brain:reset` skill, Step 3.

## Wing namespacing (critical)

Every project has a dedicated MemPalace wiki wing. The wing name is recorded in `.brain/CLAUDE.md` frontmatter as `mempalace_wing`. That value names the WIKI wing: it applies to wiki mining and wiki search only — NOT to diary operations. Diary reads and writes use the agent from `mempalace_diary_agent` in `.brain/CLAUDE.md` and MemPalace's diary wing `wing_<that-agent>` (see "Diary wing" above). Never write to a generic or guessed wing name.

```bash
# Read the wing name for the current project:
grep "mempalace_wing" .brain/CLAUDE.md
# Output: mempalace_wing: wiki_ambient_mixer
```

Wing names follow **MemPalace's own `wiki_<slug>` underscore convention** (e.g. `wiki_ambient_mixer`, `wiki_my_project`), matching the normalization MemPalace itself applies to directory-derived wings (`normalize_wing_name`: lowercase, `-` and space → `_`). The scaffold writes this automatically for new brains. Brains scaffolded before 0.9.3 may carry a legacy hyphenated `wiki-<slug>` value; re-scaffolding keeps it, and `project-brain-doctor` flags it with a migration hint. If `.brain/CLAUDE.md` is missing or does not define a non-empty `mempalace_wing`, follow the recall guard: skip MemPalace operations, tell the user to run project-brain-init or fix the file, and never derive or guess a wing. The derivation rules live in `mempalace-tools.md` ("Wing Naming Constants"); project-brain-init derives the wing name and writes it into `.brain/CLAUDE.md`.

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

See `references/mempalace-tools.md` for the full 47-tool catalog with schemas, policies, and verified behaviors.

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

Call `mempalace_search` before summarizing past project decisions, prior work, user preferences, remembered constraints, or unresolved threads. Search with the project name, current task, important entities, and decision terms, and pass `wing` = the wiki wing from `.brain/CLAUDE.md` so the search stays inside this project's namespace (a wingless search scans the whole palace, other projects included).

### Writing a new memory

1. Call `mempalace_check_duplicate` first to avoid near-identical drawer pollution.
2. Call `mempalace_add_drawer` to write to the appropriate wing/room.

### Diary writes

Call `mempalace_diary_write` after substantial work, decisions, or context changes — never while the brain's own mine is running (see "Diary writes and the palace lock").

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
| Diary entries | Source summaries |
| Recurring working style | Architecture pages |
| Context that should survive model switches but isn't yet polished knowledge | Decisions, concepts, entities, contradictions |

Use `.brain/state/session-brief.md` for the short current handoff, next read targets, active workstream, and exact next actions.

## Compile-to-wiki flow

MemPalace is not the final source of project truth. When memory contains stable facts:

1. Follow the recall rule in the plugin's SKILL.md step 7.
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
