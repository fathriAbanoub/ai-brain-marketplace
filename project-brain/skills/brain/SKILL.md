---
description: Use when the user wants a persistent AI brain, project memory, LLM wiki, personal knowledge base, model handoff memory, architecture/codebase brain, source ingestion workflow, Obsidian vault mirror, cross-project brain coordination, or any workflow combining raw sources, wiki synthesis, MemPalace memory, graphify graphs, logs, audits, health metrics, and session handoffs. This skill initializes and maintains a layered brain where `.brain/raw/` stores immutable evidence, `.brain/wiki/` stores compiled markdown knowledge, MemPalace stores verbatim session memory and user preferences, graphify maps relationships across code/docs/sources, Obsidian MCP mirrors selected wiki pages to the user's vault, and `.brain/state/session-brief.md` lets a future model recover context after a reset or model change.
---

# Project Brain

Build and maintain a persistent AI brain for the current project. This skill is not only an LLM Wiki scaffold. The LLM Wiki is the compiled-knowledge layer; after wiki edits, run the post-wiki loop so the graph, memory, log, audit, health, vault, and handoff layers stay aligned and the next model can understand the project without this chat.

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

If `project-brain-init` is not on PATH (exit code 127), find the plugin root and run the script directly. Prefer the harness-provided plugin root when available (`${CLAUDE_PLUGIN_ROOT}` — substituted by OpenClaude/Claude Code in skill and command text). Resolve the fallback with standalone statements that cannot short-circuit (no `A && B` chains — a false `[ -z ]` in a chain silently exits 1 and wastes a turn):

```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}"
: "${PLUGIN_ROOT:=$(ls -d ~/.openclaude/plugins/cache/ai-brain-marketplace/project-brain/*/ 2>/dev/null | sort -V | tail -1)}"
: "${PLUGIN_ROOT:=$HOME/.openclaude/plugins/marketplaces/ai-brain-marketplace/project-brain}"
"$PLUGIN_ROOT/bin/project-brain-init" <project-root> "<Project Name>"
```

The same fallback applies to all `project-brain-*` commands: replace the bare command with `$PLUGIN_ROOT/bin/<command>` or the full marketplace path.

Version skew warning: the installed `skills/` text can be older than the installed `scripts/` (the plugin-cache resolver prefers `cache/` over `marketplaces/`). `project-brain-init` and `project-brain-doctor` print the resolved plugin root and version from `plugin.json` — check that line matches the plugin version you expect before trusting mixed output.

4. Read `.brain/state/session-brief.md` if present.
5. Read `.brain/wiki/index.md` if present.
6. Read `graphify-out/GRAPH_REPORT.md` before architecture, code navigation, or broad relationship questions if it exists.
7. Check MemPalace before making claims about previous decisions, user preferences, or past work. Before any MemPalace call, read `references/mempalace-tools.md` for the 47-tool reference, policy table, and call recipes. Call `mempalace_status` when the tool is available (preflight). If `.brain/CLAUDE.md` is missing or does not define a non-empty `mempalace_wing`, skip the MemPalace search and diary read, tell the user the brain is not initialized or configured and to run project-brain-init (or fix the file), and never infer a wing or search without one. For claims about wiki knowledge (decisions, architecture, project facts), use `mempalace_search` with the wiki wing from `.brain/CLAUDE.md`; for claims about what happened in earlier sessions (continuity, what was done last time, open threads), use `mempalace_diary_read` with the agent from `mempalace_diary_agent` in `.brain/CLAUDE.md` (for an older brain without that field, from the agent named in the diary sentence of that file; if neither exists, skip the diary and tell the user) — see the recipe in mempalace-tools.md, "Read Diary at Wake-up"; the wiki search does not read the diary and the diary read does not search wiki pages, so use the one that fits the claim, or both. **Never call `mempalace_sync` against the wiki wing** — sync prunes drawers whose source files are gitignored or deleted, and may be used on other wings only with a dry run first and explicit user confirmation. Use Recipe 3 (`mine .brain/wiki`) for normal wiki updates.
8. If Obsidian MCP tools are available, note that the brain wiki can be mirrored to the vault (vault mirror). Do not mirror automatically — wait for the user to request it.
9. If a tool is not available in the current session, say exactly which layer is unavailable and continue from the remaining layers.
10. When a wing seems missing or empty, never conclude from one tool result: MemPalace normalizes wing names (lowercase, `-` and space → `_`), so call `mempalace_list_wings` and compare normalized names before acting. An empty `mempalace_list_rooms` result is not proof the wing is empty.

