# Post-Wiki Checklist

Use this every time the agent writes or edits wiki pages.

## Required

- [ ] Update `.brain/wiki/index.md`.
- [ ] Add wikilinks to related pages.
- [ ] Add or update decision records when choices were made.
- [ ] Resolve open questions: for each question in `open-questions.md`, make a genuine attempt to answer it from the files already read. If the answer exists in any file you have access to, document it in the relevant wiki page and remove the question from open-questions.md. Only leave a question open if: (a) the answer requires reading a file not yet ingested, OR (b) the answer genuinely does not exist anywhere in the codebase. For case (a), name the specific file that needs to be read next. Never leave a question open if the answer is visible in a file you have already read.
- [ ] Add uncertainties to `.brain/wiki/open-questions.md` (only genuine gaps that cannot be answered from available evidence).
- [ ] **Run `/graphify .` from project root.** If graphify is not installed, run `uv tool install graphify` (note: single y) and retry. If it fails after install, log the error in the session log and add a `graphify-not-available` flag to the session brief. Do NOT skip this step silently — the health score and relationship accuracy depend on it.
- [ ] Update `.brain/state/session-brief.md` if project understanding changed.
- [ ] Append a log entry in `.brain/log/YYYYMMDD.md`.

## Conditional

- [ ] Read `graphify-out/GRAPH_REPORT.md` and promote stable findings into the wiki.
- [ ] Write a MemPalace diary entry if the session created durable context. Follow the diary entry minimum standard in `references/mempalace-workflow.md`.
- [ ] Search MemPalace before summarizing prior decisions or preferences.
- [ ] Run `project-brain-lint <project-root>` after large edits.
- [ ] Create audit notes for uncertain claims that need later review.

## Definition of done

The work is done only when the next model can answer:

1. What changed?
2. Why did it change?
3. Which files/pages contain the evidence?
4. Which relationships matter?
5. What should be done next?
