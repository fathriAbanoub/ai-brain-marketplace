---
description: Use when the user wants to reset, wipe, delete, or start over a project brain. Removes the MemPalace wing and diary wing drawers (via mempalace_delete_drawers in batches), cleans up associated tunnels and hallways, deletes .brain/, graphify-out/, the Project Brain block from root CLAUDE.md, and CLAUDE.project-brain.snippet.md. Never deletes project source files.
---

# Project Brain Reset

The local-file script cannot reach MemPalace: MCP tools exist in the agent session, not in a subprocess. So the MemPalace half of this reset — resolving wings, deleting drawers, cleaning tunnels and hallways — is done by you, with the MemPalace MCP tools in your own tool list. The script handles local files only. Do not use `--confirm` without completing Step 2 (wing resolution), Step 3 (drawer enumeration + deletion + verification), and Step 5 (dry run + explicit user confirmation) first.

Before any MemPalace call in this skill, read `skills/brain/references/mempalace-tools.md` (tool schemas, policies, recipes). The algorithm below mirrors `scripts/mempalace_reset.py`, the canonical tested implementation — follow it exactly; you never need to read the script to run this flow.

**Drawer deletion is ALWAYS `mempalace_delete_drawers` (bulk, batches of at most 500 IDs) — never `mempalace_delete_drawer`, not even for a single remaining drawer.** The single-drawer tool is prohibited in this workflow: do not use it, do not fall back to it when the bulk call fails, and do not "optimize" small wings into single-drawer calls. If the bulk tool itself is unavailable or fails, stop and report — do not substitute another deletion mechanism; see Step 7 for the hard-reset referral.

---

## Step 0 — Confirm MemPalace tool access

Do this before any other step, so a missing memory layer is discovered before anything is decided or deleted.

- **Verify, don't assume.** The MemPalace tools must be reachable in this session: present in the tool list OR named in the deferred-tools list (a deferred tool exists — load its schema first, see below; the plugin's `references/deferred-tools.md` has the full policy). Check both lists, because a tool you never verified cannot be trusted later in a destructive flow. Their full names carry a harness-specific prefix (commonly `mcp__plugin_mempalace_mempalace__` for the plugin install; the prefix varies by install), so match on the `__mempalace_<tool>` suffix. Names like `mempalace_status` in this skill are shorthand for those tools.
- **One access route: the tools themselves.** The MemPalace tools are tools, not skills — calling the Skill tool with `mempalace` or `mempalace:*` loads MemPalace's install guide and runs nothing, so it can never substitute for a tool call (this skill is already loaded; do not load it again through the Skill tool). Use only the MCP tools in the tool list: do not start `mempalace-mcp` yourself, write MCP, JSON-RPC or HTTP clients, run Python against the palace's database, or use the `mempalace` CLI in place of tool calls — a second server process on the live palace can conflict with the running one, bypasses the per-call checks the user relies on, and burns context. One read-only `mempalace status` CLI call is acceptable purely to diagnose why the tools are absent — report the result and stop.
- **Deferred schemas — load them before first use.** If your harness defers tool schemas (a tool-search tool is in your tool list), load the schemas of the tools that take integer or array arguments before their first call: `mempalace_list_drawers`, `mempalace_delete_drawers`, `mempalace_list_hallways`. The tool-search tool is a tool, not a shell command: call it directly with BOTH parameters — `query: "select:<full name 1>,<full name 2>,<full name 3>"` (comma-separated exact full names, ONE call for all three) and `max_results` at least the number of names. For the plugin install a full name looks like `mcp__plugin_mempalace_mempalace__mempalace_list_drawers`, so the query is `select:mcp__plugin_mempalace_mempalace__mempalace_list_drawers,mcp__plugin_mempalace_mempalace__mempalace_delete_drawers,mcp__plugin_mempalace_mempalace__mempalace_list_hallways`. Success = the names appear in the returned `<functions>` block; a name missing from the block did not load — re-check the exact spelling in the deferred list (short names such as `mempalace_list_drawers` do not match). If a call still fails with a type error after loading, retry once, then stop: report the tool and the exact error, and make no deletions.
- **Scope discipline.** The algorithm is in this skill. Do not read the plugin's scripts to learn how reset works. Resolve `PLUGIN_ROOT` the first time you need a script (Step 2's classifier), using the blocks in Step 5, and persist it as Step 5 describes.
- **Tools absent → stop.** If the tools are in neither the tool list nor the deferred-tools list — or `mempalace_status` fails in Step 2 — stop with this message: the MemPalace layer is not reachable in this session; no deletions were made; `.brain/` is untouched and preserved for a retry. To diagnose why the tools are absent, follow "Failure handling" in `skills/brain/references/mempalace-workflow.md`, report what you find, and stop.

