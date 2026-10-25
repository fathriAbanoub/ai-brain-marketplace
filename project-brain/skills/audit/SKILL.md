---
description: Use when the user wants to review audit artifacts, check what open questions or contradictions were flagged in the brain, review audit findings, or see unresolved issues the brain has tracked.
---

# Project Brain Audit Review

Review open audit artifacts — flagged contradictions, unresolved questions, and source conflicts stored in `.brain/audit/`.

## Run the audit reviewer

```bash
project-brain-audit-open <project-root>
```

If not on PATH (exit 127):

```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}"
: "${PLUGIN_ROOT:=$(ls -d ~/.openclaude/plugins/cache/ai-brain-marketplace/project-brain/*/ 2>/dev/null | sort -V | tail -1)}"
: "${PLUGIN_ROOT:=$HOME/.openclaude/plugins/marketplaces/ai-brain-marketplace/project-brain}"
"$PLUGIN_ROOT/bin/project-brain-audit-open" <project-root>
```

## What it shows

- Open audit items in `.brain/audit/` (unresolved contradictions, flagged claims, open questions)
- Resolved items are in `.brain/audit/resolved/` — pass `--resolved` to see them, `--all` for both

## Audit lifecycle

1. During brain work, flag contradictions or unverified claims by writing to `.brain/audit/`
2. Each audit file should include: the claim, the source, the conflict, and what verification is needed
3. After verifying or resolving, move the file to `.brain/audit/resolved/`
4. Run `project-brain-audit-open` periodically to review what's still open

## Format for audit files

```markdown
---
id: AUDIT-001
severity: error
target: wiki/architecture/System Overview.md
author: agent
created: 2026-10-19
status: open
claim: "The API gateway routes all requests"
source: ".brain/raw/notes/architecture-notes.md"
conflict: "graphify output shows direct service-to-service calls bypassing the gateway"
---

## Verification needed

<what needs to be checked to resolve this>
```

## Acting on results

For each open item:
1. Read the source file and verify the claim
2. If confirmed: update the relevant wiki page and move audit file to `resolved/`
3. If refuted: correct the wiki page, note the correction, move to `resolved/`
4. If still unclear: leave open, add a note about what was checked
