# Project Brain

[![Version](https://img.shields.io/badge/version-0.6.0-blue?style=flat-square)](.claude-plugin/plugin.json)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue?style=flat-square)](https://www.python.org/)
[![Claude Code Plugin](https://img.shields.io/badge/Claude%20Code-plugin-6f42c1?style=flat-square)](https://code.claude.com/docs/en/plugins)
[![Status](https://img.shields.io/badge/status-alpha-orange?style=flat-square)](#project-status)

Project Brain is a local-first AI memory plugin for coding assistants. It gives an assistant a durable project brain made from source-grounded wiki pages, session handoffs, health checks, optional MemPalace semantic memory, and optional Graphify dependency maps.

The goal is simple: when a model changes, a chat resets, or a teammate returns to a codebase weeks later, the project context should not disappear.

> Project Brain is not a source-code deletion tool, not a cloud sync service, and not a replacement for reading the repository. It is a structured memory layer built around the source of truth: the project files on disk.

## Table of contents

- [What it does](#what-it-does)
- [Architecture](#architecture)
- [Project status](#project-status)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Commands](#commands)
- [Brain reset and deletion safety](#brain-reset-and-deletion-safety)
- [MemPalace bridge support](#mempalace-bridge-support)
- [Generated files](#generated-files)
- [Safety model](#safety-model)
- [Badges](#badges)
- [Troubleshooting](#troubleshooting)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

## What it does

Project Brain helps an AI assistant maintain project memory across sessions by coordinating three practical layers:

1. **Local wiki** - `.brain/` contains architecture notes, source summaries, decisions, open questions, logs, and a session brief.
2. **MemPalace memory** - optional semantic memory mined from the wiki, organized by project wing, room, and drawer.
3. **Graphify output** - optional dependency graph output under `graphify-out/`, generated from the real project source code.

It includes a skill plus command-line helpers for bootstrapping, linting, health checks, audit review, hook installation, and safe brain reset.

## Architecture

Project Brain intentionally separates source code, synthesized knowledge, semantic memory, and dependency graph data.

```text
Project source code
  |  never deleted by Project Brain
  |  never mined directly into MemPalace
  |
  +-- graphify --> graphify-out/GRAPH_REPORT.md
  |                dependency map of the actual codebase
  |
  +-- assistant reads and synthesizes
       |
       +-- .brain/wiki/
            source-grounded project knowledge
            |
            +-- MemPalace mine
                 searchable memory across sessions
```

### Layer responsibilities

| Layer | Location | Purpose | Reset behavior |
| --- | --- | --- | --- |
| Source code | Your repository | Primary source of truth | Never touched |
| Local brain | `.brain/` | Synthesized wiki, state, logs, raw references | Deleted by full or local-only reset |
| MemPalace | MCP-backed vector store | Searchable memory mined from the wiki | Cleared drawer-by-drawer for the resolved wing |
| Graphify | `graphify-out/` | Dependency and relationship graph of source code | Deleted by full or local-only reset |

## Project status

Project Brain is currently **alpha**. The local scaffold, lint, doctor, and reset commands are implemented as standalone scripts. Optional integrations such as MemPalace, Graphify, and Obsidian depend on the host assistant runtime and local tool availability.

Alpha means:

- The command surface is useful but still evolving.
- Integrations must fail safely when unavailable.
- You should review reset dry-runs before deleting anything.
- Public distribution should include additional runtime validation and release testing.

## Requirements

- Python 3.9 or newer.
- A Claude Code or OpenClaude-style plugin runtime that exposes plugin `bin/` commands and skills.
- Optional: MemPalace MCP tools for semantic memory.
- Optional: Graphify for code dependency maps.
- Optional: Obsidian MCP integration for vault mirroring.

The core local commands use only the Python standard library.

## Installation

This archive is structured as a local plugin marketplace:

```text
ai-brain-marketplace/
  .claude-plugin/marketplace.json
  project-brain/
    .claude-plugin/plugin.json
    bin/
    scripts/
    skills/
```

Use the local marketplace or plugin installation flow supported by your assistant runtime, pointing it at the `ai-brain-marketplace/` directory or the `project-brain/` plugin directory as appropriate for that runtime.

After installation, confirm the commands are available:

```bash
project-brain-init --help
project-brain-lint --help
project-brain-reset --help
```

If your runtime does not automatically put plugin `bin/` commands on `PATH`, run the commands directly from the plugin directory:

```bash
./bin/project-brain-init --help
./bin/project-brain-reset --help
```

## Quick start

Create a brain for an existing project:

```bash
project-brain-init /path/to/project "My Project"
```

Check health:

```bash
project-brain-doctor /path/to/project
```

Lint the local brain structure:

```bash
project-brain-lint /path/to/project
```

Preview a reset without deleting anything:

```bash
project-brain-reset /path/to/project --dry-run
```

Perform a local-only reset after reviewing the dry-run:

```bash
project-brain-reset /path/to/project --local-only --confirm
```

## Commands

| Command | Purpose |
| --- | --- |
| `project-brain-init <project-root> <title>` | Create or refresh the `.brain/` scaffold. |
| `project-brain-doctor <project-root>` | Run health checks for local brain files and optional integrations. |
| `project-brain-lint <project-root>` | Lint wiki structure, links, metadata, and brain hygiene. |
| `project-brain-reset [project-root] [options]` | Preview or execute safe brain deletion. |
| `project-brain-audit-open <project-root>` | Open or review pending audit artifacts. |
| `project-brain-hook-install <project-root>` | Install an optional Git post-commit lint summary hook. |

### Reset command options

```text
project-brain-reset [path] [options]

Arguments:
  path        Project root directory (default: current directory)

Options:
  --dry-run          Preview what would be deleted (default behavior)
  --confirm          Execute deletion (irreversible)
  --mempalace-only   Delete only the MemPalace wing, keep local files
  --local-only       Delete only .brain/ and graphify-out/, keep MemPalace
  --help             Show help
```

## Brain reset and deletion safety

Project Brain includes a reset system designed to be explicit, previewable, and narrow in scope.

### What reset can delete

- The resolved project wing in MemPalace, drawer by drawer.
- The local `.brain/` directory.
- The local `graphify-out/` directory.

### What reset never deletes

- Project source files.
- Git history.
- Files outside `.brain/` and `graphify-out/`.
- Other MemPalace wings.
- Other projects' diary entries or memories.

### Required safe workflow for agents

When a user asks to delete or reset a brain, the assistant should:

1. Run `project-brain-reset <project-root> --dry-run`.
2. Show the dry-run output to the user.
3. Ask for explicit confirmation after the user has read the output.
4. Only then run `project-brain-reset <project-root> --confirm`.
5. Offer to run `project-brain-init` again if the user wants a clean rebuild.

Reset is irreversible. MemPalace drawer deletion cannot be undone by Project Brain.

## MemPalace bridge support

MemPalace MCP tools normally live inside the assistant runtime, while `project-brain-reset` runs as a shell command. A shell process cannot call in-session MCP tools unless the runtime provides a bridge.

Project Brain supports an explicit bridge command through `PROJECT_BRAIN_MEMPALACE_BRIDGE`:

```bash
export PROJECT_BRAIN_MEMPALACE_BRIDGE="/path/to/mempalace-bridge"
```

The bridge must accept this interface:

```text
<bridge-command> <tool-name> <json-arguments>
```

It must print a JSON result to stdout.

Required tool names:

- `mempalace_list_rooms`
- `mempalace_list_drawers`
- `mempalace_delete_drawer`

If no bridge is configured, Project Brain fails closed for MemPalace deletion and can still perform local-only deletion when explicitly requested.

## Generated files

A typical initialized project receives this local structure:

```text
.brain/
  CLAUDE.md
  wiki/
    index.md
    architecture.md
    decisions.md
    open-questions.md
  state/
    session-brief.md
  log/
  raw/

graphify-out/
  GRAPH_REPORT.md
```

The exact contents can evolve as the brain is maintained.

## Safety model

Project Brain is designed around conservative defaults:

- Dry-run first for destructive actions.
- No source-code deletion path.
- No direct ChromaDB file deletion.
- MemPalace wings are cleared only by listing rooms, listing drawers, and deleting each drawer ID.
- Missing optional integrations are warnings, not fake successes.
- Local brain state is stored in visible project directories.

## Badges

The badges in this README are live Shields.io SVG badges. They are intentionally limited to facts this archive can support: version, license, Python compatibility, plugin type, and alpha status.

This README does not include fake build, coverage, npm, PyPI, or GitHub release badges because this archive does not include a public repository or CI configuration.

## Troubleshooting

### `project-brain-reset` says MemPalace is unavailable

That usually means the shell process cannot access MCP tools. Configure `PROJECT_BRAIN_MEMPALACE_BRIDGE` or run a local-only reset:

```bash
project-brain-reset /path/to/project --local-only --confirm
```

### `project-brain-doctor` reports Graphify missing

Install or enable Graphify in your environment, then regenerate graph output from the project source code. Do not run Graphify on `.brain/wiki/`; the wiki is prose, not the dependency graph source.

### A fresh brain has a low health score

A newly scaffolded brain may be structurally valid but knowledge-poor. Health improves after source files are read, wiki pages are compiled from primary sources, Graphify is run, and memory is mined.

### The Git hook dirties the working tree

`project-brain-hook-install` writes lint summaries to `.brain/log/git-hooks.md` after commits. Treat the hook as opt-in. If that behavior does not fit your workflow, do not install the hook.

## Roadmap

Practical next steps before broad distribution:

- Add runtime-specific installation docs once the target runtime is finalized.
- Add a first-party MemPalace bridge implementation when the host runtime supports it.
- Add automated tests for scaffold, lint, doctor, reset, and hook behavior.
- Add manifest validation to CI once the repository is public.
- Split large skill guidance into smaller focused references where possible.

## Contributing

Keep changes source-grounded and conservative:

1. Do not add deletion paths that touch project source code.
2. Do not mine source code directly into MemPalace.
3. Do not fake integration success when an optional tool is missing.
4. Test command changes with temporary projects before release.
5. Keep documentation honest about alpha limitations.

## License

Project Brain is released under the MIT License. See [LICENSE](LICENSE).
