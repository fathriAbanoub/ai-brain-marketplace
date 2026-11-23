# Project Brain Lifecycle

This is the canonical operating loop. The LLM Wiki is only one phase. A project brain is complete only when the wiki, MemPalace, graphify, logs, and handoff state are aligned.

Every session-brief rewrite preserves any `BLOCKED-WING:` line until reset removes the brain (SKILL.md Work loop step 5).

## Layer order

Use this order for serious work:

1. **Orient** from `.brain/CLAUDE.md`, `.brain/state/session-brief.md`, `.brain/wiki/index.md`, graphify report, and MemPalace.
2. **Ingest evidence** into `.brain/raw/` or pointers in `.brain/raw/refs/`.
3. **Compile wiki knowledge** into small, linked markdown pages.
4. **Map relationships** with graphify and summarize useful graph findings into the wiki.
5. **Consolidate memory** in MemPalace for verbatim/session/user-preference recall.
6. **Audit and lint** the brain for broken links, stale claims, contradictions, and missing pages.
7. **Handoff** by updating `.brain/state/session-brief.md`, the operation log, and next actions.

## What to do after the LLM Wiki phase

After creating or updating wiki pages, do not stop. Run this post-wiki checklist:

1. **Index**
   - Regenerate `.brain/wiki/index.md` with `project-brain-lint <project-root> --reindex` so every page is listed exactly once (never by hand).
   - Add one-line summaries that help future agents decide what to read.

2. **Cross-link**
   - Add wikilinks from new pages to related architecture, concept, entity, source, and decision pages.
   - Add backlinks or related sections where important pages should know about the new page.

3. **Decision extraction**
   - If the source or conversation contains a durable choice, create or update `.brain/wiki/decisions/<Decision>.md`.
   - Include context, options considered, consequences, status, and when to revisit.

4. **Graph refresh**
   - **Run graphify only if the doctor says stale.** Run `project-brain-doctor <project-root>` and check the graphify freshness line. If it reports stale, choose the command based on the doctor's reason:
     - Reason starts with `"graphify-out/GRAPH_REPORT.md missing"` OR `"graph built at"` → `/graphify .` (full build, API cost)
     - Reason starts with `"uncommitted changes to source files:"` → check what changed. If the reason says more paths follow (marker contains "more paths omitted"), run `git status` first to see the full list. Then decide: code-only changes use `graphify update .` (AST-only, no API cost); docs/images/comments changes use `/graphify .`
     - Any other stale reason → `/graphify .`
   - Wiki edits alone do NOT change the repo — skip graphify for wiki-only changes.
   - After ANY change to graph.json (full build or incremental `graphify update .`), reconnect the graphify MCP server before querying it (it reads the graph at startup). The CLI is the fallback: set `GRAPHIFY_BACKEND=none` on BOTH `extract` and `cluster-only` when no API access (see `references/graphify-workflow.md`).
   - Read `graphify-out/GRAPH_REPORT.md`.
   - Promote stable graph findings into `.brain/wiki/architecture/` or `.brain/wiki/concepts/`.
   - Mark graph-only inferences as leads until confirmed from files or sources.

5. **Memory consolidation**
   - If MemPalace tools are available, write a concise diary entry with what changed, why, decisions, user preferences, and unresolved next steps.
   - If MemPalace recalls something important, compile it into wiki form instead of leaving it only in memory.

6. **Open questions and contradictions**
   - Add contradictions to the relevant wiki page and `.brain/wiki/open-questions.md`.
   - Do not resolve contradictions by guessing. Identify the evidence needed.

7. **Handoff state**
   - Update `.brain/state/session-brief.md` with current state, changed files/pages, recent decisions, risks, and exact next files to read.
   - Keep the brief short enough for a future model to read every session.

8. **Log**
   - Append an entry to `.brain/log/YYYYMMDD.md` with the operation type, what changed, and follow-up actions.

9. **Lint**
   - Run `project-brain-lint <project-root>` when possible.
   - Fix hard issues before claiming the brain is healthy.

## Complete operation definitions

### Initialize

Goal: create the durable brain skeleton and continue autonomously through the strict gate and final report. No user to-do list. Pause only for a genuinely missing decision or access; leftover-wing findings never pause Initialize.

Actions (the executable first-run order is in `../SKILL.md` → Initialize):

