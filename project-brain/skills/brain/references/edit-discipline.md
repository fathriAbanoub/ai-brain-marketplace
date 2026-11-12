# Edit Discipline (Read before Edit; recover from failed edits)

Failed edits and duplicated lines come from building `old_string` from memory
— a summary or an earlier read of the page. The rules below are cheap; the
failures they prevent cost whole turns.

## Rules

1. **Read the page immediately before every Edit.** The `old_string` must
   come from that read, not from memory, a summary, or a compaction note.
2. **Re-Read after compaction** before the first Edit of the post-compaction
   session — the summary is not the file.
3. **Re-Read after ANY failed Edit.** A failed edit may have partially
   applied or shifted line content; retrying from the old mental copy fails
   again or duplicates lines.
4. **Prefer Write for whole-page rewrites.** Rewriting a wiki page with one
   Write beats five fragile Edits.
5. **Never batch dependent edits to the same file in one parallel turn.**
   Parallel tool calls do not see each other's results; the second edit's
   `old_string` is already stale. Sequence dependent edits across turns.
6. **Retry once, then switch to Write.** If the same Edit fails twice, stop
   patching: Read the page and Write the full corrected content.
7. **State only actions you actually emitted.** Never report an edit, a
   snapshot, or a lint run that did not happen; the linter and
   `project-brain-wiki log` make such claims checkable, and a false "done" is
   the expensive failure.

## Recovery path for a bad page edit

1. Read the page (current, post-failure state).
2. Fix the damage with one Edit (or Write the full page).
3. Run `project-brain-lint <project-root>` — the exit code, not your feeling,
   decides whether the page is fixed.
