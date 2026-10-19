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
# Option 1: OpenClaude plugin cache
PLUGIN_ROOT="$(ls -d ~/.openclaude/plugins/cache/ai-brain-marketplace/project-brain/*/ 2>/dev/null | sort -V | tail -1)"
"$PLUGIN_ROOT/bin/project-brain-audit-open" <project-root>

# Option 2: marketplace repo directly
~/.openclaude/plugins/marketplaces/ai-brain-marketplace/project-brain/bin/project-brain-audit-open <project-root>
```

## What it shows

- Open audit items in `.brain/audit/` (unresolved contradictions, flagged claims, open questions)
- Items already resolved in `.brain/audit/resolved/`

## Audit lifecycle

1. During brain work, flag contradictions or unverified claims by writing to `.brain/audit/`
2. Each audit file should include: the claim, the source, the conflict, and what verification is needed
3. After verifying or resolving, move the file to `.brain/audit/resolved/`
4. Run `project-brain-audit-open` periodically to review what's still open

## Format for audit files

```markdown
---
status: open
claim: "<what was claimed>"
source: "<where the claim came from>"
conflict: "<what contradicts it>"
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
