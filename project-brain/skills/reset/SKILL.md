---
description: Use when the user wants to reset, wipe, delete, or start over a project brain. Removes the MemPalace wing, .brain/ directory, graphify-out/, the Project Brain block from root CLAUDE.md, and CLAUDE.project-brain.snippet.md. Never deletes project source files.
---

# Project Brain Reset

**YOU ARE THE AGENT. YOU HAVE MCP TOOLS. YOU MUST USE THEM DIRECTLY.**

The script handles local files only. MemPalace deletion is YOUR job using MCP tools. Do not pass MemPalace to the script. Do not use `--confirm` without completing Step 2 first.

---

## Step 1 — Read the wing name

```bash
grep "mempalace_wing" <project-root>/.brain/CLAUDE.md
```

If the file is missing or `mempalace_wing` is absent, **do not infer the wing from the directory name**. Instead:

1. Call `mempalace_list_wings` and show the user the full list.
2. Ask the user to identify which wing belongs to this project.
3. Do not proceed until the user confirms the wing name.

---

## Step 2 — Delete MemPalace drawers (YOU DO THIS, NOT THE SCRIPT)

### 2a — Preview and confirm

Before deleting anything, enumerate all drawers:

1. `mempalace_list_rooms` → `{ "wing": "<wing-name>" }`
2. For each room: `mempalace_list_drawers` → `{ "wing": "<wing-name>", "room": "<room-name>", "limit": 100, "offset": 0 }`
   - If the result returns exactly `limit` drawers, call again with `offset` incremented by `limit` and collect more. Repeat until a page returns fewer than `limit` results.
3. Collect every drawer ID across all pages and all rooms.

Show the user:
- Wing name
- Number of rooms
- Total drawer count
- A short sample of drawer IDs (up to 5)

Ask: **"Delete all N drawers from wing `<wing-name>`? (yes/no)"**

Do not call `mempalace_delete_drawer` until the user says yes. If the user says no, skip all drawer deletion and go to Step 3, but note that the wing will not be cleared.

### 2b — Delete

For each collected drawer ID, call:
- `mempalace_delete_drawer` → `{ "drawer_id": "<id>" }`

Track failures. If any deletion fails:
1. Report the failed drawer IDs.
2. **Do not proceed to Step 3 (local file deletion).**
3. Preserve `.brain/CLAUDE.md` — it contains the wing name needed for a retry.
4. Ask the user: "N drawer(s) failed to delete. Retry, skip failed drawers and continue, or abort?"
   - Retry: attempt the failed IDs again, then re-evaluate.
   - Skip and continue: proceed to Step 3, but note the wing is partially populated.
   - Abort: stop here. Nothing local has been deleted yet.

If `mempalace_list_rooms` returns empty or the wing does not exist, note that and continue to Step 3 without calling any delete tools.

Report total drawers deleted before moving on.

---

## Step 3 — Delete local files

```bash
project-brain-reset <project-root> --confirm
```

If not on PATH (exit 127), use the fallback:

```bash
PLUGIN_ROOT="$(ls -d ~/.openclaude/plugins/cache/ai-brain-marketplace/project-brain/*/ 2>/dev/null | sort -V | tail -1)"
[ -z "$PLUGIN_ROOT" ] && PLUGIN_ROOT="$HOME/.openclaude/plugins/marketplaces/ai-brain-marketplace/project-brain"
"$PLUGIN_ROOT/bin/project-brain-reset" <project-root> --confirm
```

The script deletes `.brain/`, `graphify-out/`, strips the injected block from root `CLAUDE.md`, and removes `CLAUDE.project-brain.snippet.md`.

---

## Step 4 — Report

Tell the user:
- How many MemPalace drawers were deleted (or that the wing was already empty, or that deletion was skipped)
- Whether `.brain/` was removed
- Whether `graphify-out/` was removed
- Whether the CLAUDE.md block was stripped

Then say: run `/project-brain:brain` to initialize a fresh brain.
