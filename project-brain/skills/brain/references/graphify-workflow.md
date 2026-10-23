# graphify Workflow

graphify is installed as both a CLI tool and an MCP server (graphify 0.9.92+). Use it via `/graphify` skill, shell commands, or MCP tools depending on the task.

> Version note: the command guidance in this file is verified against
> graphify 0.9.93; check yours with `uv tool list | grep graphify`.

## Finding the binary

```bash
which graphify          # usually ~/.local/bin/graphify
which graphify-mcp      # usually ~/.local/bin/graphify-mcp
graphify --version      # verify installed version
```

If not on PATH, check:
- `~/.local/bin/graphify` (uv tool install location)
- `~/.local/share/uv/tools/graphifyy/bin/graphify` (uv isolated env)

Note: graphify is installed via `uv tool install graphifyy` (double-y package name on PyPI). The binaries are named `graphify` and `graphify-mcp` without the extra y.

## Invocation modes

### Skill mode

Use the skill for first-time graph builds, broad relationship analysis, architecture mapping, and when the user asks how pieces connect:

```text
/graphify <path>
```

### Shell mode

Use for targeted operations:

```bash
graphify extract <path>                  # full build or rebuild (semantic pass costs API calls)
graphify update <path>                   # incremental AST update (no API cost)
graphify query "<question>"              # natural language query over the graph
graphify path "<NodeA>" "<NodeB>"        # shortest path between two nodes
graphify explain "<concept>"             # explain a concept using graph context
graphify watch <path>                    # watch mode: auto-rebuild code changes (Ctrl+C to stop)
graphify cluster-only <path>             # (re)cluster and write GRAPH_REPORT.md / graph.html
```

There is no `build` subcommand and no `report` subcommand in the graphify CLI
(verified against graphify 0.9.93's dispatch). The full build is
`graphify extract`.
`GRAPH_REPORT.md` is written by `update`/`watch` rebuilds and by
`cluster-only` — a full `extract` intentionally stops at `graph.json` +
analysis and does NOT write the report.

`update` re-extracts code files only (AST, no LLM). Doc/paper/image changes
need the `/graphify --update` skill (LLM semantic pass) or a full
`/graphify .` run.

### MCP server mode

Install graphify with MCP support: `uv tool install "graphifyy[mcp]"`. The base install does not include the MCP server.

graphify-mcp is registered in `~/.mcp.json` and loads automatically in OpenClaude sessions. It serves MCP tools over stdio, using `graphify-out/graph.json` relative to the session's working directory.

**If MCP tools are not present in the session:**

The server needs a `graph.json` to exist at `graphify-out/graph.json` in the project root. If it doesn't exist yet:

```bash
graphify extract .              # builds graphify-out/graph.json (no `build` subcommand exists)
```

Then restart the MCP server (restart OpenClaude or reconnect). The graphify-mcp server can also be started manually for a specific graph:

```bash
graphify-mcp graphify-out/graph.json          # stdio transport (default)
graphify-mcp --graph graphify-out/graph.json  # equivalent
```

**MCP tools exposed by graphify-mcp** (use `graphify_*` prefix in tool calls — exact names depend on the server version; check the available tools list in the current session):

- Query tools: search nodes, traverse edges, find paths between nodes
- Analysis tools: identify god nodes, orphaned modules, community clusters
- Report tools: generate summaries and relationship maps

When graphify MCP tools are available in the session, prefer them over shell commands for interactive queries — they return structured data rather than text output.

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

For incremental updates after editing code files in a session: `graphify update .` (AST-only, no API cost).

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

Do not reinvent graphify with custom file-parsing scripts. When the question is about relationships, ask graphify.

## Compile findings into wiki

After reading graphify output:

1. Promote stable relationships into architecture pages.
2. Put unverified inferred links into `.brain/wiki/open-questions.md`.
3. Add wikilinks between related pages.
4. Update `.brain/wiki/index.md`.
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

If graphify MCP tools are missing from the session:

1. Check that `graphify-out/graph.json` exists in the project root. If not, run `graphify extract .` first.
2. Check that `~/.mcp.json` has a `graphify` entry pointing to the result of `which graphify-mcp`.
3. Fall back to shell commands (`graphify query`, `graphify path`, `graphify explain`) for the same queries.
4. Fall back to reading `graphify-out/GRAPH_REPORT.md` directly for structural overviews.

Never grep the source tree manually to answer relationship questions that graphify can answer.