---

## Step 1 — Read the recorded identity

```bash
grep "mempalace_wing" <project-root>/.brain/CLAUDE.md
```

Also read `mempalace_diary_agent` from the same file (fall back to the agent named in the diary sentence of that file, exactly as the wake-up recall rule does).

Identity comes from `.brain/CLAUDE.md` — these two recorded names are what the brain claims as its own. Wing names found later by pattern (in the wing list) are discovery aids only; they suggest candidates, they never establish ownership. If the file is missing or `mempalace_wing` is absent, do not infer the wing from the directory name: the classifier in Step 2 keeps the directory-derived wing diagnostic-only and surfaces orphan candidates instead, and any wing it surfaces becomes a question for the user, never a target on its own.

**Preserve `.brain/CLAUDE.md` until the MemPalace side is fully settled.** It is the only record of the wing and diary agent names. Never delete `.brain/` before the MemPalace steps are complete.

---

## Step 2 — Resolve the real wings (an empty result is never proof of an empty wing)

`mempalace_list_rooms` returning `{}` or an error for a wing name does **not** mean the project's data is gone or the wing is empty. MemPalace normalizes wing names — it lowercases and maps `-` and space to `_` (its `normalize_wing_name` rule) — so the recorded name and the actual wing can differ. Verify before concluding anything. The wing classes and the reasons behind them are documented in `skills/brain/references/wing-ownership.md`; the classifier below applies them, so you never hand-derive a class.

