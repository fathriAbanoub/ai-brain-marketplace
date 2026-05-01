# Post-Wiki Checklist

Use this every time the agent writes or edits wiki pages.

## Required

- [ ] Update `.brain/wiki/index.md`.
- [ ] Add wikilinks to related pages.
- [ ] Add or update decision records when choices were made.
- [ ] Add uncertainties to `.brain/wiki/open-questions.md`.
- [ ] Update `.brain/state/session-brief.md` if project understanding changed.
- [ ] Append a log entry in `.brain/log/YYYYMMDD.md`.

## Conditional

- [ ] Run graphify if project structure, architecture, source corpus, or code changed.
- [ ] Read `graphify-out/GRAPH_REPORT.md` and promote stable findings into the wiki.
- [ ] Write a MemPalace diary entry if the session created durable context.
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
