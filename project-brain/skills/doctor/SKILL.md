---
description: Use when the user wants to check the health of a project brain, diagnose brain problems, see health scores, check if wiki pages are complete, verify MemPalace sync, check session-brief freshness, or run a brain health report.
---

# Project Brain Doctor

Run health checks on a project brain and report scores for completeness, freshness, coverage, and memory sync.

## Run the doctor

```bash
project-brain-doctor <project-root>
```

If not on PATH (exit 127):

```bash
# Option 1: OpenClaude plugin cache
PLUGIN_ROOT="$(ls -d ~/.openclaude/plugins/cache/ai-brain-marketplace/project-brain/*/ 2>/dev/null | sort -V | tail -1)"
"$PLUGIN_ROOT/bin/project-brain-doctor" <project-root>

# Option 2: marketplace repo directly
~/.openclaude/plugins/marketplaces/ai-brain-marketplace/project-brain/bin/project-brain-doctor <project-root>
```

## What it checks

| Check | What it means |
|-------|--------------|
| Completeness | Wiki pages have title, type, wikilinks, are indexed, have status (weighted partial credit) |
| Freshness | session-brief.md was updated recently |
| Coverage | Core wiki pages exist (architecture, decisions, open-questions) |
| Memory sync | MemPalace wing exists and has drawers for this project |
| Tool availability | graphify and mempalace are accessible |

## Scores

Scores are 0–100. A score of 100 means the brain is fully healthy in that dimension.

- **Completeness 0**: Wiki pages are missing required frontmatter or are not in index.md
- **Freshness 0**: session-brief.md is stale or missing
- **Coverage 0**: Core wiki pages are absent

## Acting on results

- Low completeness: open the wiki pages listed and add missing frontmatter (`title`, `type`, `status`) and at least one wikilink
- Low freshness: run `/project-brain:brain` and update `session-brief.md`
- Low coverage: create the missing core pages
- MemPalace missing: run `mempalace_status` to check if the MCP tool is available; if not, see `references/install-and-integration.md`