1. Run `project-brain-init <project-root> "<Project Name>"`; verify the new wing's uniqueness in step 6.
2. Read `.brain/CLAUDE.md`, `.brain/state/session-brief.md`, and `.brain/wiki/index.md`; immediately write an IN-PROGRESS session brief with the current state and next step.
3. Read `references/mempalace-tools.md` before the first MemPalace call. Load deferred schemas in ONE ToolSearch call (`select:<full name 1>,<full name 2>,…`, `max_results` at least the number of names): `mempalace_status`, `mempalace_list_wings`, `mempalace_list_tunnels`, `mempalace_list_hallways`, `mempalace_get_taxonomy`, `mempalace_diary_write`, `mempalace_list_rooms`, `mempalace_mine`. Verify the returned `<functions>` block, then call `mempalace_status`.
4. Run `project-brain-doctor <project-root>` and read all four sub-scores. Repair every flagged score in the Work loop per Self-correction scan (the diary and log repair Memory sync). Skip only a repair requiring access you lack; name that access in the report.
5. Report availability of MemPalace MCP, the graphify skill/CLI, and Obsidian MCP; no install instructions unless asked.
6. Leftover-wing check (new brains only — skip on re-init): read `mempalace_wing` and `mempalace_diary_agent` from `.brain/CLAUDE.md`; call `mempalace_status`, then `mempalace_list_wings`, `mempalace_list_tunnels`, `mempalace_list_hallways` (`limit: 100`; advance `offset` by 100 until a page returns fewer than 100 records; check every record). Retry any failed call once; if it still fails (name the call and page) or the recorded wiki wing exists or has tunnel/hallway records, do NOT mine: prepend `BLOCKED-WING: <exact wing name> — collision or unverified check; do not mine; resolve via /project-brain:reset` to `.brain/state/session-brief.md`, preserving its content; memory **not done**. Report each match's exact name, drawer count and tunnel/hallway records; memory **not done** — init cannot rename it. Offer `/project-brain:reset` for wiki/brain-diary matches or orphan candidates. Directory-derived wings: informational only (MemPalace re-creates them), no cleanup offer. Never delete unasked; report and continue without waiting for an answer.
7. Ingest primary sources (README, manifests, entry points) into `.brain/raw/` or pointer files.
8. Before the first wiki write, read `references/wiki-schema.md`. Compile primary sources under Contracts 7 and 8; update System Overview and source summaries, regenerate the index with `project-brain-lint <project-root> --reindex`, and record contradictions in source pages and `open-questions.md`.
9. If the brief has `BLOCKED-WING:` naming the recorded wing, skip mining, step 10's drawer check and step 13's re-mine; report memory **not done**. Otherwise mine `.brain/wiki` with explicit `--wing` from `mempalace_wing` (Recipe 3 in mempalace-tools.md; dry run first), never the project root.
10. Verify mining with `mempalace_get_taxonomy` or `mempalace_list_rooms` for the recorded wing: it must exist with drawers. No drawers → repair now with the mining recipe, dry run first; if blocked, report the failing call, error and missing access, then continue other layers.
11. Update `.brain/state/session-brief.md` (under 400 words), run `project-brain-lint <project-root>`, and clear error-level issues.
12. Write `mempalace_diary_write` with the recorded `mempalace_diary_agent`, using the plain format in SKILL.md Initialize (full example: `references/mempalace-workflow.md`). Set `Log:` to `.brain/log/<YYYYMMDD>.md`; after success, append `## [HH:MM] diary | <title>` and `- MemPalace diary written (agent <diary agent>)` to that path, preserving existing content. Never log a failed write as written.
13. Run the `## Work loop` section from SKILL.md — inventory and git-digest first on a fresh brain. Repair flagged sub-scores and gates; re-mine wiki changes (Recipe 3 in `references/mempalace-tools.md`; dry run first). Append a second diary and log entry only if the Work loop changed findings or contradictions. Run `project-brain-doctor <project-root> --strict` until it exits 0 or the Work loop's repair cap is spent; report all four sub-scores from the last strict run's output.
14. Final report: "complete" only if the strict gate exited 0, no sub-score remains flagged, every re-mine of step 13's wiki changes succeeded, and the recorded wing is not blocked and the recorded wing has drawers (verified in step 10). Otherwise **INCOMPLETE**: list failing gates, sub-scores, mines/re-mines with their failing commands, blocked or empty wings and missing access under **not done**. No wiki changes in step 13 → no re-mine. A flagged sub-score is never "expected". No next-session to-do list for runnable work.

Done when:

