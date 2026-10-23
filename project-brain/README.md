# Project Brain

A local-first AI memory plugin for OpenClaude and Claude Code. It gives an assistant a durable project brain made from source-grounded wiki pages, session handoffs, health checks, optional MemPalace semantic memory, and optional graphify dependency maps.

When a model changes, a chat resets, or a teammate returns to a codebase weeks later, the project context should not disappear.

> Project Brain is not a source-code deletion tool, not a cloud sync service, and not a replacement for reading the repository. It is a structured memory layer built around the source of truth: the project files on disk.

## What it does

1. **Local wiki** — `.brain/` holds architecture notes, source summaries, decisions, open questions, logs, and a session brief.
2. **MemPalace memory** — optional semantic memory mined from the wiki, organized by project wing, room, and drawer.
3. **graphify output** — optional dependency graph under `graphify-out/`, generated from the real project source code.

Six layers: evidence (`.brain/raw/` + repo files), synthesis (`.brain/wiki/`), memory (MemPalace), map (`graphify-out/`), handoff (`.brain/state/session-brief.md`), and vault (Obsidian MCP, opt-in).

## Awareness hooks (bundled, automatic)

The plugin ships `hooks/hooks.json` (auto-attached on install by OpenClaude-style harnesses):

- **SessionStart** (also fires after context compaction, `source: "compact"`) — injects a short status line into the model's context: `.brain` presence, the doctor's graphify freshness line, pointers to `session-brief.md` / `index.md`, and the detected harness. ~40 ms, read-only.
- **PostToolUse** (matcher `Write|Edit|MultiEdit|NotebookEdit`) — when source files changed since the graph was built, emits a short throttled reminder (≥ 300 s apart; same reason at most once per 1800 s) to update the relevant wiki pages, run the doctor-chosen graphify command, and write a session diary entry.

Hooks never call MemPalace write tools or the CLI (MemPalace's own hooks already write session transcripts; a second writer fails with exit code 1), do no network I/O, are silent no-ops when `.brain/` does not exist, and always exit 0. Turn them off with `PROJECT_BRAIN_HOOKS_DISABLED=1` or by removing `hooks/hooks.json`.

## Install

```bash
openclaude
/plugin marketplace add /path/to/ai-brain-marketplace
/plugin install project-brain@ai-brain-marketplace
```

## Slash commands

| Command | Purpose |
| --- | --- |
| `/project-brain:brain` | Initialize, ingest, compile, graph, remember, audit, hand off |
| `/project-brain:reset` | Delete the MemPalace wing's drawers via MCP, then local files |
| `/project-brain:doctor` | Health checks and score |
| `/project-brain:lint` | Validate frontmatter, wikilinks, index consistency |
| `/project-brain:audit` | Review open audit artifacts |
| `/project-brain:update-check` | Installed vs latest versions |

## CLI commands

Wrappers in `bin/` call the Python scripts in `scripts/`. All are stdlib-only, Python 3.9+.

| Command | Purpose |
| --- | --- |
| `project-brain-init <project-root> "<Title>"` | Create or refresh the `.brain/` scaffold |
| `project-brain-doctor <project-root>` | Health checks for local files and optional integrations |
| `project-brain-lint <project-root> [--json]` | Lint wiki structure, links, frontmatter |
| `project-brain-audit-open <project-root>` | Show open audit artifacts |
| `project-brain-hook-install <project-root>` | Install an optional Git post-commit lint hook |
| `project-brain-update-check` | Compare installed vs latest versions |
| `project-brain-reset [project-root] [--dry-run\|--confirm]` | Delete local brain files |

If `bin/` is not on `PATH`:

```bash
PLUGIN_ROOT="$(ls -d ~/.openclaude/plugins/cache/ai-brain-marketplace/project-brain/*/ 2>/dev/null | sort -V | tail -1)"
"$PLUGIN_ROOT/bin/project-brain-init" /path/to/project "My Project"
```

## Reset: what the script does and does not do

`project-brain-reset` deletes **local files only**:

- `.brain/`
- `graphify-out/`
- the `# Project Brain` block in root `CLAUDE.md`
- `CLAUDE.project-brain.snippet.md`

It never touches project source code, and it **never deletes MemPalace drawers**. A shell subprocess cannot call in-session MCP tools, and the `mempalace` CLI has no drawer-delete command. Drawer deletion is the `/project-brain:reset` skill's job:

1. Read `mempalace_wing` from `.brain/CLAUDE.md` before anything is deleted.
2. `mempalace_list_rooms` → `mempalace_list_drawers` → `mempalace_delete_drawer` for every drawer.
3. Only then run `project-brain-reset <project-root> --confirm`.

### Wing names

`scaffold_brain.py` derives the wing from the project title via `sanitize_wing_name`: lowercase, replace runs outside `[a-z0-9._-]` with a single hyphen, collapse repeated hyphens, strip leading/trailing `-._`. **Underscores are preserved.** If `.brain/CLAUDE.md` is gone, use that same rule, then cross-check with `mempalace_list_wings` before concluding the wing is empty.

### What reset never deletes

- Project source files or Git history
- Files outside `.brain/` and `graphify-out/`
- Other projects' wings, diary entries, or memories

Reset is irreversible.

## Safety model

- Dry-run is the default; deletion requires `--confirm`.
- No source-code deletion path.
- No direct ChromaDB file deletion.
- Wings are cleared only by listing rooms, listing drawers, and deleting each drawer ID.
- Missing optional integrations are warnings, not fake successes.

## Generated files

```text
.brain/
  CLAUDE.md
  wiki/
    index.md
    architecture/
    decisions/
    concepts/
    entities/
    open-questions.md
  state/session-brief.md
  log/
  raw/
  audit/

graphify-out/
  GRAPH_REPORT.md
```

## Development

```bash
cd project-brain
python3 -m pytest -q
```

Tests use `tests/conftest.py` fixtures (`run_script`, `scaffolded_project`, `tmp_project`) and only exercise `--dry-run` for reset.

## Troubleshooting

### `project-brain-reset` is not found

Run it from the plugin directory (`./bin/project-brain-reset`) or resolve `PLUGIN_ROOT` as shown above.

### MemPalace drawers were not deleted

Expected if you ran the script directly. Use `/project-brain:reset` so the agent can call the MCP tools. The script reports `MemPalace: handled by the /project-brain:reset skill via MCP tools, not by this script.`

### `project-brain-doctor` reports graphify missing

Install graphify, then regenerate graph output from project source. Do not run graphify on `.brain/wiki/`.

### A fresh brain has a low health score

A new brain is structurally valid but knowledge-poor. It improves after sources are ingested, wiki pages are compiled from primary sources, graphify runs, and memory is mined.

## License

MIT. See [LICENSE](LICENSE).