1. Call `mempalace_status` first. If it fails or the tools are missing, apply the Step 0 stop rule: the MemPalace layer is not reachable, no deletions, everything preserved for a retry.
2. Call `mempalace_list_wings` and write its raw result to a temporary file (or pipe it on standard input), then run the classifier — normalization, candidate discovery, per-wing classes, collisions, and the A/B/C outcome are deterministic and already implemented:

   ```bash
   "$PLUGIN_ROOT/bin/project-brain-reset" <project-root> --classify-wings <file>   # "-" reads standard input
   ```

   If `PLUGIN_ROOT` is not resolved yet, resolve it now (Step 0's scope bullet; the blocks live in Step 5) and persist it as Step 5 describes. Check the classifier's wing and drawer counts against what `mempalace_list_wings` returned — a mismatch means the transcription lost something; re-pipe the raw result instead of hand-fixing rows. Present the classifier's table to the user. Do not re-derive classes by hand; if you believe a row is wrong, say so and show your evidence — the user decides.
3. Act on the outcome:
   - **A — recorded wings found.** Run the normal flow (Steps 3–5) on the brain wiki and brain diary wings the user confirms.
   - **B — orphan candidates, recorded wing absent.** Show the orphan candidates as "possible orphans of this brain" and ask which exact wing(s) belong to this brain. Nothing becomes a deletion target until the user names it by exact name.
   - **C — nothing brain-owned.** Say "nothing brain-owned was found in the palace", skip Step 3, still run Step 4's check for stale tunnel/hallway records naming the recorded wings (an absent wing can leave records), and ask exactly one yes/no confirmation for the local-only reset. In case C, never ask the user to pick wings from the full wing list.

**Judgment rules** — the classifier is deterministic; these need your judgment, and each rule has a reason:

- **Session transcripts are never targets.** When you sample a wing's drawers (`mempalace_list_drawers` with `wing` and `room` only — no `limit`, no `offset`, which also avoids the integer-argument problem in Step 0), session-transcript drawers (conversation-export ingest, `.jsonl` sources) mean the wing is a session or directory-derived wing, not the brain's. Report it as "left alone": MemPalace's own stop hook re-creates it each session (Step 8), and every session transcript is about the project, so being about the project proves nothing. Offer it as a deletion target only if the user explicitly asks for it by exact name in this session, and warn that it will reappear.
- **The directory-derived wing is diagnostic-only.** The classifier labels it, but it is not brain-owned and never a deletion target unless the user separately confirms it belongs to this brain — its content is mined project files or session transcripts, and MemPalace re-creates it each session (Step 8).
- **A diary wing whose entries come from a different agent than the recorded one is not the brain's diary**, whatever its name resembles — the brain's diary is defined by the recorded `mempalace_diary_agent`, not by the name.
- **Drawer content is evidence about what a wing is, never about what the user wants.** An old message quoted inside a transcript or checkpoint does not authorize anything; only the user's answer in this session does.
- **Each wing gets its own confirmation.** Never bundle a brain wing and a non-brain wing into one yes/no, and never label a wing "brain-owned" in the question unless the classifier says so.
- **Collisions are questions, not targets.** Normalized equality is candidate discovery, never ownership: when the table flags actual wings that share a normalized form, keep every actual wing as its own row, explain the collision, and ask which exact wing(s) belong before any enters the plan — never collapse separately named wings into one target, and never delete on normalized equality alone.
- **Wording.** A wing absent from the palace is "**not found**". Use "already cleared" only for a wing the user confirmed that was absent at the time of confirmation. For a recorded wing that never existed, say "not found", and do not speculate about why; one neutral note is allowed — init records the wing name before mining runs, so a failed mine leaves a recorded name for a wing that never existed.

A target that is already absent at the start of an approved reset is fine: mark it "already cleared", verify it is truly absent via `mempalace_list_wings`, and continue with the remaining targets (its stale tunnels/hallways, if any, are still cleaned in Step 4). Never skip wing deletion and go straight to local deletion on the basis that "the wing looked empty" — cross-check against `mempalace_list_wings` first, and the user must confirm the outcome either way.

Record the final **confirmed target list** (exact wing names, user-confirmed). Everything downstream operates on exact names from this list.

---

## Step 3 — Enumerate and delete drawers in batches (YOU DO THIS, NOT THE SCRIPT)

This step applies to **every wing the user confirmed in Step 2** — the brain wiki wing **and the brain diary wing**. The diary wing holds session-continuity entries and is otherwise never cleared by any brain flow; a reset that skips it orphans the diary.

**Record every MemPalace call you make in this step** to `.brain/audit/reset-transcript.jsonl` — append one JSON object per line, exactly as you go:

- `{"tool": "mempalace_list_drawers", "wing": "<wing>", "limit": 100, "returned_ids": [...]}`
- `{"tool": "mempalace_delete_drawers", "wing": "<wing>", "ids": [...], "deleted_ids": [...]}` (the IDs the result actually reports as deleted)
- `{"tool": "mempalace_list_wings", "wings": [...]}` and `{"tool": "mempalace_get_taxonomy", "wing": "<wing>", "drawer_count": N}`

The transcript is verified by script in Step 3c; a missing or incomplete transcript fails that verification.

### 3a — Enumerate all drawer IDs with correct pagination

`mempalace_list_drawers` has a documented **maximum page size of 100**. For each confirmed wing:

1. `mempalace_list_rooms` → `{ "wing": "<wing-name>" }`. If it returns no rooms, still cross-check `mempalace_list_wings` before treating the wing as empty.
2. For each room: `mempalace_list_drawers` → `{ "wing": "<wing-name>", "room": "<room-name>", "limit": 100, "offset": 0 }`
   - If the result returns exactly 100 drawers, call again with `offset` incremented by 100 and collect more. Repeat until a page returns fewer than 100 results. Never re-fetch the first page, never skip offsets, never confuse drawers from similarly named wings.
3. Collect every drawer ID across all pages and all rooms.
4. Deduplicate the list (order-preserving), note the duplicate count, and cross-check the collected count against the wing's `drawer_count` from `mempalace_get_taxonomy`. **If the counts disagree, STOP: the palace changed during enumeration.** Report the discrepancy, delete nothing, and re-run the enumeration. Do not delete from an inconsistent target set.

Fetch and validate the complete target set BEFORE deleting, so later deletions do not shift pagination under the enumeration.

Show the user:
- Wing name
- Number of rooms
- Total drawer count (and any duplicates collapsed)
- A short sample of drawer IDs (up to 5)

Ask: **"Delete all N drawers from wing `<wing-name>`? (yes/no)"**

Do not call any deletion tool until the user says yes. If the user says no for a wing, skip that wing's deletion and record that the wing was kept.

### 3b — Delete in batches of at most 500

For each confirmed wing, pass the collected IDs to the bulk tool in consecutive batches of **at most 500 IDs**:

```
mempalace_delete_drawers → { "drawer_ids": [ ...up to 500 IDs... ] }
```

- 0 drawers → no deletion call; verify and continue.
- 1 drawer → ONE bulk call with that single ID. Still not `mempalace_delete_drawer`.
- 1,200 drawers → 3 bulk calls (500 + 500 + 200). Deletion calls scale with batches, not drawers.

**Inspect every batch result.** A successfully accepted batch is NOT proof every drawer was deleted. The result contains per-ID `results`, plus `count`, `deleted`, `errors`, `revisions_deleted`, and `revisions_error`:

1. For each ID, check its individual result record. An ID with `success: false` or an error message is a **failed** deletion.
2. An ID absent from the results list is **missing**, not deleted — record it as missing rather than assuming success.
3. Record `revisions_deleted`; if `revisions_error` is present, report it.
4. Retry only transient failures (timeouts, temporary unavailability), at most 2 attempts total per batch. Do not retry indefinitely; a batch that still fails stops the destructive phase for that wing with its diagnostics.
5. If a drawer is reported missing/not-found but the final wing inspection shows zero drawers remain, the deletion postcondition is satisfied — record that the tool response included the missing-ID result instead of claiming every original request succeeded. Never conceal errors behind a zero remaining count.

### 3c — Verify each wing, then CONTINUE (a vanished wing is success, not an error)

After deleting a wing's drawers:

1. Query the palace again: `mempalace_list_wings` (and `mempalace_get_taxonomy`, or rooms + `mempalace_list_drawers`).
2. The target wing is **cleared** when it is **absent from the wing list** (MemPalace deletes a wing implicitly with its last drawer — this is the expected success state) **or present with zero drawers**.
3. Record per wing: requested count, per-batch outcome, anomalies, final state, and the verification evidence.
4. **Move on to the next confirmed wing and keep executing the remaining reset steps.** The disappearance of one wing MUST NOT stop the reset: if the wiki wing vanished, continue with the diary wing and every remaining step. Do not `return`, exit, or stop because a wing is now missing — that absence is the postcondition you just verified.
5. A wing that still reports drawers after deletion is a real failure: report the remaining count and the per-ID errors, do NOT proceed to local deletion for that wing, and do not silently mark the reset successful. Other wings' processing continues.

6. **Script-verify the recorded transcript for this wing** (the wing counts as reset-verified only when this exits 0):

```bash
project-brain-reset <project-root> --verify-reset-transcript <wing-name>
```

   Exit 0 = the transcript satisfies every hard contract (no single-drawer deletes, batches ≤ 500, pages ≤ 100, every enumerated ID deleted, wing cleared after the last delete). Nonzero = a contract violation or missing evidence — read the printed violations, fix what they name, and re-run. If the command is unavailable on PATH (exit 127), use the same `PLUGIN_ROOT` re-resolution fallback shown in Step 5.

Report total drawers deleted per wing before moving on.

---

## Step 4 — Clean up tunnels and hallways (stale graph records)

Deleting the last drawer does not necessarily remove the wing's tunnels and hallways. After all confirmed wings' drawers are handled:

1. `mempalace_list_tunnels` (optionally filtered per wing) and inspect each tunnel's `source_wing`/`target_wing` endpoints. A tunnel is in scope when **one of its exact endpoint wings is one of the confirmed reset targets that was actually cleared**. Use exact names; do not match by normalized slug.
2. `mempalace_list_hallways` and inspect each hallway's wing association. Same exact-name rule.
3. Delete in-scope records one at a time — `mempalace_delete_tunnel` → `{ "tunnel_id": ... }`, `mempalace_delete_hallway` → `{ "hallway_id": ... }`. These are individual operations; there is no bulk variant — do not invent one.
4. Do NOT delete every tunnel/hallway in the palace. Records whose wings are not confirmed targets stay untouched.
5. For a wing whose drawer deletion FAILED or was kept by the user, leave its graph records in place for a retry and say so.
6. Re-list tunnels and hallways and verify the in-scope records are gone. Track tunnel failures and hallway failures separately from drawer deletion.
7. If a very large graph makes per-record deletion impractical, stop, report the observed limitation, and recommend `/project-brain:hard-reset` (Step 7). Do not substitute unverified database operations into this normal MCP path.

---

## Step 5 — Delete local files (dry run first, then explicit confirmation)

Run the dry run and show the output:

```bash
project-brain-reset <project-root> --dry-run
```

Review it with the user, then ask for explicit confirmation ("Delete the local brain files shown above? (yes/no)"). Only after the user says yes, run:

```bash
project-brain-reset <project-root> --confirm
```

Use the SAME command form for both the dry run and the confirmed run. If `project-brain-reset` is not on PATH (exit 127), resolve the plugin root once and use `"$PLUGIN_ROOT/bin/project-brain-reset"` for BOTH invocations — each shell invocation must resolve `PLUGIN_ROOT` again because a variable set in one tool call does not survive into the next:

```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}"
# If still empty: the harness prints "Base directory for this skill: <path>"
# directly above this skill's text (verified in --plugin-dir sessions, where
# the marketplace paths below do not exist). Do NOT count dirname levels by
# hand — a wrong depth guess cascades into a filesystem hunt that can end on
# a foreign copy of the plugin. Set BASE_DIR to that path and take the first
# candidate that actually contains the plugin's bin/:
BASE_DIR='<path-from-that-line>'
for _c in "$BASE_DIR" "$(dirname "$BASE_DIR")" "$(dirname "$(dirname "$BASE_DIR")")"; do
  if [ -d "$_c/bin" ]; then PLUGIN_ROOT="$_c"; break; fi
done
# Verify before use: ls "$PLUGIN_ROOT/bin" must list the project-brain-* wrappers.
: "${PLUGIN_ROOT:=$(ls -d ~/.openclaude/plugins/cache/ai-brain-marketplace/project-brain/*/ 2>/dev/null | sort -V | tail -1)}"
: "${PLUGIN_ROOT:=$HOME/.openclaude/plugins/marketplaces/ai-brain-marketplace/project-brain}"
"$PLUGIN_ROOT/bin/project-brain-reset" <project-root> --dry-run
```

Never type a bare `project-brain-*` command. The wrappers are not on PATH in this harness; every bare attempt wastes a turn, and roughly three consecutive failed Bash calls abort the whole session. Every `project-brain-*` command in this skill means `"$PLUGIN_ROOT/bin/<command>"`, with PLUGIN_ROOT read from `.brain/state/plugin-root.txt` (written by init) or resolved by the fallback above.

If PLUGIN_ROOT still cannot be resolved after all of the above, STOP and report exactly which paths you tried. NEVER write or modify `.brain/` files by hand as a substitute for the scripts — a brain the scripts did not build is unverifiable and counts as failure, not as a completed step.

After any shell resolves PLUGIN_ROOT successfully, persist it — the variable dies with the shell, the file survives into later shells and sessions:

```bash
printf '%s' "$PLUGIN_ROOT" > .brain/state/plugin-root.txt
```

In every LATER shell — Step 2's classifier run, Step 3c's transcript verification, and the confirmed run below — try the persisted value first (with a staleness check — a moved plugin must fall back to re-resolution, never be used blindly), then run the confirmed deletion in that same invocation:

```bash
PLUGIN_ROOT="$(cat .brain/state/plugin-root.txt 2>/dev/null || true)"
[ -n "$PLUGIN_ROOT" ] && [ -d "$PLUGIN_ROOT/bin" ] || PLUGIN_ROOT=""
"$PLUGIN_ROOT/bin/project-brain-reset" <project-root> --confirm
```

The script deletes `.brain/`, `graphify-out/`, strips the injected block from root `CLAUDE.md`, and removes `CLAUDE.project-brain.snippet.md`. Never pass `--confirm` before the user has seen the dry-run output and answered yes. Never run this step while any confirmed wing still has drawers or an unresolved ownership question.

**Consistency check (after the fallback resolves a root).** The harness-printed line "Base directory for this skill: <path>" implies a plugin root two levels up from that path (`<root>/skills/reset` → `<root>`). If the `PLUGIN_ROOT` you resolved differs from that directory, report both paths and prefer the base-directory root unless the user says otherwise — an older installed copy of the plugin can silently satisfy the last-resort marketplace guesses, and running its scripts would not match the skill text you are following.

---

## Step 6 — Report (distinguish the four postconditions)

Tell the user, separately:

- **Drawer deletion**: per confirmed wing — how many drawers were deleted, or that the wing was already absent/empty, kept by the user, or failed (with counts and diagnostics)
- **Tunnel cleanup**: in-scope tunnels deleted / remaining / preserved
- **Hallway cleanup**: in-scope hallways deleted / remaining / preserved
- **Local files**: whether `.brain/`, `graphify-out/`, the CLAUDE.md block, and the snippet were removed

A failed phase does not hide the others: report everything that completed and everything that did not. Only report the reset successful when drawer deletion, tunnel cleanup, and hallway cleanup all verified clean and the local files were removed.

Then say: run `/project-brain:brain` to initialize a fresh brain.

---

## Step 7 — When the normal reset cannot complete: recommend the hard reset

If the MCP route cannot complete safely — the bulk tool fails persistently, a wing still reports drawers after verified deletion attempts, or a huge graph makes per-record cleanup impractical:

1. Explain which phase failed.
2. Show the diagnostic evidence: remaining drawer counts, unresolved tunnel/hallway records, or the enumeration inconsistency.
3. Explain the failure class: MCP availability, enumeration problem, partial deletion, or unresolved ownership question.
4. If the problem is ownership (which wing belongs to this project), resolving ownership is the fix — do NOT recommend a database reset for it.
5. Otherwise, recommend `/project-brain:hard-reset` — the separate, database-level destructive operation with its own dry run, backup, and explicit authorization. It is NOT launched automatically and is never a routine substitute for bulk deletion.

---

## Step 8 — Know the re-creation hazard (read before declaring the reset complete)

MemPalace's own session stop hook re-mines the `MEMPAL_DIR` directory **without `--wing`** when that variable is set (verified in MemPalace 3.11.0 `hooks_cli.py`: `hook_stop` → `_maybe_auto_ingest` → `mine <dir> --mode projects`, wing falls back to `normalize(dirname)`). Consequence: after a clean reset, a wing named after the project's normalized directory name can **reappear automatically** at the next session stop, containing mined project files — not brain data.

The plugin cannot prevent this safely: `MEMPAL_DIR` belongs to MemPalace's configuration, the hook runs in MemPalace's own process, and suppressing another product's hooks from here is out of scope. So this is documented behavior instead:

- New brains record a timestamped wiki wing (`wiki_<slug>_<UTC-timestamp>`) that never collides with the directory-derived wing; legacy names recorded in `.brain/CLAUDE.md` are kept.
- After a reset, if the user reports a wing reappearing with mined project source in it, that is the stop hook, not a failed reset.
- `project-brain-doctor` prints this same note and warns when `MEMPAL_DIR` points at the project root.
- Do not "clean up" the re-created wing as part of a brain reset — it belongs to MemPalace's project mining, and deleting it is the user's separate decision.