## Behavioral Contracts

### Contract 1: Never claim MemPalace is unavailable without checking

Before saying "MemPalace is unavailable", call `mempalace_status`. If the MCP tool is present, MemPalace is available. The plugin is installed. There is no fallback scenario unless the tool call itself fails.

### Contract 2: Never reinvent graphify

Do not write Python scripts to parse code structure, extract relationships, or build knowledge graphs. That is graphify's job. If a relationship question requires graph traversal, use `/graphify query` or `graphify query "<question>"`. If graphify output is missing, rebuild it with `/graphify .` — do not substitute manual file scanning.

### Contract 3: Never let wiki edits be the last step

Every wiki edit must be followed by the post-wiki checklist. No exceptions. The checklist is not optional friction — it is what makes the brain durable.

### Contract 4: The session brief must be readable in under 2 minutes

If the session brief exceeds 400 words, trim it. Depth belongs in wiki pages, not the brief. The brief is a map to the wiki, not a replacement for it.

### Contract 5: Obsidian vault mirror is opt-in

Never push to the Obsidian vault without the user asking. The vault is the user's personal space. The brain writes to `.brain/wiki/` first; the vault is a view layer the user controls.

### Contract 6: Route to the right layer first

Before answering any question from the brain, identify the question type and consult `references/retrieval-strategy.md` or the routing table in `references/agent-playbook.md`. Do not default to reading the wiki index for every question. Code navigation questions go to graphify first. Decision questions go to MemPalace first. Status questions go to the session brief first. Using the wrong layer first wastes turns and risks stale answers.

### Contract 7: Primary source verification

> **PRIMARY SOURCE VERIFICATION RULE**: Before documenting any claim about a file's status, purpose, imports, or behavior — you MUST read that file directly using the Read tool. Secondary sources (GEMINI.md, critic reports, README files, any AI-generated analysis) are opinions, not evidence. If a secondary source makes a claim about a specific file (e.g. "this file is unused", "this function does X"), you must verify it by reading the actual file. If the secondary source contradicts the primary source code, document the contradiction explicitly in `sources/<filename>.md` under a `## Known Inaccuracies in This Source` section. Never copy a claim from a secondary source into the wiki architecture pages without primary verification.

**Orphaned file check**: Before marking any file as "orphaned", "unused", or "not imported": search the entire codebase for import statements, require() calls, script tags, and dynamic references to that file. Only label a file orphaned after this search returns zero results.

### Contract 8: No speculative language in architecture pages

Words like "likely", "probably", "appears to", "seems to", and "may" are banned from wiki architecture pages unless explicitly marked as a hypothesis under an open question. If you do not know how two components interact, do not guess — write "Integration method not yet verified. See [[open-questions#integration-question]]" and add the question to open-questions.md. If you do know, state it definitively and cite the file and line number.

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

If the user asks "what should the AI do after LLM Wiki?", the answer is: run the post-wiki loop in `references/post-wiki-checklist.md`.


## Brain Reset

Use brain reset only when the user explicitly requests deletion or a clean slate, when the project source code was significantly refactored and the wiki is now structurally stale, when the brain was built from inaccurate secondary sources and must be rebuilt from primary source code, or when the project has been archived and its project brain should be removed.

Do **not** reset the entire brain when a smaller repair is enough:

- If the wiki only needs normal updating, re-compile the affected wiki pages from primary sources instead.
- If MemPalace only needs to be regenerated from a still-valid wiki, delete the wing's drawers yourself with the MCP tools (see the `/project-brain:reset` skill, Step 2), then re-mine. Leave `.brain/` alone.
- If a single wiki page is wrong, fix that page and run the post-wiki loop; do not delete the whole brain.

Brain reset is irreversible. `.brain/`, `graphify-out/`, and MemPalace drawer deletions cannot be undone. The project source code must never be deleted or modified by a reset.

