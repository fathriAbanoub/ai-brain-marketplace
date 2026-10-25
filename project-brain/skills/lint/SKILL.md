---
description: Use when the user wants to validate wiki structure, find broken wikilinks, check frontmatter errors, lint brain files, or get a JSON report of brain issues.
---

# Project Brain Lint

Validate the structure of a project brain's wiki — frontmatter, wikilinks, index consistency, and page schema.

## Run the linter

```bash
project-brain-lint <project-root>
```

For machine-readable output:

```bash
project-brain-lint <project-root> --json
```

If not on PATH (exit 127):

```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}"
: "${PLUGIN_ROOT:=$(ls -d ~/.openclaude/plugins/cache/ai-brain-marketplace/project-brain/*/ 2>/dev/null | sort -V | tail -1)}"
: "${PLUGIN_ROOT:=$HOME/.openclaude/plugins/marketplaces/ai-brain-marketplace/project-brain}"
"$PLUGIN_ROOT/bin/project-brain-lint" <project-root>
```

## What it checks

| Check | Severity |
|-------|----------|
| Missing required frontmatter fields | error |
| Broken wikilinks (target page doesn't exist) | error |
| Page not listed in index.md | warning |
| Duplicate page titles | error |
| Empty wiki pages | warning |

## Exit codes

- 0: no errors (warnings may exist)
- 1: one or more errors found

## Acting on results

Fix errors before merging or sharing the brain. Warnings are informational — address them when convenient.

Common fixes:
- Missing frontmatter: add `title`, `type`, and `status` to the page's YAML block
- Broken wikilink: either create the target page or update the link to point to an existing page
- Not in index: add an entry to `.brain/wiki/index.md`
