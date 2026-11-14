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
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}"
# A stale CLAUDE_PLUGIN_ROOT (moved/foreign copy) must not skip discovery:
# validate it against bin/ and clear it when invalid; a valid one is kept.
if [ -n "$PLUGIN_ROOT" ] && [ ! -d "$PLUGIN_ROOT/bin" ]; then
  PLUGIN_ROOT=""
fi
# If still empty: the harness prints "Base directory for this skill: <path>"
# directly above this skill's text (verified in --plugin-dir sessions, where
# the marketplace paths below do not exist). Do NOT count dirname levels by
# hand — a wrong depth guess cascades into a filesystem hunt that can end on
# a foreign copy of the plugin. Set BASE_DIR to that path and take the first
# candidate that actually contains the plugin's bin/. The candidate loop
# runs only when PLUGIN_ROOT is still empty — never overwrite a resolved root.
if [ -z "$PLUGIN_ROOT" ]; then
  BASE_DIR='<path-from-that-line>'
  for _c in "$BASE_DIR" "$(dirname "$BASE_DIR")" "$(dirname "$(dirname "$BASE_DIR")")"; do
    if [ -d "$_c/bin" ]; then PLUGIN_ROOT="$_c"; break; fi
  done
fi
# Verify before use: ls "$PLUGIN_ROOT/bin" must list the project-brain-* wrappers.
: "${PLUGIN_ROOT:=$(ls -d ~/.openclaude/plugins/cache/ai-brain-marketplace/project-brain/*/ 2>/dev/null | sort -V | tail -1)}"
: "${PLUGIN_ROOT:=$HOME/.openclaude/plugins/marketplaces/ai-brain-marketplace/project-brain}"
"$PLUGIN_ROOT/bin/project-brain-update-check"
```

Never type a bare `project-brain-*` command. The wrappers are not on PATH in
this harness; every bare attempt wastes a turn, and roughly three
consecutive failed Bash calls abort the whole session. Every
`project-brain-*` command in this skill means `"$PLUGIN_ROOT/bin/<command>"`,
with PLUGIN_ROOT read from `.brain/state/plugin-root.txt` (written by init)
or resolved by the fallback above.

If PLUGIN_ROOT still cannot be resolved after all of the above, STOP and
report exactly which paths you tried. NEVER write or modify `.brain/` files
by hand as a substitute for the scripts — a brain the scripts did not build
is unverifiable and counts as failure, not as a completed step.

Persist the resolved PLUGIN_ROOT only when this project already has a brain:
write `.brain/state/plugin-root.txt` only if `.brain/state/` already exists.
The update check also runs in projects without a brain — never create the
directory (or any part of `.brain/`) here; a half-initialized brain is worse
than none:

```bash
if [ -d .brain/state ]; then
  printf '%s' "$PLUGIN_ROOT" > .brain/state/plugin-root.txt
fi
```

In every LATER shell, try the persisted value first (with a staleness check —
a moved plugin must fall back to re-resolution, never be used blindly):

```bash
PLUGIN_ROOT="$(cat .brain/state/plugin-root.txt 2>/dev/null || true)"
[ -n "$PLUGIN_ROOT" ] && [ -d "$PLUGIN_ROOT/bin" ] || PLUGIN_ROOT=""
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

See `../brain/references/harness-detection.md` for how to detect which harness you're in.
