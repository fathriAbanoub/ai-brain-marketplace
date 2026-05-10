# MemPalace Workflow

MemPalace is available as a connected plugin. Use its MCP tools directly.

MemPalace is already installed as a plugin. graphify is already installed as a CLI tool and skill. Do not reinstall either.

## Expected MCP tools

Use the tool names exposed in the current session. The core tools this brain expects are:

- `mempalace_status` — verify the memory layer before making claims about availability or prior sessions.
- `mempalace_search` — search prior conversations, diary entries, decisions, and preferences.
- `mempalace_diary_write` — write concise session diary entries after substantial work.
- `mempalace_preferences_get` — read durable user preferences before applying style, workflow, or project conventions.
- `mempalace_preferences_set` — save persistent user preferences when the user states or confirms them.

If the plugin exposes additional tools, prefer the names and capabilities returned by `mempalace_status`.


## Wing Lifecycle

Wings are labels on drawers, not independent objects. A wing is created implicitly when the first drawer is written with that wing name, and it is deleted implicitly when its last drawer is removed. There is no `delete_wing` tool and no valid direct ChromaDB file deletion path.

Correct wing deletion loop:

1. Call `mempalace_list_rooms` with the target wing name.
2. For each returned room, call `mempalace_list_drawers` with the wing and room.
3. For each returned drawer ID, call `mempalace_delete_drawer` once.
4. Continue deleting remaining drawers if one drawer deletion fails, then report failures at the end.
5. After the last drawer is deleted, the wing no longer exists.

The same wing name can be reused immediately after deletion by writing any new drawer to it. No wing recreation step is needed.

Mine the `.brain/wiki/` layer into MemPalace, never the project source code. The source code is already on disk and greppable; mining it bloats the palace with redundant drawers. MemPalace should hold synthesized wiki knowledge, session diary entries, prior decisions, and durable preferences.

Graphify runs on the project source code, not on the wiki. Graphify maps imports, calls, module dependencies, and code relationships. Markdown prose in `.brain/wiki/` has no dependency structure worth graphing.

## When to call each tool

### Wake-up

Call `mempalace_status` at the start of serious project-brain work and before any claim about previous sessions. If the tool is present and responds, MemPalace is available.

### Prior decisions and context

Call `mempalace_search` before summarizing:

- past project decisions,
- prior work from another session,
- user preferences,
- remembered constraints,
- unresolved threads from earlier chats.

Search with the project name, current task, important entities, and decision terms.

### Diary writes

Call `mempalace_diary_write` after substantial work, decisions, or context changes. Diary entries must follow the minimum standard below.

#### Diary entry minimum standard

A diary entry must contain at minimum: (1) session date and project name, (2) what was ingested or read, (3) the single most important finding or decision made, (4) any contradictions or surprises found, (5) a reference to the session log file path for full detail. Pipe-delimited compressed format is permitted only as a supplement to a plain-language summary, not as a replacement. A future agent must be able to read the diary entry alone and understand what happened and why, without needing to open the log file.

**Required format:**

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
Contradictions: GEMINI.md says port 8080 but server.js uses 3000; GEMINI.md says audio-renderer.js is unused but index.html imports it.
Log: .brain/log/20260509.md
Next: Run /graphify . to build dependency graph; verify all open questions against primary source.
```

### Preferences

Use `mempalace_preferences_get` when a workflow choice depends on the user's persistent preferences. Use `mempalace_preferences_set` when the user states a preference that should apply beyond this session, such as output style, preferred tools, review cadence, or safety boundaries.

Never store secrets, credentials, private keys, or sensitive tokens as preferences.

## What belongs in MemPalace vs wiki

Use MemPalace for:

- verbatim memory from prior conversations,
- user preferences,
- diary entries,
- recurring working style,
- context that should survive model switches but is not yet polished knowledge.

Use `.brain/wiki/` for:

- durable project facts,
- source summaries,
- architecture pages,
- decisions,
- concepts and entities,
- contradictions and verified synthesis.

Use `.brain/state/session-brief.md` for:

- the short current handoff,
- next read targets,
- active workstream,
- exact next actions.

## Compile-to-wiki flow

MemPalace is not the final source of project truth. When memory contains stable facts or decisions:

1. Search MemPalace for the relevant context.
2. Verify against raw sources, repo files, or existing wiki pages where possible.
3. Promote durable findings into `.brain/wiki/` pages.
4. Add or update decision records when the memory captures a decision.
5. Add wikilinks and update `.brain/wiki/index.md`.
6. Write a short diary entry saying what was compiled.
7. Update `.brain/state/session-brief.md` if the compiled memory changes current work.

## Failure handling

If `mempalace_status` fails or the tool is not exposed in the current session, say that the MemPalace layer is not active in this session and continue from `.brain/wiki/`, `.brain/log/`, graphify output, raw sources, and the current chat. Do not invent memories.
