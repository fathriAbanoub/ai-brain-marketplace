# graphify Workflow

graphify maps relationships across code and docs. Three ways to use it, in
priority order:

1. **`/graphify` skill — PRIMARY for builds and rebuilds.** Invoke the skill
   (`/graphify <path>`); per this project's setup (reported, verify on first
   use) it runs the semantic pass through the session's own model. If it
   reports a missing backend, use the labeled CLI fallback with
   `GRAPHIFY_BACKEND=none` on both `extract` and `cluster-only`.
2. **graphify MCP tools — PRIMARY for queries** once a graph exists (deferred;
   see "MCP server mode" below).
3. **CLI — FALLBACK ONLY**, when the skill is unavailable or you need a single
   targeted operation from the shell.

> Version note: the CLI guidance below is verified against graphify 0.9.93;
> check yours with `uv tool list | grep graphify`.

## Finding the binary (fallback only)

```bash
which graphify          # usually ~/.local/bin/graphify
which graphify-mcp      # usually ~/.local/bin/graphify-mcp
graphify --version      # verify installed version
```

If not on PATH, check:
- `~/.local/bin/graphify` (uv tool install location)
- `~/.local/share/uv/tools/graphifyy/bin/graphify` (uv isolated env)

Note: graphify is installed via `uv tool install graphifyy` (double-y package
name on PyPI). The binaries are named `graphify` and `graphify-mcp` without
the extra y.

## Invocation modes

### Skill mode (primary)

Use the `/graphify` skill for first-time graph builds, full rebuilds, broad
relationship analysis, architecture mapping, and when the user asks how pieces
connect:

```text
/graphify <path>
```

`/graphify` is a skill invocation, not a shell command — never type it into
Bash. In a CLI-only environment (graphify on PATH, skill not installed), use
the CLI fallback below instead.

### MCP server mode (queries)

graphify-mcp is registered in `~/.mcp.json` and loads automatically in
OpenClaude sessions. It serves MCP tools over stdio, reading
`graphify-out/graph.json` relative to the session's working directory — the
server is read-only over an already-built graph and loads it at startup.

**The tools are deferred.** They appear only by name in the deferred-tools
list; load the schemas before first use with ONE ToolSearch call (query
`select:<full name 1>,<full name 2>` — comma-separated exact full names — and
`max_results` at least the number of names; see the plugin's
`references/deferred-tools.md`).

