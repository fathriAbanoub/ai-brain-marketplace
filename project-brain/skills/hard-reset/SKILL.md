---
description: Use only when the normal MCP-based MemPalace reset cannot complete safely and the user explicitly authorizes a direct database-level deletion. This is the "mempalace hard reset" command: a separate destructive operation with fail-closed database discovery, mandatory dry run, plan-hash confirmation, backup, transactional deletion, and post-deletion verification. Never a routine substitute for mempalace_delete_drawers.
---

# Project Brain Hard Reset (database-level)

**This is an exceptional, separate operation. It is NOT part of the normal reset and is never launched automatically.**

Use it only when ALL of these hold:

1. The normal `/project-brain:reset` MCP flow failed in a way that cannot be fixed by retrying or by resolving wing ownership (persistent bulk-tool failure, drawers surviving verified deletion, or a graph too large for per-record cleanup).
2. The user explicitly authorizes direct database mutation after seeing the failed normal-route evidence.
3. The palace is a local SQLite database on this device. A remote backend, or a local cache that is not the authoritative palace, is a refusal — never claim a remote palace was cleaned by touching a local file.

If the actual problem is an unresolved ownership question (which wing belongs to the project), answer that question through the normal reset's Step 2 instead. Do not recommend or run a hard reset for it.

---

## What it does

`scripts/hard_reset.py` (wrapper: `project-brain-hard-reset`):

1. **Discovers the database, fail-closed**: explicit `--db-path`, else `MEMPAL_DIR` (a file directly, or a directory containing exactly one database file). When neither resolves the location, it refuses and tells you to find the real path — via the installed MemPalace CLI's own output (e.g. `mempalace status`, if that command exists in this installation), the MemPalace package's storage configuration, or the user — and pass `--db-path`. It never guesses a home-directory path and never treats a cache directory as the palace.
2. **Verifies the backend**: reads the file header; only local SQLite is supported. Anything else refuses.
3. **Introspects the actual schema**: classifies tables by real column evidence (wing-tagged columns `wing`, `wing_name`, `source_wing`, `target_wing`, `wing_a`, `wing_b`; drawer-child tables via `drawer_id` columns). A layout without a wing-tagged table is refused — no invented table names. A default ChromaDB palace (embeddings/embedding_metadata tables) is also refused: its records can only be removed safely through the Chroma API, and deleting its SQLite rows directly would leave vectors in the HNSW segment files — so **the default ChromaDB backend is unsupported by the hard reset**; use the normal MCP-based reset for it.
4. **Plans and prints a dry run by default**: backend, resolved database path, exact target wings, affected row counts per table (drawers, chunks/children, tunnels, hallways), revision sidecar lines, the backup location, unrelated wings that will be preserved, and a **plan hash**.
5. **Requires bound confirmation**: `--confirm --plan-hash <hash>` where the hash must match the exact displayed plan. A materially changed plan invalidates the old confirmation — re-run the dry run and confirm the new hash.
6. **Backs up** the database (plus WAL/SHM and revision sidecars) to a timestamped backup directory next to it.
7. **Deletes inside one transaction** (`BEGIN IMMEDIATE` … `COMMIT` with rollback on any error): children of the target wings' drawers first, then wing-tagged rows, then a wing registry row when one exists. JSONL revision sidecars are rewritten via temp file + atomic replace (never in-place text replacement).
8. **Verifies independently**: `PRAGMA integrity_check`, zero remaining rows for the target wings, unrelated wings' counts unchanged, backup present. Verification failure means the command reports failure — never success — and preserves the backup and recovery path.
9. **Tells you to reconnect**: call `mempalace_reconnect` (MCP) or restart the MemPalace server so the in-memory index matches the database, then verify the final state through the supported interface (`mempalace_list_wings`, `mempalace_get_taxonomy`).

It refuses to operate when WAL/SHM files suggest MemPalace is running (pass `--allow-live` only after stopping the server is impossible and the user accepts the risk — this is not recommended).

## Command sequence

```bash
# 1. Dry run (default; nothing is modified)
project-brain-hard-reset --wing "<exact-wing-name>" --db-path <palace.db>

# 2. Show the user the printed plan. After explicit authorization:
project-brain-hard-reset --wing "<exact-wing-name>" --db-path <palace.db> \
  --confirm --plan-hash <hash-from-step-1>
```

If the wrapper is not on PATH (exit 127), resolve the plugin root in the SAME shell invocation as the command — a variable from an earlier tool call does not survive:

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
"$PLUGIN_ROOT/bin/project-brain-hard-reset" --wing "<exact-wing-name>" --db-path <palace.db>
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

Multiple confirmed wings: repeat `--wing` once per exact wing name. Ambiguous targets (distinct names that normalize identically) are refused — the user must supply the exact names.

## Agent rules

- Resolve the exact wing names and ownership through the normal reset's Step 2 FIRST. The hard reset does not guess ownership.
- Always run the dry run and show the plan before asking for authorization. Never `--confirm` without a fresh, matching plan hash.
- Never delete an entire palace to remove one project's wing; never accept a plan that deletes every record.
- If discovery, backend verification, or schema classification refuses, stop and report the refusal reason. Do not bypass it with ad-hoc SQL.
- After a successful run, instruct the user (or the next session) to reconnect and re-verify through MCP before any further brain work.
- Never test or run this against the user's real palace during development; use disposable databases only.