- `.brain/` exists with `wiki/index.md`, `wiki/open-questions.md`, and `state/session-brief.md`.
- Primary sources are ingested and compiled, the wiki is mined into the recorded wing, the plain diary is written, and the log and brief are updated.
- The final strict gate exits 0, all sub-scores are at or above the repair threshold, every re-mine of step 13's wiki changes succeeded, the recorded wing is not blocked and it has drawers verified in step 10; otherwise Initialize is INCOMPLETE, never complete with an explanation instead of repair; list failed re-mines and their failing commands under **not done**. No wiki changes in step 13 → no re-mine.
- The user or future model can see the brain protocol from project files.

### Wake up / orient

Goal: recover context after a new session or model switch.

Actions:

1. Read `.brain/CLAUDE.md`.
2. Read `.brain/state/session-brief.md`.
3. Read `.brain/wiki/index.md`.
4. Read `graphify-out/GRAPH_REPORT.md` if present.
5. Follow the recall rule in the plugin's SKILL.md step 7.
6. Produce a concise orientation with project purpose, components, current workstream, known risks, and next files/pages.
7. Update the session brief if the current state differs from the stored state.

Done when:

- The agent can state the project purpose, current workstream, key decisions, and next read targets without relying on chat history alone.

### Ingest

Goal: turn new evidence into durable project knowledge.

Actions:

1. Store the source in `.brain/raw/` or create a pointer file in `.brain/raw/refs/`.
2. Extract key claims, decisions, entities, relationships, code references, and uncertainties.
3. Create a source summary under `.brain/wiki/sources/`.
4. Update concept, architecture, entity, and decision pages.
5. Regenerate `.brain/wiki/index.md` with `project-brain-lint <project-root> --reindex`.
6. Run the post-wiki checklist.

Done when:

- The source is findable, summarized, cross-linked, logged, and represented in memory/graph/handoff where appropriate.

### Query

Goal: answer from the brain and preserve useful discoveries.

Actions:

1. Read the wiki index first.
2. Search/read relevant wiki pages.
3. Use graphify for relationship, architecture, path, or code-navigation questions.
4. Follow the recall rule in the plugin's SKILL.md step 7.
5. Check raw sources for high-stakes or contested claims.
6. Answer with citations to wiki pages, raw paths, graph report, or memory notes as appropriate.
7. If the answer creates durable value, save it to `.brain/outputs/queries/` or promote it into the wiki.
8. Update session brief and log if the answer changes project understanding.

Done when:

- The answer is grounded and any durable synthesis is stored outside chat.

### Build or refresh graph

Goal: make relationships visible and queryable.

Actions:

1. Ensure `.graphifyignore` excludes noisy folders like `node_modules/`, `dist/`, vendor folders, caches, build outputs, and secrets.
2. **Run graphify only if the repo changed.** Run `project-brain-doctor <project-root>` and check the "freshness" gate. If it reports stale, choose the command based on the doctor's reason:
   - Reason starts with `"graphify-out/GRAPH_REPORT.md missing"` OR `"graph built at"` → `/graphify .` (full build, API cost)
   - Reason starts with `"uncommitted changes to source files:"` → check what changed. If the reason says more paths follow (marker contains "more paths omitted"), run `git status` first to see the full list. Then decide: code-only changes use `graphify update .` (AST-only, no API cost); docs/images/comments changes use `/graphify .`
   - Any other stale reason → `/graphify .`
   After graphify runs, the doctor reports fresh until a source file changes again. Reconnect the graphify MCP server after ANY change to graph.json (full build or incremental `graphify update .`; it reads the graph at startup); the CLI is the fallback, with `GRAPHIFY_BACKEND=none` on BOTH `extract` and `cluster-only` when no API access.
3. Read `graphify-out/GRAPH_REPORT.md`.
4. Identify god nodes, communities, surprising connections, and suggested questions.
5. Update `.brain/wiki/architecture/System Overview.md` and related pages.
6. Add graph-derived leads to open questions until verified.
7. Log the graph refresh.

Done when:

- Graph outputs exist and the wiki captures the important structural findings.

### Consolidate memory

Goal: preserve session-specific context without bloating the wiki.

Before any MemPalace call, read `references/mempalace-tools.md` for the complete 47-tool reference, policy table, and call recipes. Follow those recipes exactly — preflight check before writes, search before claims.

Actions:

