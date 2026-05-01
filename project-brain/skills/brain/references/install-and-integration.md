# Install and Integration

This file documents the actual dependency state for the user's environment.

MemPalace is already installed as a plugin. graphify is already installed as a CLI tool and skill. Do not reinstall either.

## Pre-installed tools

### MemPalace

MemPalace is available as an OpenClaude plugin. Use MCP tools directly:

- `mempalace_status`
- `mempalace_search`
- `mempalace_diary_write`
- `mempalace_preferences_get`
- `mempalace_preferences_set`

Call `mempalace_status` before claiming anything about prior sessions or availability.

### graphify

graphify is available in two forms:

- skill mode: `/graphify <path>`
- shell mode: `graphify <subcommand>`

Use skill mode for full builds and shell mode for targeted operations.

### Obsidian MCP

Obsidian MCP is connected separately. Use it only when the user asks to sync, view, save, or open brain pages in Obsidian. `.brain/wiki/` remains the source of truth; Obsidian is a view layer.

## Plugin layout

```text
project-brain/
├── .claude-plugin/plugin.json
├── skills/brain/SKILL.md
├── skills/brain/references/
├── scripts/
└── bin/
```

The `bin/` wrappers call scripts in `project-brain/scripts/`.

## Verification

Run:

```bash
project-brain-doctor <project-root>
project-brain-lint <project-root>
project-brain-lint <project-root> --json
```

Healthy output should show:

- `.brain/` exists,
- `.brain/wiki/index.md` exists,
- `.brain/state/session-brief.md` exists and is fresh,
- graphify CLI is available,
- MemPalace MCP is available in the current session,
- Obsidian MCP is connected when vault sync is desired,
- lint has no `error` issues.

`project-brain-doctor` also prints health scores for completeness, freshness, coverage, and memory sync.

## Recommended `.graphifyignore`

Use or adapt these patterns:

```gitignore
.git/
.venv/
venv/
node_modules/
dist/
build/
coverage/
__pycache__/
*.pyc
*.log
.env
.env.*
secrets/
.brain/log/
.brain/audit/
.brain/state/
.brain/outputs/
graphify-out/
```

Do not ignore `.brain/wiki/` or `.brain/raw/refs/` if you want graphify to map the brain itself.

## CLAUDE.md integration

`project-brain-init` creates or updates the project root `CLAUDE.md` with a `# Project Brain` block. The block tells future models to read:

1. `.brain/CLAUDE.md`
2. `.brain/state/session-brief.md`
3. `.brain/wiki/index.md`
4. `graphify-out/GRAPH_REPORT.md` when available
5. MemPalace before making claims about past work

If the project already has a `CLAUDE.md`, the scaffold appends the block only when it is missing.