Correct sequence when a user requests brain deletion (full procedure in the `/project-brain:reset` skill):

1. Read the wing name and diary agent from `.brain/CLAUDE.md` (`mempalace_wing`, `mempalace_diary_agent`), before any file deletion.
2. Resolve the real wings: call `mempalace_list_wings` and match, using MemPalace's normalize rule (lowercase, `-` and space → `_`), the recorded wing, the directory-derived wing (`normalize(<project-root dirname>)`), and the diary wing (`wing_<diary-agent>` and its normalized form). Show every candidate with its drawer count and ask the user which wings to delete. An empty `mempalace_list_rooms` result is never proof a wing is empty.
3. For each user-confirmed wing: `mempalace_list_rooms` → `mempalace_list_drawers` → `mempalace_delete_drawer`. Report how many were deleted per wing. The diary wing must be included — no other flow ever clears it.
4. Run `project-brain-reset <project-root> --dry-run` and show the output.
5. Only after explicit user confirmation, run `project-brain-reset <project-root> --confirm`.
6. After reset completes, offer to immediately run `project-brain-init <project-root> "<Project Name>"` to start fresh.

The reset script handles local files only (`.brain/`, `graphify-out/`, the injected `CLAUDE.md` block, and the snippet). It has no MemPalace access — MCP tools exist in the agent session, not in a subprocess. If the MCP tools are missing, stop and say so; never report drawers as deleted when they were not. Never run local deletion while a candidate wing is unresolved or unconfirmed, and preserve `.brain/CLAUDE.md` until the MemPalace side is settled.

Re-creation hazard: MemPalace's own session stop hook re-mines `MEMPAL_DIR` without `--wing` when that variable is set (verified in MemPalace 3.11.0 `hooks_cli.py`), so the directory-derived wing can reappear after a reset with mined project files inside. That wing belongs to MemPalace's project mining, not to the brain — do not treat its reappearance as a failed reset and do not delete it as part of a brain reset.

See the `/project-brain:reset` skill for the full procedure.

## Operation modes

### Initialize

Use when the project has no brain yet or the user asks to create/install/set up the brain. Initialize is autonomous: it continues through the lifecycle on its own and ends with a final report of what was done and what could not be done and why — never with a to-do list for the user. The agent may pause to ask the user only when a decision (e.g. which wing to delete, whether to run a destructive operation) or an access (missing tool, missing file permission) is genuinely missing.

Steps:

