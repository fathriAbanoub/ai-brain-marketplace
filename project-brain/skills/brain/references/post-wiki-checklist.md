# Post-Wiki Checklist

Use this every time the agent writes or edits wiki pages.

## Required

- [ ] Update `.brain/wiki/index.md`.
- [ ] Add wikilinks to related pages.
- [ ] Add or update decision records when choices were made.
- [ ] Resolve open questions: for each question in `open-questions.md`, make a genuine attempt to answer it from the files already read. If the answer exists in any file you have access to, document it in the relevant wiki page and remove the question from open-questions.md. Only leave a question open if: (a) the answer requires reading a file not yet ingested, OR (b) the answer genuinely does not exist anywhere in the codebase. For case (a), name the specific file that needs to be read next. Never leave a question open if the answer is visible in a file you have already read.
- [ ] Add uncertainties to `.brain/wiki/open-questions.md` (only genuine gaps that cannot be answered from available evidence).
- [ ] **Run graphify only if the doctor says stale.** Run `project-brain-doctor <project-root>` and check the graphify freshness line. If it reports stale, choose the command based on the doctor's reason:
  - Reason starts with `"graphify-out/GRAPH_REPORT.md missing"` OR `"graph built at"` → `/graphify .` (full build, API cost)
  - Reason starts with `"uncommitted changes to source files:"` → check what changed. If the reason says more paths follow (marker contains "more paths omitted"), run `git status` first to see the full list. Then decide: code-only changes use `graphify update .` (AST-only, no API cost); docs/images/comments changes use `/graphify .`
  - Any other stale reason → `/graphify .`
  Wiki edits alone do NOT change the repo — skip graphify for wiki-only changes.
- [ ] Update `.brain/state/session-brief.md` if project understanding changed.
- [ ] Append a log entry in `.brain/log/YYYYMMDD.md`.

## Conditional

- [ ] Read `graphify-out/GRAPH_REPORT.md` and promote stable findings into the wiki.
- [ ] Consolidate MemPalace memory: write a diary entry if the session created durable context. Follow the diary entry minimum standard in `references/mempalace-workflow.md`.
- [ ] Search MemPalace before summarizing prior decisions or preferences. For claims about wiki knowledge (decisions, architecture, project facts), use `mempalace_search` with the wiki wing from `.brain/CLAUDE.md`; for claims about what happened in earlier sessions (continuity, what was done last time, open threads), use `mempalace_diary_read` with agent brain-<project-slug>; the wiki search does not read the diary and the diary read does not search wiki pages, so use the one that fits the claim, or both.
- [ ] Run `project-brain-lint <project-root>` after large edits.
- [ ] Create audit notes for uncertain claims that need later review.

## Definition of done

The work is done only when the next model can answer:

1. What changed?
2. Why did it change?
3. Which files/pages contain the evidence?
4. Which relationships matter?
5. What should be done next?