1. Call `mempalace_status` (preflight). If `vector_disabled` is true, skip writes and tell the user to run `mempalace repair rebuild-index`.
2. If `.brain/CLAUDE.md` is missing or does not define a non-empty `mempalace_wing`, skip the MemPalace search and diary read, tell the user the brain is not initialized or configured and to run project-brain-init (or fix the file), and never infer a wing or search without one. For claims about wiki knowledge (decisions, architecture, project facts), use `mempalace_search` with the wiki wing from `.brain/CLAUDE.md`; for claims about what happened in earlier sessions (continuity, what was done last time, open threads), use `mempalace_diary_read` with the agent from `mempalace_diary_agent` in `.brain/CLAUDE.md` (for an older brain without that field, from the agent named in the diary sentence of that file; if neither exists, skip the diary and tell the user) — see the recipe in mempalace-tools.md, "Read Diary at Wake-up". The wiki search does not read the diary and the diary read does not search wiki pages, so use the one that fits the claim, or both.
3. Store diary entries after meaningful changes (follow the format in `../SKILL.md` → Initialize step 12).
4. Convert stable facts from memory into wiki pages or decisions.
5. Do not store secrets or full raw dumps.

Done when:

- Important session context is findable later and durable project knowledge has been compiled into the wiki.

### Audit / lint

Goal: keep the brain trustworthy.

Actions:

1. Run `project-brain-lint <project-root>`.
2. Process `.brain/audit/*.md` feedback from highest to lowest severity.
3. Find dead wikilinks, orphan pages, stale claims, contradictions, missing decisions, unindexed pages, and vague pages.
4. Use raw sources, graphify, and MemPalace to resolve issues.
5. Move resolved audit files to `.brain/audit/resolved/` with a resolution note.
6. Log the audit.

Done when:

- Known hard issues are fixed or explicitly recorded as open questions.

### Self-correction scan

Goal: detect brain drift before it causes bad answers.

Use when: the user asks "is the brain healthy?", "are things up to date?", or when `project-brain-doctor` shows health below the repair threshold (70/100) or any single sub-score below it (a score of exactly 70 passes). Also run autonomously at the start of any session longer than a few turns if the session brief is more than 7 days old.

Actions:

1. Run `project-brain-doctor <project-root>` and read all four sub-scores, not just the total. The doctor marks every sub-score below 70 with `BELOW REPAIR THRESHOLD` (exactly 70 passes).
2. For each sub-score below 70, trigger the matching repair action (exactly 70 needs no repair):

   **Completeness below 70:**
   - Identify pages missing title, type, status, sources, wikilinks, or index entries.
   - Fix or flag each missing field. Do not invent sources — mark `sources: []` and add an open question.

   **Freshness below 70:**
   - If session brief is stale: update it from current chat context immediately.
   - If graphify is stale: propose a rebuild to the user (do not rebuild silently — it may take time).
   - Identify wiki pages with `updated:` older than 30 days and cross-check against recent log entries to see if they changed but frontmatter was not updated.

   **Coverage below 70:**
   - Run `project-brain-inventory <project-root> inventory` and use the
     uncovered core/important units it reports as the work list — coverage is
     computed from `.brain/inventory.json`, not from raw files lacking a
     summary page.
   - For each uncovered unit, write or update a non-draft wiki page that cites
     the unit with a lint-valid `{{src ...}}` citation and carries enough body
     text to pass the inventory substance check (>= 120 non-whitespace
     characters). A one-line stub does not count as coverage.

   **Memory consolidation below 70 (estimated):**
   - Write a MemPalace diary entry covering current project state, recent decisions, and active workstream.
   - Verify known preferences from wiki or `.brain/CLAUDE.md` are still current.

3. After repairs, re-run `project-brain-lint <project-root>` and check that error count is zero.
4. Log the scan: what was found, what was repaired, what was deferred.
5. Update session brief with the scan result.

Done when:

- Doctor sub-scores are at or above 70, or all remaining issues are explicitly logged as open questions with a resolution plan.

### Handoff

Goal: make the next model productive in minutes.

Actions:

1. Update `.brain/state/session-brief.md`.
2. Include current state, active workstream, recent decisions, changed files/pages, risks, and exact next read targets.
3. Add next actions with checkboxes.
4. Write a MemPalace diary entry if available.
5. Append a log entry.

Done when:

- A future model can resume without reading this chat.

## Trust model

Use this evidence hierarchy:

1. Raw sources and repository files.
2. Decision pages with source links.
3. Wiki synthesis.
4. Graphify extracted relationships.
5. Graphify inferred relationships.
6. MemPalace recollections.
7. Current chat claims.

If layers disagree, do not hide the conflict. State the conflict, inspect the higher-trust evidence, then update the stale layer.
