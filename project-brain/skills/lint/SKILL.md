---
description: Use when the user wants to validate wiki structure, find broken wikilinks, check frontmatter errors, validate inline citations and their staleness, record citation verification stamps, or get a JSON report of brain issues.
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
# If still empty: the harness prints "Base directory for this skill: <path>"
# directly above this skill's text (verified in --plugin-dir sessions, where
# the marketplace paths below do not exist). Do NOT count dirname levels by
# hand — a wrong depth guess cascades into a filesystem hunt that can end on
# a foreign copy of the plugin. Set BASE_DIR to that path and take the first
# candidate that actually contains the plugin's bin/. The candidate loop
# runs only when PLUGIN_ROOT is still empty — never overwrite a resolved root.
if [ -z "$PLUGIN_ROOT" ]; then
  BASE_DIR='<path-from-that-line>'
  for _c in "$BASE_DIR" "$(dirname "$BASE_DIR")" "$(dirname "$(dirname "$BASE_DIR")")"; do
    if [ -d "$_c/bin" ]; then PLUGIN_ROOT="$_c"; break; fi
  done
fi
# Verify before use: ls "$PLUGIN_ROOT/bin" must list the project-brain-* wrappers.
: "${PLUGIN_ROOT:=$(ls -d ~/.openclaude/plugins/cache/ai-brain-marketplace/project-brain/*/ 2>/dev/null | sort -V | tail -1)}"
: "${PLUGIN_ROOT:=$HOME/.openclaude/plugins/marketplaces/ai-brain-marketplace/project-brain}"
"$PLUGIN_ROOT/bin/project-brain-lint" <project-root>
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

## What it checks

| Check | Severity |
|-------|----------|
| Missing required frontmatter fields | warning |
| Broken wikilinks (target page doesn't exist) | error |
| Page missing from index.md | warning |
| Page listed more than once / dangling index entry | error |
| Task checklist in session brief (tasks belong in tasks/next-actions.md only) | error |
| Nested graphify-out/graphify-out/ (stale cache copy) | error |
| Citation drift: `{{src path:lines "anchor"}}` file missing, range outside file, anchor not in window | error |
| Bare `file.ext:123` references without an anchor | warning |
| Stale citations (cited file changed or vanished since --verify) | error |
| Decision page rationale_source missing / invalid / dangling doc or commit | warning / error / error |
| All-clear claims ("no contradictions" ...) without a verify stamp + crossrefs receipt | error |
| Volatile counts ("49 tests") without [unverified] or command+date | warning |
| Short wiki pages | warning |

## Verifying citations

After writing or changing citations, record verification stamps:

```bash
project-brain-lint <project-root> --verify
```

This re-checks all citations and writes `.brain/verification.json` (SHA-256 of
each cited file per clean page, plus the current commit). Only this flag
writes that file — never edit it by hand. When a cited file later changes, the
page becomes `stale_citation` until you re-check it and run `--verify` again.

## Exit codes

- 0: no errors (warnings may exist)
- 1: one or more errors found
- 2: usage error (or --reindex without a .brain directory)
- 3: .brain/verification.json is corrupt — inspect it, do not ignore

## Acting on results

Fix errors before merging or sharing the brain. Warnings are informational — address them when convenient.

Common fixes:
- Missing frontmatter: add `title`, `type`, and `status` to the page's YAML block
- Broken wikilink: either create the target page or update the link to point to an existing page
- Not in index: run `project-brain-lint <project-root> --reindex` (index.md is script-generated)
- Citation drift: open the cited file, fix the path/range/anchor to what is actually there
- Stale citation: re-read the changed source, update the page, then run `--verify`
- All-clear error: run the cross-reference check first, then `--verify`, or delete the claim
