# Wiki Schema

The wiki is the durable, human-readable synthesis layer under `.brain/wiki/`.

## Primary source verification

> **PRIMARY SOURCE VERIFICATION RULE**: Before documenting any claim about a file's status, purpose, imports, or behavior — you MUST read that file directly. Secondary sources (GEMINI.md, critic reports, README files, any AI-generated analysis) are opinions, not evidence. If a secondary source makes a claim about a specific file (e.g. "this file is unused", "this function does X"), you must verify it by reading the actual file. If the secondary source contradicts the primary source code, document the contradiction explicitly in the source summary under a `## Known Inaccuracies in This Source` section. Never copy a claim from a secondary source into the wiki architecture pages without primary verification.

**Orphaned file check**: Before marking any file as "orphaned", "unused", or "not imported": search the entire codebase for import statements, require() calls, script tags, and dynamic references to that file. Only label a file orphaned after this search returns zero results.

## Writing standards

### No speculative language in architecture pages

Words like "likely", "probably", "appears to", "seems to", and "may" are banned from wiki architecture pages unless explicitly marked as a hypothesis under an open question. If you do not know how two components interact, do not guess — write "Integration method not yet verified. See [[open-questions#integration-question]]" and add the question to open-questions.md. If you do know, state it definitively and cite the file and line number.

### Issue documentation precision

When documenting security, validation, or correctness issues, distinguish between:

- **Absent** — the feature does not exist at all.
- **Insufficient** — the feature exists but has exploitable gaps. Quote the specific gap.
- **Misconfigured** — the feature exists but is set incorrectly.

Never write "no input validation" when validation exists but is insufficient. Example: "Duration validated as positive integer but no upper bound — allows arbitrarily long render requests (see `backend/renderVideo.js` line 42)."

## Required files

```text
.brain/
├── CLAUDE.md
├── wiki/index.md
├── wiki/open-questions.md
├── state/session-brief.md
└── log/YYYYMMDD.md
```

## Page frontmatter

Every wiki page must start with frontmatter using these required fields:

```yaml
---
title: <Page Title>
type: concept | architecture | decision | entity | source | overview
created: YYYY-MM-DD
updated: YYYY-MM-DD
status: draft | active | stale | superseded
sources: []
tags: []
---
```

**Standardized fields**: All page types (concept, architecture, decision, entity, source, overview) must use the same required frontmatter fields: `title:`, `type:`, `created:`, `updated:`, `status:`, `sources:`, `tags:`. Do not use `name:` instead of `title:`, or add non-standard fields like `author:` or `score:`.

## Concept page template

```markdown
---
title: <Concept>
type: concept
created: YYYY-MM-DD
updated: YYYY-MM-DD
status: active
sources: [raw/path.md]
tags: []
---

# <Concept>

One-sentence definition.

## What it is

## Why it matters to this project

## How it connects

- [[Related Page]] — relationship.

## Evidence

- `raw/path.md` — what it supports.

## Open questions
```

## Architecture page template

```markdown
---
title: <Subsystem or Flow>
type: architecture
created: YYYY-MM-DD
updated: YYYY-MM-DD
status: active
sources: []
tags: [architecture]
---

# <Subsystem or Flow>

## Purpose

## Components

## Flow

```mermaid
flowchart LR
    A --> B
```

## Key files

- `src/path/file.ts` — role.

## Decisions and tradeoffs

- [[decisions/Decision Name]]

## Failure modes

## Open questions
```

## Decision page template

```markdown
---
title: <Decision>
type: decision
created: YYYY-MM-DD
updated: YYYY-MM-DD
status: proposed | accepted | superseded | rejected
sources: []
tags: [decision]
---

# <Decision>

## Decision

## Context

## Options considered

## Why this option

## Consequences

## Revisit when
```

## Source summary page template

Source summaries use the same required frontmatter fields as all other page types, plus the `reliability:` field.

```markdown
---
title: <Source Name>
type: source
created: YYYY-MM-DD
updated: YYYY-MM-DD
status: active
sources: [path/to/source]
tags: [source]
reliability: primary | secondary-verified | secondary-unverified
---

# <Source Name>

## Summary

## Key claims

## Known Inaccuracies in This Source

*(Only present for secondary-verified or secondary-unverified sources where discrepancies were found. Remove this section if no inaccuracies were found.)*

| Incorrect claim | Correct value | Primary source | Line |
|-----------------|---------------|----------------|------|
| e.g. "Port 8080" | Port 3000 | `backend/server.js` | 5 |

## Related

- [[architecture/System Overview]]
```

### Source reliability tagging

Every source summary page must include a `reliability:` field in frontmatter set to one of:

- **`primary`** — actual source code files. These are the canonical source of truth.
- **`secondary-verified`** — AI/human analysis whose claims have been checked against primary sources. Discrepancies found are documented in `## Known Inaccuracies in This Source`.
- **`secondary-unverified`** — AI/human analysis not yet cross-checked against primary sources. Treat all claims as unconfirmed until verified.

For any `secondary-unverified` or `secondary-verified` source where discrepancies were found, add a `## Known Inaccuracies in This Source` section listing each error with: the incorrect claim, the correct value verified from primary source, and the primary source file and line number that proves the correction.

## Index rules

`wiki/index.md` must list every wiki page exactly once. Organize by category:

```markdown
# Project Brain Index

## Architecture
- [[architecture/System Overview]] — one-line summary

## Decisions
- [[decisions/Use Local Memory]] — one-line summary

## Concepts
- [[concepts/LLM Wiki]] — one-line summary

## Entities
- [[entities/MemPalace]] — one-line summary

## Sources
- [[sources/initial-setup]] — one-line summary
```

## Splitting rule

Split pages that exceed roughly 1200 words. Create a folder with an `index.md` and focused subpages.
