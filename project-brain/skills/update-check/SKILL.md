---
description: Use when the user wants to check for updates to project-brain tools, check if mempalace or graphify are outdated, or see what tool versions are installed vs latest on PyPI. Reports installed vs latest versions and prints upgrade commands. Does not install anything automatically.
---

# Project Brain Update Check

Check whether mempalace, graphify, and the project-brain plugin are up to date.

## Run the checker

```bash
project-brain-update-check
```

If not on PATH (exit 127):

```bash
# Option 1: OpenClaude plugin cache
PLUGIN_ROOT="$(ls -d ~/.openclaude/plugins/cache/ai-brain-marketplace/project-brain/*/ 2>/dev/null | sort -V | tail -1)"
"$PLUGIN_ROOT/bin/project-brain-update-check"

# Option 2: marketplace repo directly
~/.openclaude/plugins/marketplaces/ai-brain-marketplace/project-brain/bin/project-brain-update-check
```

## What it checks

| Tool | How checked |
|------|-------------|
| project-brain plugin | Reads version from plugin.json |
| mempalace binary | `mempalace --version` vs PyPI latest |
| mempalace plugin cache | `~/.openclaude/plugins/cache/mempalace/mempalace/` |
| graphify binary | `graphify --version` vs PyPI latest (`graphifyy` package) |

Exit code 0 = all current. Exit code 1 = something is outdated.

## Updating outdated tools

The checker prints the exact commands when something is behind. Common cases:

```bash
# Update mempalace
uv tool install mempalace --upgrade

# Update graphify (PyPI package is "graphifyy" with double-y)
uv tool install graphifyy --upgrade
```

After updating graphify, rebuild the graph in any active project:
```bash
graphify update .
```

## Harness differences

- **OpenClaude**: mempalace runs as a plugin. The binary on PATH and the plugin cache version should match. After upgrading the binary, restart OpenClaude to pick up the new version.
- **Claude Code**: mempalace runs as an MCP server. After upgrading, restart Claude Code.

See `references/harness-detection.md` for how to detect which harness you're in.