**MCP tools exposed by graphify-mcp** (10; exact prefixed names carry the
server's `mcp__…` prefix):

| Tool | Answers | CLI equivalent (fallback) |
|---|---|---|
| `query_graph` | natural-language relationship questions | `graphify query "<q>"` |
| `shortest_path` | connection between two nodes | `graphify path "<A>" "<B>"` |
| `get_node` | one concept/node explained with graph context | `graphify explain "<concept>"` |
| `get_neighbors` | what connects to a node | — |
| `get_community` | one community's members | — |
| `god_nodes` | hub nodes with the most connections | — |
| `graph_stats` | size/shape of the graph | — |
| `get_pr_impact` | what a change would touch | — |
| `list_prs` | PR impact listing | — |
| `triage_prs` | PR triage over the graph | — |

**Reconnect after the first build.** The server reads `graph.json` at startup,
so a graph built later in the same session is invisible to it. After the
FIRST successful build (or any full rebuild), reconnect the graphify MCP
server (restart the session or reconnect the server) before using the query
tools. Until then, use the CLI fallback or read
`graphify-out/GRAPH_REPORT.md` directly.

**If the MCP tools are neither in the tool list nor the deferred list:** the
graph probably does not exist yet — build it via the `/graphify` skill first,
then reconnect the server.

### CLI mode (fallback only)

```bash
graphify extract <path>                  # full build or rebuild
graphify update <path>                   # incremental AST update (no API cost)
graphify query "<question>"              # natural language query over the graph
graphify path "<NodeA>" "<NodeB>"        # shortest path between two nodes
graphify explain "<concept>"             # explain a concept using graph context
graphify watch <path>                    # watch mode: auto-rebuild code changes (Ctrl+C to stop)
graphify cluster-only <path>             # (re)cluster and write GRAPH_REPORT.md / graph.html
```

**`GRAPHIFY_BACKEND=none` — the one CLI trap that corrupts output.** If
`OPENAI_API_KEY` is set in the environment, graphify auto-selects an openai
backend and fails when the `openai` package is missing. Set
`GRAPHIFY_BACKEND=none` for BOTH `extract` AND `cluster-only` — setting it on
only one of them produced 79 "Community N" placeholder communities live
(observed: the agent set it on `extract`, forgot it on `cluster-only`). In
`none`-backend mode doc files get no nodes (only code is indexed).

`watch` needs the optional `watch` extra (it provides `watchdog`): install with
`uv tool install "graphifyy[watch]"` (verified in the graphifyy 0.9.93 package
metadata: `Provides-Extra: watch`, `Requires-Dist: watchdog; extra == "watch"`).
Watch mode stays optional — no workflow step below requires it.

There is no `build` subcommand and no `report` subcommand in the graphify CLI
(verified against graphify 0.9.93's dispatch). The full build is
`graphify extract`.
`GRAPH_REPORT.md` is written by `update`/`watch` rebuilds and by
`cluster-only` — a full `extract` intentionally stops at `graph.json` +
analysis and does NOT write the report.

`update` re-extracts code files only (AST, no LLM). Doc/paper/image changes
need the `/graphify` skill (LLM semantic pass) or a full `/graphify .` run.

## What graphify owns

graphify owns generated graph artifacts:

- `graphify-out/graph.json` — the graph data
- `graphify-out/graph.html` — interactive visualization
- `graphify-out/GRAPH_REPORT.md` — human-readable report

The brain plugin does not duplicate those files.

## What the brain plugin owns

The brain plugin owns the durable synthesis of graph findings:

- summaries in `.brain/wiki/architecture/`
- concept pages in `.brain/wiki/concepts/`
- decision records in `.brain/wiki/decisions/`
- open questions and verification leads in `.brain/wiki/open-questions.md`
- session handoff notes in `.brain/state/session-brief.md`

The brain links to graphify output and summarizes stable findings. It does not paste the entire graph report into the wiki.

## When to run graphify

Run graphify when:

- a new project brain is initialized
- code or docs changed significantly
- the user asks how systems connect
- a wiki page needs architecture evidence
- the agent is lost in the codebase
- two project brains need a cross-repo map

For incremental updates after editing code files in a session: `graphify update .` (AST-only, no API cost; CLI fallback — fine here because it changes no semantics).

Before a full build, review `.graphifyignore` so caches, generated files, secrets, raw binaries, and noisy folders do not pollute the graph.

## Use during work

Use graphify for:

- code navigation
- architecture maps
- dependency relationships
- identifying god nodes
- finding bridge files between subsystems
- detecting isolated or orphaned areas
- suggesting new questions

Do not reinvent graphify with custom file-parsing scripts. When the question is about relationships, ask graphify — via the MCP query tools, the skill, or the CLI fallback, in that order.

## Compile findings into wiki

After reading graphify output:

1. Promote stable relationships into architecture pages.
2. Put unverified inferred links into `.brain/wiki/open-questions.md`.
3. Add wikilinks between related pages.
4. Regenerate `.brain/wiki/index.md` with `project-brain-lint <project-root> --reindex` (never by hand).
5. Update `.brain/state/session-brief.md` when the graph changes the current mental model.
6. Log the graph run.

## Trust labels

Use this hierarchy:

1. Explicit source/repo facts.
2. graphify extracted relationships.
3. graphify inferred relationships.
4. agent hypotheses.

Inferred relationships are leads until verified from source files.

## Failure handling

If the graphify MCP tools are missing from both the tool list and the deferred list:

1. Check that `graphify-out/graph.json` exists in the project root. If not, build it via the `/graphify` skill (primary) or the CLI fallback.
2. After a build, reconnect the graphify MCP server (it reads the graph at startup) and retry.
3. Use the CLI fallback (`graphify query`, `graphify path`, `graphify explain`) for the same queries — with `GRAPHIFY_BACKEND=none` on `extract`/`cluster-only` when no API access (see above).
4. Read `graphify-out/GRAPH_REPORT.md` directly for structural overviews.

If a CLI build fails on a missing `openai` package while `OPENAI_API_KEY` is
set, re-run with `GRAPHIFY_BACKEND=none` on BOTH `extract` and `cluster-only`.

Never grep the source tree manually to answer relationship questions that graphify can answer.
