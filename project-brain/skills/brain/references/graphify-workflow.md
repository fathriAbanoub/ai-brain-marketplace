# graphify Workflow

graphify is installed and its SKILL.md is registered. Use it via the `/graphify` skill trigger or shell commands.

MemPalace is already installed as a plugin. graphify is already installed as a CLI tool and skill. Do not reinstall either.

## Invocation modes

### Skill mode

Use skill mode when the agent should run the full graphify pipeline with its own instructions:

```text
/graphify <path>
```

Use this for first-time graph builds, broad relationship analysis, architecture mapping, and when the user asks how pieces connect.

### Shell mode

Use shell mode for targeted operations in bash:

```bash
graphify <subcommand>
```

Use this when the task requires a specific graphify operation, such as querying an existing graph, refreshing output, or merging graphs.

## What graphify owns

graphify owns generated graph artifacts such as:

- `graphify-out/graph.html`
- `graphify-out/graph.json`
- `graphify-out/GRAPH_REPORT.md`
- graphify cache/output files

The brain plugin does not duplicate those files.

## What the brain plugin owns

The brain plugin owns the durable synthesis of graph findings:

- summaries in `.brain/wiki/architecture/`,
- concept pages in `.brain/wiki/concepts/`,
- decision records in `.brain/wiki/decisions/`,
- open questions and verification leads in `.brain/wiki/open-questions.md`,
- session handoff notes in `.brain/state/session-brief.md`.

The brain links to graphify output and summarizes stable findings. It does not paste the entire graph report into the wiki.

## Build graph

Run graphify when:

- a new project brain is initialized,
- code or docs changed significantly,
- the user asks how systems connect,
- a wiki page needs architecture evidence,
- the agent is lost in the codebase,
- two project brains need a cross-repo map.

Before a full build, review `.graphifyignore` so caches, generated files, secrets, raw binaries, and noisy folders do not pollute the graph.

## Use during work

Use graphify for:

- code navigation,
- architecture maps,
- dependency relationships,
- identifying god nodes,
- finding bridge files between subsystems,
- detecting isolated or orphaned areas,
- suggesting new questions.

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

