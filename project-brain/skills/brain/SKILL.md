---
description: Use when the user wants a persistent AI brain, project memory, LLM wiki, personal knowledge base, model handoff memory, architecture/codebase brain, source ingestion workflow, Obsidian vault mirror, cross-project brain coordination, or any workflow combining raw sources, wiki synthesis, MemPalace memory, graphify graphs, logs, audits, health metrics, and session handoffs. This skill initializes and maintains a layered brain where `.brain/raw/` stores immutable evidence, `.brain/wiki/` stores compiled markdown knowledge, MemPalace stores verbatim session memory and user preferences, graphify maps relationships across code/docs/sources, Obsidian MCP mirrors selected wiki pages to the user's vault, and `.brain/state/session-brief.md` lets a future model recover context after a reset or model change.
---

# Project Brain

Build and maintain a persistent AI brain for the current project. This skill is not only an LLM Wiki scaffold. The LLM Wiki is the compiled-knowledge layer; after wiki edits, synchronize the graph, memory, log, audit, health, vault, and handoff layers so the next model can understand the project without this chat.

## Core model

The brain has six coordinated layers:

1. **Evidence** — `.brain/raw/` and repository files. These are the source of truth.
2. **Synthesis** — `.brain/wiki/`. These are small, linked markdown pages maintained by the agent.
3. **Memory** — MemPalace. This preserves previous conversations, user preferences, diary entries, and verbatim recall.
4. **Map** — graphify output in `graphify-out/`. This captures relationships, communities, paths, god nodes, and structural hints.
5. **Handoff** — `.brain/state/session-brief.md`. This is the short briefing a future model should read first.
6. **Vault** — Obsidian MCP. The wiki can be mirrored to the user's Obsidian vault for human browsing, graph view, and annotation. See `references/obsidian-workflow.md`.

Never treat one layer as the whole brain. A healthy project brain keeps the layers aligned.

## Required first move

At the start of any serious project-brain session:

1. Identify the project root. If unsure, use the current working directory.
2. If `.brain/CLAUDE.md` exists, read it first.
3. If `.brain/CLAUDE.md` does not exist and the user asked to set up a brain, run:

```bash
project-brain-init <project-root> "<Project Name>"
```

4. Read `.brain/state/session-brief.md` if present.
5. Read `.brain/wiki/index.md` if present.
6. Read `graphify-out/GRAPH_REPORT.md` before architecture, code navigation, or broad relationship questions if it exists.
7. Check MemPalace before making claims about previous decisions, user preferences, or past work. Call `mempalace_status` when the tool is available, then use `mempalace_search` for relevant memory.
8. If Obsidian MCP tools are available, note that the brain wiki can be synced to the vault. Do not sync automatically — wait for the user to request it.
9. If a tool is not available in the current session, say exactly which layer is unavailable and continue from the remaining layers.

## Behavioral Contracts

### Contract 1: Never claim MemPalace is unavailable without checking

Before saying "MemPalace is unavailable", call `mempalace_status`. If the MCP tool is present, MemPalace is available. The plugin is installed. There is no fallback scenario unless the tool call itself fails.

### Contract 2: Never reinvent graphify

Do not write Python scripts to parse code structure, extract relationships, or build knowledge graphs. That is graphify's job. If a relationship question requires graph traversal, use `/graphify query` or `graphify query "<question>"`. If graphify output is missing, rebuild it with `/graphify .` — do not substitute manual file scanning.

### Contract 3: Never let wiki edits be the last step

Every wiki edit must be followed by the post-wiki checklist. No exceptions. The checklist is not optional friction — it is what makes the brain durable.

### Contract 4: The session brief must be readable in under 2 minutes

If the session brief exceeds 400 words, trim it. Depth belongs in wiki pages, not the brief. The brief is a map to the wiki, not a replacement for it.

### Contract 5: Obsidian sync is opt-in

Never push to the Obsidian vault without the user asking. The vault is the user's personal space. The brain writes to `.brain/wiki/` first; the vault is a view layer the user controls.

### Contract 6: Route to the right layer first

Before answering any question from the brain, identify the question type and consult `references/retrieval-strategy.md` or the routing table in `references/agent-playbook.md`. Do not default to reading the wiki index for every question. Code navigation questions go to graphify first. Decision questions go to MemPalace first. Status questions go to the session brief first. Using the wrong layer first wastes turns and risks stale answers.

## Canonical lifecycle

Use `references/brain-lifecycle.md` as the primary runbook. The short version:

