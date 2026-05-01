# Project Brain Lifecycle

This is the canonical operating loop. The LLM Wiki is only one phase. A project brain is complete only when the wiki, MemPalace, graphify, logs, and handoff state are synchronized.

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
   - Update `.brain/wiki/index.md` so every page is listed exactly once.
   - Add one-line summaries that help future agents decide what to read.

2. **Cross-link**
   - Add wikilinks from new pages to related architecture, concept, entity, source, and decision pages.
   - Add backlinks or related sections where important pages should know about the new page.

3. **Decision extraction**
   - If the source or conversation contains a durable choice, create or update `.brain/wiki/decisions/<Decision>.md`.
   - Include context, options considered, consequences, status, and when to revisit.

4. **Graph synchronization**
   - If new code/docs/sources change project structure, run `/graphify .` or `graphify . --update` when available.
   - Read `graphify-out/GRAPH_REPORT.md`.
   - Promote stable graph findings into `.brain/wiki/architecture/` or `.brain/wiki/concepts/`.
   - Mark graph-only inferences as leads until confirmed from files or sources.

5. **Memory synchronization**
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

Goal: create the durable brain skeleton and orient the project to use it.

Actions:

1. Run `project-brain-init <project-root> "<Project Name>"`.
2. Read the created `.brain/CLAUDE.md` and `.brain/state/session-brief.md`.
3. Run `project-brain-doctor <project-root>`.
4. Tell the user which optional dependencies are missing: MemPalace and graphify.
5. Recommend merging `CLAUDE.project-brain.snippet.md` into root `CLAUDE.md`.
6. Ask for the first sources to ingest or scan the project if the user asked for autonomous setup.

Done when:

- `.brain/` exists.
- `wiki/index.md`, `wiki/open-questions.md`, and `state/session-brief.md` exist.
- The user or future model can see the brain protocol from project files.

### Wake up / orient

Goal: recover context after a new session or model switch.

Actions:

1. Read `.brain/CLAUDE.md`.
2. Read `.brain/state/session-brief.md`.
3. Read `.brain/wiki/index.md`.
4. Read `graphify-out/GRAPH_REPORT.md` if present.
5. Query MemPalace for project name, current task, recent decisions, and user preferences if available.
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
5. Update `.brain/wiki/index.md`.
6. Run the post-wiki checklist.

Done when:

- The source is findable, summarized, cross-linked, logged, and represented in memory/graph/handoff where appropriate.

### Query

Goal: answer from the brain and preserve useful discoveries.

Actions:

1. Read the wiki index first.
2. Search/read relevant wiki pages.
3. Use graphify for relationship, architecture, path, or code-navigation questions.
4. Search MemPalace for past conversations, preferences, and decision context.
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
2. Run `/graphify .` for first build or `graphify . --update` for refresh.
3. Read `graphify-out/GRAPH_REPORT.md`.
4. Identify god nodes, communities, surprising connections, and suggested questions.
5. Update `.brain/wiki/architecture/System Overview.md` and related pages.
6. Add graph-derived leads to open questions until verified.
7. Log the graph refresh.

Done when:

- Graph outputs exist and the wiki captures the important structural findings.

### Consolidate memory

Goal: preserve session-specific context without bloating the wiki.

Actions:

1. Search MemPalace before making claims about previous work.
2. Store diary entries after meaningful changes.
3. Store user preferences that should survive model switches.
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

Use when: the user asks "is the brain healthy?", "are things up to date?", or when `project-brain-doctor` shows health below 70/100. Also run autonomously at the start of any session longer than a few turns if the session brief is more than 7 days old.

Actions:

1. Run `project-brain-doctor <project-root>` and read all four scores.
2. For each score below 70, trigger the matching repair action:

   **Completeness below 70:**
   - Identify pages missing title, type, status, sources, wikilinks, or index entries.
   - Fix or flag each missing field. Do not invent sources — mark `sources: []` and add an open question.

   **Freshness below 70:**
   - If session brief is stale: update it from current chat context immediately.
   - If graphify is stale: propose a rebuild to the user (do not rebuild silently — it may take time).
   - Identify wiki pages with `updated:` older than 30 days and cross-check against recent log entries to see if they changed but frontmatter was not updated.

   **Coverage below 70:**
   - List raw source files that have no wiki/sources/ summary page.
   - Create stub source summary pages for the top unreferenced raw files. A stub with title, type, status, and a one-line summary is better than nothing.

   **Memory sync below 70 (estimated):**
   - Write a MemPalace diary entry covering current project state, recent decisions, and active workstream.
   - Call `mempalace_preferences_get` to verify known preferences are still current.

3. After repairs, re-run `project-brain-lint <project-root>` and check that error count is zero.
4. Log the scan: what was found, what was repaired, what was deferred.
5. Update session brief with the scan result.

Done when:

- Doctor scores are above 70 or all remaining issues are explicitly logged as open questions with a resolution plan.

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
