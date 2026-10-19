# Harness Detection and Tool Updates

How to detect whether you're running in OpenClaude or Claude Code, and how to update mempalace/graphify in each.

## Detecting the harness

Check in this order:

1. **OpenClaude** — the `OPENCLAUDE` environment variable is set, or the session prompt mentions "OpenClaude". The plugin system uses `~/.openclaude/`. MCP tools are loaded from `~/.openclaude/plugins/`.

2. **Claude Code** — no `OPENCLAUDE` env var. Plugin system uses `~/.claude/`. MCP servers are configured in `~/.claude/settings.json` under `mcpServers`.

3. **Ambiguous** — run `echo $OPENCLAUDE` in bash. Empty = Claude Code. Non-empty (any value) = OpenClaude.

```bash
# Quick harness check
echo "OPENCLAUDE=${OPENCLAUDE:-<unset>}"
ls ~/.openclaude/plugins/ 2>/dev/null && echo "OpenClaude plugins dir exists" || echo "no OpenClaude plugins dir"
ls ~/.claude/settings.json 2>/dev/null && echo "Claude Code settings exist" || echo "no Claude Code settings"
```

## Updating mempalace

### OpenClaude (plugin-managed)

mempalace is installed as an OpenClaude plugin, not a standalone binary. The plugin version in the cache is what runs:

```
~/.openclaude/plugins/cache/mempalace/mempalace/<version>/
```

To update:
1. Check current plugin version: `ls ~/.openclaude/plugins/cache/mempalace/mempalace/`
2. Check PyPI latest: `pip index versions mempalace 2>/dev/null | head -1` or visit pypi.org/project/mempalace
3. Update the binary: `uv tool install mempalace --upgrade` or `pip install --upgrade mempalace`
4. If the plugin cache is separate from the binary, copy or re-install the plugin through OpenClaude's plugin manager UI or by running the marketplace install command

**The binary PATH matters too.** If `mempalace --version` is outdated but the plugin cache is current, the agent uses the plugin version — but CLI tools like `mempalace status` use the PATH binary. Keep them in sync.

### Claude Code (MCP server)

mempalace runs as an MCP server configured in `~/.claude/settings.json`. To update:

```bash
uv tool install mempalace --upgrade
# Then restart Claude Code to pick up the new binary
```

Verify after restart: the `mempalace_status` tool response shows the version.

## Updating graphify

graphify is a CLI tool in both harnesses — the update command is the same either way:

```bash
uv tool install graphifyy --upgrade   # note: PyPI package is "graphifyy" (double-y)
graphify --version                    # confirm new version
```

After updating, run `graphify update .` in any active project to rebuild the graph with the new version.

## Running project-brain-update-check

The built-in update checker reports all three:

```bash
project-brain-update-check
```

If the binary is not on PATH, find it via the plugin root (same fallback as all project-brain commands — see SKILL.md).

The checker exits 0 if all current, 1 if any are outdated. It prints the exact `uv tool install` command for anything behind.

## Summary table

| Tool | OpenClaude update | Claude Code update |
|------|------------------|--------------------|
| mempalace (binary) | `uv tool install mempalace --upgrade` | `uv tool install mempalace --upgrade` |
| mempalace (plugin cache) | Re-install via OpenClaude plugin manager | N/A — no plugin cache |
| graphify | `uv tool install graphifyy --upgrade` | `uv tool install graphifyy --upgrade` |
| project-brain plugin | Pull latest from marketplace repo | Pull latest from marketplace repo |