1. Run `project-brain-init <project-root> "<Project Name>"`.
2. Read the files it created (`.brain/CLAUDE.md`, `.brain/state/session-brief.md`, `.brain/wiki/index.md`).
3. **Read `references/mempalace-tools.md` now** — the full 47-tool reference, policy table, and call recipes. This must happen before the first MemPalace call of this mode; do not call `mempalace_status` or any other MemPalace tool before reading it.
4. Run `project-brain-doctor <project-root>` and read all four sub-scores, not just the total. The doctor flags any sub-score below the repair threshold (70) with `BELOW REPAIR THRESHOLD`. For each flagged sub-score, either run the matching repair from `references/brain-lifecycle.md` → Self-correction scan now (e.g. the diary entry in step 11 raises Memory sync), or state explicitly in the final report why it was not repaired. Never summarize a flagged sub-score as success.
5. Report the current availability of MemPalace MCP, graphify CLI, and Obsidian MCP. Do not give install instructions unless the user asks.
6. **Leftover-wing check (new brains only — skip on re-init of an existing brain):** after `mempalace_status`, call `mempalace_list_wings`. If any existing wing normalizes (MemPalace rule: lowercase, `-` and space → `_`) to this project's slug, its directory-derived wing, or the diary wing, and the brain was just created, tell the user these wings predate the new brain and offer cleanup via the `/project-brain:reset` flow. Do not delete anything unasked.
7. Ingest the project's own primary sources into the brain: read the project README, manifests (`package.json`, `pyproject.toml`, `Cargo.toml`, equivalents), and main entry points; store curated material or pointer files under `.brain/raw/` (per `references/evidence-lifecycle.md`).
8. Compile wiki pages from those primary sources under Contracts 7 and 8: read the actual files; no speculative language; update `.brain/wiki/architecture/System Overview.md`, add source summaries under `.brain/wiki/sources/` with `reliability:` frontmatter, update `.brain/wiki/index.md`, and record contradictions (e.g. a README claim that contradicts the code) in the source page and `open-questions.md`.
9. Mine `.brain/wiki` into the wiki wing with an explicit `--wing` from `mempalace_wing` in `.brain/CLAUDE.md` (Recipe 3 in mempalace-tools.md; dry run first). Never mine the project root into the wiki wing.
10. Run graphify only if the doctor says stale (step 9 of the post-wiki loop decides the command from the doctor's reason). Skip graphify if the CLI is unavailable; say so in the final report.
11. Write the diary entry (`mempalace_diary_write` with the agent from `mempalace_diary_agent`, diary format in `references/mempalace-workflow.md`).
12. Update `.brain/state/session-brief.md` (under 400 words), append the log entry, and run `project-brain-lint <project-root>`; clear error-level issues.
13. Final report: state what was done, what could not be done and why (e.g. graphify missing), and the doctor's sub-score status. It must not contain a to-do list for the user to execute.

MemPalace is already installed as a plugin. graphify is already installed as a CLI tool and skill. Do not reinstall either.

### Wake up / orient

Use at the start of a new session, after a model change, or when the user says to continue from memory.

Steps:

1. Read `.brain/CLAUDE.md`.
2. Read `.brain/state/session-brief.md`.
3. Read `.brain/wiki/index.md`.
4. Read `graphify-out/GRAPH_REPORT.md` if present.
5. Follow the recall rule in step 7 below.
6. Produce a short orientation: project purpose, current state, architecture map, decisions, risks, and next read targets.
7. Update the session brief if it is stale.

### Ingest

Use when the user adds a source, explains something important, links docs, uploads notes, asks to process a codebase, or gives new project context.

Steps:

1. Store the material in `.brain/raw/` or create a pointer file in `.brain/raw/refs/` according to `references/evidence-lifecycle.md`.
2. Extract claims, entities, relationships, decisions, uncertainties, and useful quotes.
3. **Read the actual source files referenced by the material** before writing any wiki claims. Apply Contract 7 (Primary Source Verification) and Contract 8 (No Speculative Language).
4. Create or update a source summary under `.brain/wiki/sources/` with a `reliability:` field in frontmatter set to `primary`, `secondary-verified`, or `secondary-unverified` (see Source reliability tagging below).
5. If the source is `secondary-unverified` or `secondary-verified` and discrepancies were found, add a `## Known Inaccuracies in This Source` section listing each error with: the incorrect claim, the correct value verified from primary source, and the primary source file and line number.
6. Update affected architecture, concept, entity, synthesis, and decision pages.
7. Update `.brain/wiki/index.md`.
8. Run the post-wiki checklist.

**Source reliability tagging**: Every source summary page (`wiki/sources/<name>.md`) must include a `reliability:` field in its frontmatter set to one of:

- `primary` — actual source code files (the canonical source of truth).
- `secondary-verified` — AI/human analysis whose claims have been checked against primary sources.
- `secondary-unverified` — AI/human analysis not yet cross-checked against primary sources.

For any `secondary-unverified` or `secondary-verified` source where discrepancies were found, add a `## Known Inaccuracies in This Source` section listing each error with: the incorrect claim, the correct value verified from primary source, and the primary source file and line number that proves the correction.

### Query

Use when answering questions from the brain.

Steps:

1. Identify the question type and route to the right layer first using `references/retrieval-strategy.md` or the routing table in `references/agent-playbook.md`.
2. Read only the relevant pages, graph reports, memories, logs, or raw sources needed for that question type.
3. Use graphify first for relationship, architecture, path, dependency, or code-navigation questions.
4. Follow the recall rule in step 7 below.
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
2. Follow the recall rule in step 7 above.
3. Write a concise diary entry with `mempalace_diary_write` after substantial work, decisions, or context changes. Follow the diary entry minimum standard in `references/mempalace-workflow.md`.
4. Convert stable memory into wiki pages, decisions, or `.brain/CLAUDE.md` preferences.
5. Never store secrets.

### Mirror to Obsidian (vault mirror)

Use when the user asks to view, browse, save, mirror, sync, or open brain content in Obsidian, or asks for the vault to reflect current brain state.

Steps:

1. Read `references/obsidian-workflow.md`.
2. Identify which wiki pages have changed since last mirror by checking `.brain/log/` for the last mirror timestamp.
3. Use Obsidian MCP write tools to mirror changed pages to `<vault>/project-brains/<project-name>/`.
4. Preserve all wikilinks — they work natively in Obsidian.
5. Do not mirror `.brain/raw/`, `.brain/log/`, `.brain/audit/`, or `.brain/state/` unless explicitly requested.
6. Log the mirror.

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
3. MemPalace has no verified store for global preferences. Keep durable preferences in `.brain/CLAUDE.md` or the project wiki, and create pointer files instead of duplicating them across projects.
4. Use graphify `merge-graphs` only when a cross-repo relationship map is needed.
5. Write a multi-project session brief that names each project and its next read targets.

### Self-correction scan

Use when `project-brain-doctor` shows health below the repair threshold (70/100) or any single sub-score below the repair threshold, when the session brief is more than 7 days old, or when the user asks whether the brain is healthy or up to date.

Steps:

1. Run `project-brain-doctor <project-root>` and read all four sub-scores, not just the total. The doctor marks every sub-score below 70 with `BELOW REPAIR THRESHOLD`.
2. For each sub-score below 70, run the matching repair from `references/brain-lifecycle.md` → Self-correction scan. Never summarize a flagged sub-score as success; if a repair is impossible, say which score, why, and what is needed.
3. Run `project-brain-lint <project-root>` and clear all error-level issues.
4. Log the scan result.
5. Update session brief.

## Non-negotiable post-wiki loop

Every time wiki pages change, perform this loop unless impossible:

1. Update index.
2. Add cross-links and backlinks.
3. Extract decisions.
4. **Resolve open questions**: For each question in `open-questions.md`, make a genuine attempt to answer it from the files already read. If the answer exists in any file you have access to, document it in the relevant wiki page and remove the question from open-questions.md. Only leave a question open if: (a) the answer requires reading a file not yet ingested, OR (b) the answer genuinely does not exist anywhere in the codebase. For case (a), name the specific file that needs to be read next. Never leave a question open if the answer is visible in a file you have already read.
5. **Run graphify only if the doctor says stale.** Run `project-brain-doctor <project-root>` and check the graphify freshness line. If it reports stale, choose the command based on the doctor's reason:
   - Reason starts with `"graphify-out/GRAPH_REPORT.md missing"` OR `"graph built at"` → `/graphify .` (full build, API cost)
   - Reason starts with `"uncommitted changes to source files:"` → check what changed. If the reason says more paths follow (marker contains "more paths omitted"), run `git status` first to see the full list. Then decide: code-only changes use `graphify update .` (AST-only, no API cost); docs/images/comments changes use `/graphify .`
   - Any other stale reason → `/graphify .`
   Skip graphify for wiki-only changes.
6. Consolidate MemPalace memory (diary entry) if session context changed.
7. Record contradictions/open questions.
8. Update session brief.
9. Append log entry.
10. Run lint for large changes.

The wiki is not the finish line; it is the compiled layer that must be wired back into the rest of the brain.

## Known issues documentation standard

When documenting security, validation, or correctness issues in wiki pages or open-questions.md, be precise about the severity and nature of the gap. Distinguish between three categories:

- **Absent** — the feature does not exist at all. Example: "No authentication on the /render-video endpoint."
- **Insufficient** — the feature exists but has exploitable gaps. Quote the specific gap. Example: "Duration validated as positive integer but no upper bound — allows arbitrarily long render requests (see `backend/renderVideo.js` line 42)."
- **Misconfigured** — the feature exists but is set incorrectly. Example: "CORS allows all origins despite being meant for a single-domain deployment (see `backend/server.js` line 15)."

Never write "no input validation" when validation exists but is insufficient. The distinction matters because "absent" tells a future agent to build from scratch, while "insufficient" tells them to extend what is already there.

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
