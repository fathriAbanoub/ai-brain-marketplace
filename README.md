# AI Brain Marketplace

A local plugin marketplace containing the [`project-brain`](project-brain/) plugin for OpenClaude and Claude Code.

Project Brain is a persistent, self-maintaining knowledge layer for a codebase: a source-grounded wiki, session handoffs, health checks, optional MemPalace semantic memory, and optional graphify dependency maps.

## Contents

```text
ai-brain-marketplace/
  .claude-plugin/marketplace.json
  project-brain/
    README.md
    LICENSE
    .claude-plugin/plugin.json
    bin/
    scripts/
    skills/
    tests/
```

## Install

```bash
openclaude
/plugin marketplace add /path/to/ai-brain-marketplace
/plugin install project-brain@ai-brain-marketplace
```

## Slash commands

| Command | Purpose |
| --- | --- |
| `/project-brain:brain` | Initialize, maintain, compile, and hand off a brain |
| `/project-brain:reset` | Delete MemPalace drawers (MCP) and local brain files |
| `/project-brain:doctor` | Health checks |
| `/project-brain:lint` | Validate wiki structure and wikilinks |
| `/project-brain:audit` | Review open audit artifacts |
| `/project-brain:update-check` | Compare installed vs latest versions |

## Requirements

- Python 3.9+ (stdlib only for the core scripts)
- A plugin runtime that exposes `bin/` commands and `skills/`
- Optional: MemPalace MCP tools, graphify, Obsidian MCP

## Documentation

See [project-brain/README.md](project-brain/README.md) for architecture, commands, safety model, and troubleshooting.

## License

MIT. See [project-brain/LICENSE](project-brain/LICENSE).