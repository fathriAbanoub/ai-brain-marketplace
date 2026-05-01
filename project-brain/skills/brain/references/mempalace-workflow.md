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

Call `mempalace_diary_write` after substantial work, decisions, or context changes. Good diary entries include:

- what changed,
- why it matters,
- user-stated preferences,
- decisions made,
- next read targets,
- links to updated brain pages.

Keep diary entries concise. Do not dump raw source text.

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

