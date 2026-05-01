# Wiki Schema

The wiki is the durable, human-readable synthesis layer under `.brain/wiki/`.

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

Every wiki page should start with:

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
