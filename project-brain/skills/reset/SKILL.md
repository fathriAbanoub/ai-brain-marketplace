---
description: Use when the user wants to reset, wipe, delete, or start over a project brain. Removes the MemPalace wing and diary wing drawers, .brain/ directory, graphify-out/, the Project Brain block from root CLAUDE.md, and CLAUDE.project-brain.snippet.md. Never deletes project source files.
---

# Project Brain Reset

**YOU ARE THE AGENT. YOU HAVE MCP TOOLS. YOU MUST USE THEM DIRECTLY.**

The script handles local files only. MemPalace deletion is YOUR job using MCP tools. Do not pass MemPalace to the script. Do not use `--confirm` without completing Step 2 (wing resolution + drawer deletion) and Step 4 (dry run + explicit user confirmation) first.

Before any MemPalace call in this skill, read `skills/brain/references/mempalace-tools.md` (tool schemas, policies, recipes).

---

## Step 1 — Read the wing name

```bash
grep "mempalace_wing" <project-root>/.brain/CLAUDE.md
```

Also read `mempalace_diary_agent` from the same file (fall back to the agent named in the diary sentence of that file, exactly as the wake-up recall rule does).

If the file is missing or `mempalace_wing` is absent, **do not infer the wing from the directory name alone**. Still build the candidate list in Step 2 (it covers the directory-derived wing), and additionally ask the user to identify the wing from the full `mempalace_list_wings` output.

**Preserve `.brain/CLAUDE.md` until the MemPalace side is fully settled.** It is the only record of the wing and diary agent names. Never delete `.brain/` before Step 2 is complete.

---

## Step 2 — Resolve the real wings (an empty result is never proof of an empty wing)

`mempalace_list_rooms` returning `{}` or an error for a wing name does **not** mean the project's data is gone or the wing is empty. MemPalace normalizes wing names — it lowercases and maps `-` and space to `_` (its `normalize_wing_name` rule) — so the recorded name and the actual wing can differ. Verify before concluding anything:

1. Build the candidate list:
   - `c1` = the `mempalace_wing` value from `.brain/CLAUDE.md` (verbatim).
   - `c2` = the directory-derived wing: MemPalace mines a project root **without** `--wing` into `normalize(<project-root dirname>)`, where `normalize` = lowercase, `-` and space → `_`, edge `_` stripped. Compute it for this project's root directory name.
   - `c3` = the diary wing for the diary agent: `wing_<diary_agent>` verbatim, plus its normalized form `normalize(wing_<diary_agent>)`.
2. Call `mempalace_list_wings` (or `mempalace_get_taxonomy`, which also returns drawer counts).
3. Match every candidate against the actual wing list using the same normalize rule (compare `normalize(candidate)` to `normalize(actual_wing)`), never raw string equality alone.
4. For each matched candidate, get the drawer count via `mempalace_get_taxonomy`, or `mempalace_list_rooms` + `mempalace_list_drawers`.

Show the user a table: every candidate (c1, c2, c3), the actual wing(s) it matched, and the drawer count.

- If **no candidate matches anything**, show the full wing list and ask the user which wings belong to this project. Do not proceed until the user answers.
- Never skip wing deletion and go straight to local deletion on the basis that "the wing looked empty". An empty/missing result must be cross-checked against `mempalace_list_wings` first, and the user must confirm the outcome either way.

---

## Step 3 — Delete MemPalace drawers (YOU DO THIS, NOT THE SCRIPT)

This step applies to **every wing the user confirmed in Step 2** — the wiki wing (c1/c2 match) **and the diary wing (c3)**. The diary wing holds session-continuity entries and is otherwise never cleared by any brain flow; a reset that skips it orphans the diary.

### 3a — Preview and confirm

For each confirmed wing:

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

Do not call `mempalace_delete_drawer` until the user says yes. If the user says no for a wing, skip that wing's deletion and record that the wing was kept.

### 3b — Delete

For each collected drawer ID, call:
- `mempalace_delete_drawer` → `{ "drawer_id": "<id>" }`

Track failures. If any deletion fails:
1. Report the failed drawer IDs.
2. **Do not proceed to Step 4 (local file deletion).**
3. Preserve `.brain/CLAUDE.md` — it contains the wing name needed for a retry.
4. Ask the user: "N drawer(s) failed to delete. Retry, skip failed drawers and continue, or abort?"
   - Retry: attempt the failed IDs again, then re-evaluate.
   - Skip and continue: proceed to Step 4, but note the wing is partially populated.
   - Abort: stop here. Nothing local has been deleted yet.

Report total drawers deleted per wing before moving on.

---

## Step 4 — Delete local files (dry run first, then explicit confirmation)

Run the dry run and show the output:

```bash
project-brain-reset <project-root> --dry-run
```

Review it with the user, then ask for explicit confirmation ("Delete the local brain files shown above? (yes/no)"). Only after the user says yes, run:

```bash
project-brain-reset <project-root> --confirm
```

If not on PATH (exit 127), resolve the plugin root with statements that cannot short-circuit, then run the wrapper directly:

```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}"
: "${PLUGIN_ROOT:=$(ls -d ~/.openclaude/plugins/cache/ai-brain-marketplace/project-brain/*/ 2>/dev/null | sort -V | tail -1)}"
: "${PLUGIN_ROOT:=$HOME/.openclaude/plugins/marketplaces/ai-brain-marketplace/project-brain}"
"$PLUGIN_ROOT/bin/project-brain-reset" <project-root> --dry-run
```

The script deletes `.brain/`, `graphify-out/`, strips the injected block from root `CLAUDE.md`, and removes `CLAUDE.project-brain.snippet.md`. Never pass `--confirm` before the user has seen the dry-run output and answered yes.

---

## Step 5 — Report

Tell the user:
- How many MemPalace drawers were deleted, per wing — or that deletion was skipped/kept for a wing, or (only after the Step 2 cross-check) that no matching wing existed
- Whether the diary wing was cleared
- Whether `.brain/` was removed
- Whether `graphify-out/` was removed
- Whether the CLAUDE.md block was stripped

Then say: run `/project-brain:brain` to initialize a fresh brain.

---

## Step 6 — Know the re-creation hazard (read before declaring the reset complete)

MemPalace's own session stop hook re-mines the `MEMPAL_DIR` directory **without `--wing`** when that variable is set (verified in MemPalace 3.11.0 `hooks_cli.py`: `hook_stop` → `_maybe_auto_ingest` → `mine <dir> --mode projects`, wing falls back to `normalize(dirname)`). Consequence: after a clean reset, a wing named after the project's normalized directory name can **reappear automatically** at the next session stop, containing mined project files — not brain data.

The plugin cannot prevent this safely: `MEMPAL_DIR` belongs to MemPalace's configuration, the hook runs in MemPalace's own process, and suppressing another product's hooks from here is out of scope. So this is documented behavior instead:

- The wiki wing is always `wiki_<slug>` (or a legacy `wiki-<slug>` recorded in `.brain/CLAUDE.md`) and never collides with the directory-derived wing.
- After a reset, if the user reports a wing reappearing with mined project source in it, that is the stop hook, not a failed reset.
- `project-brain-doctor` prints this same note and warns when `MEMPAL_DIR` points at the project root.
- Do not "clean up" the re-created wing as part of a brain reset — it belongs to MemPalace's project mining, and deleting it is the user's separate decision.
