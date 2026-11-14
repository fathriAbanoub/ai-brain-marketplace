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
"$PLUGIN_ROOT/bin/project-brain-doctor" <project-root>
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

| Check | What it means |
|-------|--------------|
| Completeness | Wiki pages have title, type, wikilinks, are indexed, have status, and active pages carry a source or citation (draft pages exempt) |
| Freshness | session-brief.md was updated recently |
| Coverage | From `.brain/inventory.json`: units covered = cited by a substantive non-draft page with a lint-valid citation; reported as weighted % with core-uncovered count |
| Memory sync | MemPalace wing exists and has drawers for this project (estimated from logs) |
| Tool availability | graphify and mempalace are accessible |
| Secrets | `.brain/` is scanned for private keys and credential patterns (lint `brain_secret`) |

Recorded-wing check: when the MemPalace tools are available, also confirm the recorded wiki wing (`mempalace_wing` in `.brain/CLAUDE.md`) exists and has drawers (`mempalace_get_taxonomy`, or `mempalace_list_rooms` for that exact wing). If it is not found, report "recorded wing not found; mining may have failed" and recommend re-running the mining step from the brain skill (dry run first). The doctor never deletes anything — a missing or empty wing is a report item, not a cleanup target, and the doctor script itself is unchanged by this check.

## Strict gate

Run after PLUGIN_ROOT is resolved (the resolution flow above), by full path:

```bash
"$PLUGIN_ROOT/bin/project-brain-doctor" <project-root> --strict
```

The hard gate: exits 0 only when every gate passes —

- **lint_errors**: `project-brain-lint` reports zero errors (covers citation
  drift, stale citations, forbidden all-clears, secrets, index duplicates)
- **coverage**: the inventory is complete (all core units covered AND
  weighted coverage ≥ 0.90)

Every strict run writes one receipt to `.brain/audit/runs/<UTC-timestamp>/run.json`
(commit, plugin version, unit counts, gate results, status). "Done" means
`--strict` exited 0 and the receipt says `passed-for-scope` — nothing else.

Exit codes: 0 all gates passed · 1 a gate failed or could not run (including
missing inventory — run `project-brain-inventory <root> inventory` first).

## Scores

Scores are 0–100 (informational, printed without --strict).

- **Completeness 0**: Wiki pages are missing required frontmatter or are not in index.md
- **Freshness 0**: session-brief.md is stale or missing
- **Coverage 0**: no inventory yet, or nothing covered — never treat absent data as 100

## Acting on results

- Low completeness: open the wiki pages listed and add missing frontmatter (`title`, `type`, `status`) and at least one wikilink
- Low freshness: run `/project-brain:brain` and update `session-brief.md`
- Low coverage: run `"$PLUGIN_ROOT/bin/project-brain-inventory" <project-root> inventory` (PLUGIN_ROOT resolved as above) and cover the UNCOVERED core/important units (doctor prints the work list)
- MemPalace missing: run `mempalace_status` to check if the MCP tool is available; if not, see `references/install-and-integration.md`
