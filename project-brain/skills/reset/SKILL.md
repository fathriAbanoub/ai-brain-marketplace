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

If the file doesn't exist or the key isn't there, derive the wing name using the **same rule as `sanitize_wing_name` in `scaffold_brain.py`**: lowercase, replace runs of characters outside `[a-z0-9._-]` with a single hyphen, collapse repeated hyphens, strip leading/trailing `-._`.

Example: `ambient-studio_brain-test` → `ambient-studio_brain-test` (underscore preserved)

If the directory name yields nothing, try the wing names `mempalace_list_wings` returns that contain a distinctive substring of the project directory name. Report exactly which wing name you used.

---

## Step 2 — Delete MemPalace drawers (YOU DO THIS, NOT THE SCRIPT)

Call these MCP tools in sequence. Do not skip this step.

1. `mempalace_list_rooms` → `{ "wing": "<wing-name>" }`
2. For each room returned: `mempalace_list_drawers` → `{ "wing": "<wing-name>", "room": "<room-name>" }`
3. For each drawer returned: `mempalace_delete_drawer` → `{ "drawer_id": "<id>" }`

Report total drawers deleted before moving on.

If `mempalace_list_rooms` returns empty or the wing doesn't exist, note that and continue.

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

The script deletes `.brain/`, `graphify-out/`, strips the `# Project Brain` block from root `CLAUDE.md`, and removes `CLAUDE.project-brain.snippet.md`.

---

## Step 4 — Report

Tell the user:
- How many MemPalace drawers were deleted (or that the wing was already empty)
- Whether `.brain/` was removed
- Whether `graphify-out/` was removed
- Whether the CLAUDE.md block was stripped

Then say: run `/project-brain:brain` to initialize a fresh brain.
