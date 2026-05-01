# Agent Playbook

This file tells the agent what kind of work to do at each stage. Use it when the user asks broad questions like "make the AI understand this project", "build the brain", "what next", or "continue from memory".

## Default behavior

Always think in five artifacts:

1. **Evidence**: `.brain/raw/` and project files.
2. **Synthesis**: `.brain/wiki/`.
3. **Memory**: MemPalace.
4. **Map**: graphify outputs.
5. **Handoff**: `.brain/state/session-brief.md`.

A good turn should usually update at least one artifact. A major turn should update several.

## Decision tree

### If `.brain/` does not exist

Run initialization. Do not pretend there is memory. Create the scaffold and explain the next setup steps.

### If `.brain/` exists but graphify is missing

Continue using the wiki and raw sources. Tell the user graph relationships are not available yet. Run `project-brain-doctor` and suggest installing graphify if architecture/navigation matters.

### If `.brain/` exists but MemPalace is missing

Continue using the wiki and logs. Tell the user verbatim previous-session recall is not available yet. Store durable facts in the wiki and session brief.

### If wiki exists but is shallow

Do not only answer the current question. Propose or create missing pages: system overview, core entities, active decisions, glossary/concepts, open questions, and source summaries.

### If graphify exists but wiki does not reflect it

Summarize graphify's important communities, god nodes, and surprising edges into wiki architecture pages. Mark unverified graph findings as leads.

### If MemPalace recalls relevant history but wiki lacks it

Convert the memory into a decision, concept, preference, or session-brief update. MemPalace is recall; the wiki is compiled understanding.

### If the user changes direction

Record the pivot as a decision or current-workstream update. Preserve the old path as superseded rather than deleting it.

## Retrieval routing

Do not always start with the wiki. The wiki is compiled synthesis — it is correct for concept questions but slow for code navigation (graphify is faster) and wrong for session-specific context (session-brief is faster). Match the tool to the question.

Before answering a question, identify its type and consult layers in the order shown.
Stop when you have a confident answer. If the primary layer is unavailable, move to the next.

| Question type | Layer order |
|---|---|
| Code navigation, architecture, "how does X connect to Y", dependency | graphify → wiki/architecture → raw/repo files |
| Past decision, "why did we choose X", options considered | MemPalace → wiki/decisions → wiki/sources → raw |
| Current project status, "where are we", "what's the state" | session-brief → wiki/index → MemPalace → log |
| Concept definition, "what is X in this project" | wiki/concepts → wiki/entities → wiki/sources → graphify |
| User preference, working style, "how do I like X" | MemPalace (preferences) → brain/CLAUDE.md → session-brief |
| Source verification, "does the evidence support X" | raw sources → wiki/sources → graphify extracted edges |
| Cross-project question, "how does project A relate to B" | cross-brain pointers → merged graphify graph → MemPalace global |
| General orientation (new session) | session-brief → wiki/index → graph report → MemPalace status |

When layers disagree, apply the evidence hierarchy from `brain-lifecycle.md`. Do not hide the disagreement — record it in `open-questions.md`.

## Exact work products

For a new software project, create or update:

- `.brain/wiki/architecture/System Overview.md`
- `.brain/wiki/architecture/<Core Flow>.md`
- `.brain/wiki/concepts/<Domain Concept>.md`
- `.brain/wiki/entities/<Major Tool or Service>.md`
- `.brain/wiki/decisions/<Decision>.md`
- `.brain/wiki/sources/<source-summary>.md`
- `.brain/wiki/open-questions.md`
- `.brain/state/session-brief.md`

For a research/personal knowledge project, create or update:

- `.brain/wiki/concepts/<Theme>.md`
- `.brain/wiki/entities/<Person, Book, Framework, Project>.md`
- `.brain/wiki/sources/<article-or-note>.md`
- `.brain/wiki/syntheses/<Question or Thesis>.md` if a synthesis deserves its own page
- `.brain/wiki/open-questions.md`
- `.brain/state/session-brief.md`

## Minimum useful brain

A project brain is not useful until it has:

1. A project purpose.
2. A system overview or topic overview.
3. At least one source summary or project scan.
4. An index that lists pages.
5. Open questions.
6. A current session brief.
7. A clear next-action list.

If any are missing, prioritize creating them.

## When to ask vs act

Ask the user when a choice changes the brain's scope, privacy, or source of truth.

Act without asking when:

- updating the index,
- adding wikilinks,
- logging work,
- moving resolved audit notes,
- writing a session brief,
- marking uncertainty,
- creating obvious missing support pages.

## Knowledge compression

Compression is the process of reducing noise in the brain without losing knowledge. Apply it when the wiki has more than 30 pages, after large ingestion sessions, or when the index becomes hard to scan.

### When to compress

Compress a wiki page when:

- two pages cover the same concept under different names (merge into one, redirect the other)
- a source summary page has no wikilinks pointing to it (candidate for archival)
- a concept page is shorter than 5 lines and has no evidence (merge into a related page or promote to a bullet in another page)
- an architecture page describes a component that no longer exists (mark superseded, keep for history)

### How to compress

1. Read the wiki index end to end, looking for duplicates, orphans, and stubs.
2. For each candidate, check whether other pages link to it before deleting or merging.
3. When merging: keep the richer page, add a redirect note in the thinner page, update all wikilinks pointing to the old page, update the index.
4. When archiving: move the page to `.brain/wiki/archive/`, update the index, add a log entry.
5. Never delete a page with a decision record or source link without verifying the decision/source is captured elsewhere.
6. After compression, run `project-brain-lint` to verify no broken wikilinks were introduced.

### Compression is not deletion

Compressed knowledge is still accessible. Archive > delete. Merge > archive. Only hard-delete pages that are pure scaffolding artifacts with no knowledge content.

## Privacy and safety

Never write credentials, private keys, tokens, passwords, or unreduced sensitive personal data into MemPalace, wiki pages, logs, or graph sources. Use pointer files or redacted summaries for sensitive material.
