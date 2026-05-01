# Cross-Brain Workflow

Use this workflow when the user works across multiple projects, each with its own `.brain/` directory.

## Linking brains

Do not copy whole pages from one project brain into another. Create pointer files that identify the other project and the exact page, decision, source, or graph artifact.

Recommended pointer file location:

```text
.brain/wiki/external/<other-project>-<topic>.md
```

Pointer file format:

```markdown
---
title: <Pointer Title>
type: external-pointer
status: active
project: <other project name>
target_path: <path to page or artifact>
reason: <why this matters here>
---

# <Pointer Title>

This project depends on or relates to `<other project>`.

## Why this matters

<short explanation>

## Read target

- `<target_path>`

## Local implications

- <what changes in this project>
```

Use pointers for shared concepts, related decisions, reusable architecture, and cross-project dependencies.

## Global preferences

Preferences that apply across all projects belong in MemPalace at a global scope, not duplicated in every project wiki.

Examples:

- preferred response style,
- preferred tooling,
- recurring safety boundaries,
- naming conventions the user wants everywhere,
- review cadence.

Before writing a global preference, confirm it is not project-specific. Use `mempalace_preferences_get` before relying on a preference and `mempalace_preferences_set` after the user states a durable preference.

## Cross-repo graph maps

Use graphify `merge-graphs` when:

- two repos call each other,
- a feature spans multiple projects,
- decisions in one project constrain another,
- the user asks for a cross-project dependency map,
- onboarding requires understanding an ecosystem rather than one repo.

The merged graph is an analysis artifact. Summarize stable findings into each affected brain's wiki and create pointer files instead of duplicating full pages.

## Multi-project session brief

When a session spans two or more projects, the session brief should include:

```markdown
## Multi-project context

Projects involved:

1. <Project A> — <root path> — <current role in the task>
2. <Project B> — <root path> — <current role in the task>

## Cross-project links

- <Project A page> ↔ <Project B page>

## Next read targets

### <Project A>
- <path>

### <Project B>
- <path>
```

Keep each project's local brief short. Put deeper cross-project analysis in a wiki synthesis page or pointer page.