1. **Orient** from schema, session brief, wiki index, graph report, and MemPalace.
2. **Ingest** new evidence into `.brain/raw/` or pointer files.
3. **Compile** durable knowledge into `.brain/wiki/`.
4. **Graph** with graphify and promote stable graph findings into the wiki.
5. **Remember** with MemPalace diary/preferences/decision context.
6. **Mirror** selected wiki pages to Obsidian only when requested.
7. **Audit** with linting, open questions, contradiction tracking, and feedback files.
8. **Handoff** by updating session brief, log, and next actions.

If the user asks "what should the AI do after LLM Wiki?", the answer is: run the post-wiki synchronization loop in `references/post-wiki-checklist.md`.

## Operation modes

### Initialize

Use when the project has no brain yet or the user asks to create/install/set up the brain.

Steps:

1. Run `project-brain-init <project-root> "<Project Name>"`.
2. Read the files it created.
3. Run `project-brain-doctor <project-root>`.
4. Report the current availability of MemPalace MCP, graphify CLI, and Obsidian MCP. Do not give install instructions unless the user asks.
5. Recommend keeping the generated Project Brain block in root `CLAUDE.md`.
6. Ask for first sources only if the user has not already supplied a clear next step.

MemPalace is already installed as a plugin. graphify is already installed as a CLI tool and skill. Do not reinstall either.

### Wake up / orient

Use at the start of a new session, after a model change, or when the user says to continue from memory.

Steps:

1. Read `.brain/CLAUDE.md`.
2. Read `.brain/state/session-brief.md`.
3. Read `.brain/wiki/index.md`.
4. Read `graphify-out/GRAPH_REPORT.md` if present.
5. Call `mempalace_status` and search MemPalace for the project name, current task, recent decisions, and relevant user preferences when available.
6. Produce a short orientation: project purpose, current state, architecture map, decisions, risks, and next read targets.
7. Update the session brief if it is stale.

### Ingest

Use when the user adds a source, explains something important, links docs, uploads notes, asks to process a codebase, or gives new project context.

Steps:

1. Store the material in `.brain/raw/` or create a pointer file in `.brain/raw/refs/` according to `references/evidence-lifecycle.md`.
2. Extract claims, entities, relationships, decisions, uncertainties, and useful quotes.
3. Create or update a source summary under `.brain/wiki/sources/`.
4. Update affected architecture, concept, entity, synthesis, and decision pages.
5. Update `.brain/wiki/index.md`.
6. Run the post-wiki checklist.

### Query

Use when answering questions from the brain.

Steps:

1. Identify the question type and route to the right layer first using `references/retrieval-strategy.md` or the routing table in `references/agent-playbook.md`.
2. Read only the relevant pages, graph reports, memories, logs, or raw sources needed for that question type.
3. Use graphify first for relationship, architecture, path, dependency, or code-navigation questions.
4. Search MemPalace first for prior decisions, preferences, or previous session context.
5. Check raw sources first for high-stakes, uncertain, or contested evidence claims.
6. Answer with clear citations/paths/wikilinks and state confidence when only one layer supports the answer.
7. If the answer is durable, save it under `.brain/outputs/queries/` or promote it into `.brain/wiki/`.
8. Log and update handoff state when project understanding changed.

### Build or refresh graph

Use when the user asks how pieces connect, when code/docs/raw sources changed, or after initial brain setup.

Steps:

1. Create or review `.graphifyignore` to exclude noisy or sensitive paths.
2. Use `/graphify .` for the full skill pipeline, or `graphify <subcommand>` for targeted shell operations.
3. Read `graphify-out/GRAPH_REPORT.md`.
4. Extract god nodes, communities, surprising edges, and suggested questions.
5. Update architecture/concept pages with stable findings.
6. Add graph-derived leads to `.brain/wiki/open-questions.md` until verified.
7. Log the graph refresh.

### Consolidate memory

Use after significant project conversations, decisions, preference changes, or handoffs.

Steps:

1. Call `mempalace_status`.
2. Search MemPalace before making claims about previous work.
3. Write a concise diary entry with `mempalace_diary_write` after substantial work, decisions, or context changes.
4. Store user preferences with `mempalace_preferences_set` when they should survive model switches.
5. Convert stable memory into wiki pages, decisions, or `.brain/CLAUDE.md` preferences.
6. Never store secrets.

### Sync to Obsidian

Use when the user asks to view, browse, save, mirror, sync, or open brain content in Obsidian, or asks for the vault to reflect current brain state.

Steps:

1. Read `references/obsidian-workflow.md`.
2. Identify which wiki pages have changed since last sync by checking `.brain/log/` for the last sync timestamp.
3. Use Obsidian MCP write tools to mirror changed pages to `<vault>/project-brains/<project-name>/`.
4. Preserve all wikilinks — they work natively in Obsidian.
5. Do not sync `.brain/raw/`, `.brain/log/`, `.brain/audit/`, or `.brain/state/` unless explicitly requested.
6. Log the sync.

### Audit / lint

Use periodically, after large updates, or when the user asks whether the brain is healthy.

Steps:

1. Run `project-brain-lint <project-root>` or `project-brain-lint <project-root> --json` when a tool needs machine-readable output.
2. Run `project-brain-doctor <project-root>` for health scores.
3. Process `.brain/audit/*.md` from highest severity to lowest.
4. Find broken links, unindexed pages, orphan pages, stale claims, missing decisions, contradictions, vague summaries, missing source citations, and stale raw evidence.
5. Use raw files, graphify, and MemPalace to resolve.
6. Move resolved audit notes to `.brain/audit/resolved/` with a resolution.
7. Log the audit.

### Handoff

Use before ending a large session, before compaction, after major work, or when the user asks for continuity.

Steps:

1. Update `.brain/state/session-brief.md`.
2. Keep it under 400 words.
3. Include current state, active workstream, recent decisions, files changed, brain pages changed, risks, and exact next read targets.
4. Add next actions as checkboxes.
5. Write a MemPalace diary entry if available.
6. Append a log entry.

### Cross-brain coordination

Use when the user works across multiple projects or asks to connect one project brain to another.

Steps:

1. Read `references/cross-brain-workflow.md`.
2. Create pointer files rather than duplicating pages across projects.
3. Store global user preferences in MemPalace, not in every project wiki.
4. Use graphify `merge-graphs` only when a cross-repo relationship map is needed.
5. Write a multi-project session brief that names each project and its next read targets.

### Self-correction scan

Use when `project-brain-doctor` shows health below 70/100, when the session brief is more than 7 days old, or when the user asks whether the brain is healthy or up to date.

Steps:

1. Run `project-brain-doctor <project-root>` and read all four scores.
2. For each score below 70, run the matching repair from `references/brain-lifecycle.md` → Self-correction scan.
3. Run `project-brain-lint <project-root>` and clear all error-level issues.
4. Log the scan result.
5. Update session brief.

## Non-negotiable post-wiki loop

Every time wiki pages change, perform this loop unless impossible:

1. Update index.
2. Add cross-links and backlinks.
3. Extract decisions.
4. Sync graphify if structure changed.
5. Sync MemPalace if session memory changed.
6. Record contradictions/open questions.
7. Update session brief.
8. Append log entry.
9. Run lint for large changes.

The wiki is not the finish line; it is the compiled layer that must be wired back into the rest of the brain.

## Evidence hierarchy

When layers disagree, trust evidence in this order:

1. Raw sources and repository files.
2. Decision pages with source links.
3. Wiki synthesis.
4. graphify extracted relationships.
5. graphify inferred relationships.
6. MemPalace recollections.
7. Current chat claims.

Do not erase disagreement. Record the conflict and update the stale layer after verification.

## Supporting references

Load these only when relevant:

- `references/agent-playbook.md` — decision tree for what the agent should do next.
- `references/audit-workflow.md` — how to process human feedback.
- `references/brain-architecture.md` — detailed architecture of the six brain layers.
- `references/brain-health-metrics.md` — measurable brain health scoring.
- `references/brain-lifecycle.md` — full end-to-end workflow and definitions of done.
- `references/cross-brain-workflow.md` — linking multiple project brains without duplication.
- `references/evidence-lifecycle.md` — raw evidence intake, pointer files, aging, and contradictions.
- `references/graphify-workflow.md` — how to use graphify as the relationship graph layer.
- `references/handoff-protocol.md` — how to prepare a future model.
- `references/install-and-integration.md` — actual dependency state, plugin layout, verification, and CLAUDE.md integration.
- `references/mempalace-workflow.md` — how to use MemPalace MCP as the memory layer.
- `references/obsidian-workflow.md` — how to mirror wiki pages to Obsidian via MCP.
- `references/post-wiki-checklist.md` — exact checklist after wiki edits.
- `references/wiki-schema.md` — page formats, frontmatter, index rules.

## Completion standard

A response or operation is not complete until the agent can answer:

1. What changed?
2. Why did it change?
3. Which evidence supports it?
4. Which relationships matter?
5. What memory should survive?
6. What should the next model read first?
7. What should happen next?
