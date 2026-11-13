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
# A stale CLAUDE_PLUGIN_ROOT (moved/foreign copy) must not skip discovery:
# validate it against bin/ and clear it when invalid; a valid one is kept.
if [ -n "$PLUGIN_ROOT" ] && [ ! -d "$PLUGIN_ROOT/bin" ]; then
  PLUGIN_ROOT=""
fi
# If still empty: the harness prints "Base directory for this skill: <path>"
# directly above this skill's text (verified in --plugin-dir sessions, where
# the marketplace paths below do not exist). Do NOT count dirname levels by
# hand — a wrong depth guess cascades into a filesystem hunt that can end on
# a foreign copy of the plugin. Set BASE_DIR to that path and take the first
# candidate that actually contains the plugin's bin/. The candidate loop runs
# only when PLUGIN_ROOT is still empty — never overwrite a resolved root.
if [ -z "$PLUGIN_ROOT" ]; then
  BASE_DIR='<path-from-that-line>'
  for _c in "$BASE_DIR" "$(dirname "$BASE_DIR")" "$(dirname "$(dirname "$BASE_DIR")")"; do
    if [ -d "$_c/bin" ]; then PLUGIN_ROOT="$_c"; break; fi
  done
fi
# Verify before use: ls "$PLUGIN_ROOT/bin" must list the project-brain-* wrappers.
: "${PLUGIN_ROOT:=$(ls -d ~/.openclaude/plugins/cache/ai-brain-marketplace/project-brain/*/ 2>/dev/null | sort -V | tail -1)}"
: "${PLUGIN_ROOT:=$HOME/.openclaude/plugins/marketplaces/ai-brain-marketplace/project-brain}"
"$PLUGIN_ROOT/bin/project-brain-audit-open" <project-root>
```

Never type a bare `project-brain-*` command. The wrappers are not on PATH in
this harness; every bare attempt wastes a turn, and roughly three
consecutive failed Bash calls abort the whole session. Every
`project-brain-*` command in this skill means `"$PLUGIN_ROOT/bin/<command>"`,
with PLUGIN_ROOT read from `.brain/state/plugin-root.txt` (written by init)
or resolved by the fallback above.

If PLUGIN_ROOT still cannot be resolved after all of the above, STOP and
report exactly which paths you tried. NEVER write or modify `.brain/` files
by hand as a substitute for the scripts — a brain the scripts did not build
is unverifiable and counts as failure, not as a completed step.

After any shell resolves PLUGIN_ROOT successfully, persist it — the variable
dies with the shell, the file survives into later shells and sessions:

```bash
printf '%s' "$PLUGIN_ROOT" > .brain/state/plugin-root.txt
```

In every LATER shell, try the persisted value first (with a staleness check —
a moved plugin must fall back to re-resolution, never be used blindly):

```bash
PLUGIN_ROOT="$(cat .brain/state/plugin-root.txt 2>/dev/null || true)"
[ -n "$PLUGIN_ROOT" ] && [ -d "$PLUGIN_ROOT/bin" ] || PLUGIN_ROOT=""
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
