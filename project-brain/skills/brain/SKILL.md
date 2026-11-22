---
description: Use when the user wants a persistent AI brain, project memory, LLM wiki, personal knowledge base, handoff memory, an architecture/codebase map, source ingestion, an Obsidian vault mirror, or cross-project brain coordination — or says "set up the brain", "remember this project", "continue from memory", or "prepare a handoff". Maintains the layered brain under `.brain/` (raw evidence, wiki, session brief) plus MemPalace memory, graphify graphs, and script health gates. NOT for one-off questions needing no persistence (just answer), for a code graph without a brain (use /graphify), or for MemPalace cleanup outside a brain reset (use the reset skill).
---

# Project Brain

Build and maintain a persistent brain for the current project so a future
model can understand it without this chat. Six layers, kept aligned: evidence
(`.brain/raw/`), synthesis (`.brain/wiki/`), memory (MemPalace), map
(`graphify-out/`), handoff (`.brain/state/session-brief.md`), Obsidian vault
(opt-in mirror). Depth: `references/brain-architecture.md`.

## Harness facts (ignoring any of these wastes turns)

- This skill is injected once and sits in context for every later turn; files
  under `references/` do NOT — load one only on its trigger. Relative
  `references/...` paths resolve against the "Base directory for this skill"
  line the harness prints above this text.
- A tool missing from the tool list may still be DEFERRED (named in the
  deferred-tools list). Rules: `references/deferred-tools.md`.
- Parallel tool calls in one turn do not see each other's results; shell
  variables do not survive between Bash calls.
- `Edit` requires a prior `Read` of the same file: `references/edit-discipline.md`.
- After compaction only a summary survives; the run can be cut at any moment
  and you cannot see the remaining budget — make progress durable in small
  steps (Work loop step 5).

## Resolve the plugin root (before the first command of a session)

Never type a bare `project-brain-*` command: the wrappers are not on PATH in
this harness, every bare attempt wastes a turn, and roughly three consecutive
failed Bash calls abort the whole session. Every `project-brain-<tool> …` in
this skill means `"$PLUGIN_ROOT/bin/project-brain-<tool>" …`, with PLUGIN_ROOT
read from `.brain/state/plugin-root.txt` (written by init) or resolved by the
fallback:

```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}"
# A stale CLAUDE_PLUGIN_ROOT (moved/foreign copy) must not skip discovery:
# validate it against bin/ and clear it when invalid; a valid one is kept.
if [ -n "$PLUGIN_ROOT" ] && [ ! -d "$PLUGIN_ROOT/bin" ]; then
  PLUGIN_ROOT=""
fi
# If still empty: the harness prints "Base directory for this skill: <path>"
# directly above this skill's text. Do NOT count dirname levels by hand — a
# wrong depth guess ends on a foreign copy of the plugin. Take the first
# candidate that actually contains the plugin's bin/.
if [ -z "$PLUGIN_ROOT" ]; then
  BASE_DIR='<path-from-that-line>'
  for _c in "$BASE_DIR" "$(dirname "$BASE_DIR")" "$(dirname "$(dirname "$BASE_DIR")")"; do
    if [ -d "$_c/bin" ]; then PLUGIN_ROOT="$_c"; break; fi
  done
fi
# Verify before use: ls "$PLUGIN_ROOT/bin" must list the project-brain-* wrappers.
: "${PLUGIN_ROOT:=$(ls -d ~/.openclaude/plugins/cache/ai-brain-marketplace/project-brain/*/ 2>/dev/null | sort -V | tail -1)}"
: "${PLUGIN_ROOT:=$HOME/.openclaude/plugins/marketplaces/ai-brain-marketplace/project-brain}"
"$PLUGIN_ROOT/bin/project-brain-doctor" <project-root> --strict
```

After any shell resolves PLUGIN_ROOT, persist it — the variable dies with the
shell, the file survives:

```bash
printf '%s' "$PLUGIN_ROOT" > .brain/state/plugin-root.txt
```

In every LATER shell, load it with a staleness check (a moved plugin must fall
back to re-resolution, never be used blindly):

```bash
PLUGIN_ROOT="$(cat .brain/state/plugin-root.txt 2>/dev/null || true)"
[ -n "$PLUGIN_ROOT" ] && [ -d "$PLUGIN_ROOT/bin" ] || PLUGIN_ROOT=""
```

If PLUGIN_ROOT still cannot be resolved, STOP and report exactly which paths
you tried. NEVER write or modify `.brain/` files by hand as a substitute for
the scripts — a brain the scripts did not build is unverifiable and counts as
failure, not as a completed step. Version skew: installed `skills/` text can
be older than installed `scripts/`; the scripts print their resolved root and
version — check that line before trusting mixed output.

## Session start (every session; also after a model change or compaction)

1. Resolve PLUGIN_ROOT (above) if not already done this session.
2. Read `.brain/CLAUDE.md` if present.
3. Read `.brain/state/session-brief.md` if present.
4. Read `.brain/wiki/index.md` if present.
5. Read `graphify-out/GRAPH_REPORT.md` before architecture, code-navigation,
   or relationship questions, if it exists.
6. If `.brain/` does not exist and the user asked to set up a brain, run
   Initialize (below). If `.brain/CLAUDE.md` is missing or incomplete, say so
   and let Initialize repair it — never hand-write brain files.
7. Check MemPalace before claims about previous decisions, preferences, or past work (wing-scoped recall; rules and recipes: `references/mempalace-tools.md`). If `.brain/CLAUDE.md` is missing or does not define a non-empty `mempalace_wing`, skip the search and diary read, say the brain is not initialized (run project-brain-init or fix the file), and never infer a wing. Otherwise: `mempalace_search` (wiki-knowledge claims, recorded wing) and `mempalace_diary_read` (earlier sessions, via `mempalace_diary_agent`) — the one that fits the claim, or both. Availability: Contract 1.
8. If Obsidian MCP tools are available, note the vault mirror is possible;
   do not mirror automatically (Contract 5).
9. If a layer is unavailable, say exactly which one and continue from the
   others — never fabricate a check to hide the gap.
10. A wing that seems missing or empty is not proof: MemPalace normalizes wing names, so compare normalized forms (`mempalace_list_wings`) before concluding — `references/mempalace-tools.md` → "Empty-wing lookups".

## Work loop (batch maintenance — the ONE procedure for every session that changes the brain)

Every step below is script-gated. Run the script, read its output, fix what it
names, re-run. Never claim a step is done without its script exiting 0.

1. If `.brain/` does not exist: run Initialize (below) first.
2. Build the work list: `project-brain-inventory <project-root> inventory`.
   The UNCOVERED core/important units are your obligations; the git-history
   unit is covered by citing the digest from step 3.
3. Generate digests: `project-brain-inventory <project-root> git-digest`, and
   (when `graphify-out/graph.json` exists) `graph-digest`. Build or refresh
   the graph **at most once per session**, and only if the doctor says stale —
   primary: the `/graphify` skill (Contract 2); fallback: the CLI.
4. Cover units in a small batch (a few units per pass). **Before the first wiki write of this session, read `references/wiki-schema.md`** — pages written without it guess the schema and fail lint. Write or extend pages under `.brain/wiki/`; cite every claim inline as `{{src path/to/file.ts:10-20 "anchorText"}}`; decision pages need `rationale_source:`. Stub pages do not count as coverage.
5. Make progress durable: after each batch run `project-brain-lint <project-root> --verify` (whenever citations changed), then — once the lint is clean — snapshot the wiki: `project-brain-wiki <project-root> snapshot`. Then update `.brain/state/session-brief.md` honestly — what changed, what is verified, what remains; preserve any `BLOCKED-WING:` line in every brief rewrite until reset removes the brain. The inventory persists progress; resume from disk, not the transcript.
6. Check doc cross-refs: `project-brain-inventory <project-root> crossrefs`
   (exit 1 lists missing refs — create or fix them, then re-run).
7. Gate: `project-brain-doctor <project-root> --strict`. Exit 0
   (`passed-for-scope`) → done for this scope; the receipt is under
   `.brain/audit/runs/`. Nonzero → fix the printed gate failures, re-run.
8. Repair limit: the scripts count your rounds — every failing `project-brain-lint` or `project-brain-doctor <project-root> --strict` run prints `repair round N/3` (per-gate counter: `.brain/state/repair-rounds`; a passing run resets only its own gate). At `repair round 3/3 — STOP and write the honest report`, stop and report exactly which gates failed and what remains — an honest incomplete report is required; a hopeful "done" is forbidden.

### Context discipline (the loop survives small context windows)

- Read source files in a bounded slice (`sed -n '1,120p'` or Read with a
  limit); widen only when the citation needs it — a whole-file read of a
  large source can consume the remaining budget in one step.
- Never re-run a generator or digest that already produced output this
  session; re-read its result from disk.
- Prefer `rg -n` over whole-file reads to find where something lives.
- When the budget feels tight, finish the batch through step 5, then end the
  session with an honest note in `.brain/state/session-brief.md`.

## Wiki ledger (page history in `.brain/state/wiki.git`)

Wiki edits are auto-snapshotted (a hook commits `auto: <tool> <page>`); the
ledger is local to the brain and has nothing to do with the project's git.
Four triggers: after compaction run `status` + `log 5` instead of re-reading
pages (`status` separates `uncommitted:` pages from `recently snapshotted:`
ones); before a large page rewrite run `snapshot`; verify any edit with
`diff <page>` — it shows the page's most recent change (last two versions
plus anything uncommitted); after a bad edit run `diff <page>`, then
`restore <page>` — no rev needed, it targets the version before the page's
latest change (dry run by default; `--rev <rev>` picks an older one from
`history <page>`). Subcommands, bounds, and failure paths:
`references/wiki-ledger.md`.

## Initialize (first run only — owns first-run order)

Autonomous: continue to the final report, never a user to-do list. Pause only
for a genuinely missing decision or access; the leftover-wing check never pauses.

1. Run `project-brain-init <project-root> "<Project Name>"`; verify the new wing's uniqueness in step 7.
2. Read the files it created: `.brain/CLAUDE.md`, `.brain/state/session-brief.md`, `.brain/wiki/index.md`. Immediately write an IN-PROGRESS `.brain/state/session-brief.md` (Current state: initialize running, plus the next step).
3. **Read `references/mempalace-tools.md` now**, before the first MemPalace call of this mode — policies and call recipes.
4. Load deferred MemPalace schemas in ONE ToolSearch call: query `select:<full name 1>,<full name 2>,…` (exact full names; short names do not match), `max_results` at least the number of names. Load: `mempalace_status`, `mempalace_list_wings`, `mempalace_list_tunnels`, `mempalace_list_hallways`, `mempalace_get_taxonomy`, `mempalace_diary_write`, `mempalace_list_rooms`, `mempalace_mine`. Verify them in the returned `<functions>` block; then call `mempalace_status`. If absent from both tool lists, report memory unavailable and continue (`references/deferred-tools.md`).
5. Doctor baseline: run `project-brain-doctor <project-root>` and read all four sub-scores. Repair each `BELOW REPAIR THRESHOLD` score in the Work loop per `references/brain-lifecycle.md` → Self-correction scan; the diary and log below repair Memory sync. Skip only a repair requiring access you lack; name that access in the report.
6. Report the current availability of MemPalace MCP, the graphify skill/CLI,
   and Obsidian MCP. No install instructions unless the user asks.
7. **Leftover-wing check (new brains only — skip on re-init):** read `mempalace_wing` and `mempalace_diary_agent` from `.brain/CLAUDE.md`. Call `mempalace_status`, then `mempalace_list_wings`, `mempalace_list_tunnels`, `mempalace_list_hallways`. If the recorded wiki wing exists there or in tunnel/hallway records, do NOT mine into it; prepend `BLOCKED-WING: <exact wing name> — do not mine; resolve via /project-brain:reset` (recorded name) to `.brain/state/session-brief.md`, preserving its content. Report the collision and memory layer **not done** — init cannot rename it. Report each match's exact name and drawer count, plus tunnel/hallway records. Offer `/project-brain:reset` for wiki/brain diary matches or orphan candidates (read `references/wing-ownership.md`); directory-derived wings are informational only (MemPalace re-creates them), no cleanup offer. Never delete unasked.
8. Ingest the project's primary sources (README, manifests, entry points)
   into `.brain/raw/` or pointer files per `references/evidence-lifecycle.md`.
9. Compile wiki pages under Contracts 7 and 8 (read `references/wiki-schema.md` before the first write): update System Overview, add `.brain/wiki/sources/` summaries with `reliability:` frontmatter, regenerate the index with `project-brain-lint <project-root> --reindex`, and record contradictions in the source page and `open-questions.md`. If the brief has `BLOCKED-WING:` naming the recorded wing, skip mining, step 10's drawer check and step 13's re-mine; report memory **not done**. Otherwise mine `.brain/wiki` with explicit `--wing` from `mempalace_wing` (Recipe 3 in mempalace-tools.md; dry run first), never the project root.
10. Verify with `mempalace_get_taxonomy` or `mempalace_list_rooms`: the recorded wing must have drawers. If empty, repair now (mining recipe, dry run first); if blocked, report the failing call, error and missing access, then continue.
11. Update `.brain/state/session-brief.md` (under 400 words), run `project-brain-lint <project-root>`, and clear error-level issues.
12. Write `mempalace_diary_write` with the agent from `mempalace_diary_agent` in `.brain/CLAUDE.md` using this exact format:

    ```text
    [DATE] | [PROJECT] | [ACTION]
    Summary: [1-2 plain English sentences describing what happened]
    Key finding: [the most important thing discovered]
    Contradictions: [any source conflicts found, or "none"]
    Log: [path to session log file]
    Next: [top priority action for next session]
    ```

    Plain text, not the dialect shown by `mempalace_status`.
    The `Log:` field is `.brain/log/<YYYYMMDD>.md`. After a successful diary write, append to that path (preserve existing content):

    ```text
    ## [HH:MM] diary | <title>
    - MemPalace diary written (agent <diary agent>)
    ```

    Fill the placeholders with the date, time, title and recorded agent. Read `references/mempalace-workflow.md` before retrying a failed write; never log it as written if it failed.
13. **Run the `## Work loop` section.** Fresh brain: `project-brain-inventory <project-root> inventory` and `project-brain-inventory <project-root> git-digest` first. Repair sub-scores and gates; re-mine wiki changes. Append a second diary and log entry only if the Work loop changed findings or contradictions. Run `project-brain-doctor <project-root> --strict` until it exits 0 or the Work loop's repair cap is spent; report all four sub-scores from the last strict run's output.
14. Final report: "complete" only if the strict gate exited 0, no sub-score remains flagged and the recorded wing is not blocked. Otherwise say **INCOMPLETE** and list each failing gate or sub-score with its failing command, any blocked wing, and missing access under **not done**. A flagged sub-score is never "expected". No next-session to-do list for runnable work.

MemPalace and graphify are pre-installed; do not reinstall.

## Other modes (detail lives in references — read the named file)

| Mode | Use when | Authoritative steps |
|---|---|---|
| Ingest | a source, doc, or explanation arrives | `references/brain-lifecycle.md` → Ingest; intake rules: `references/evidence-lifecycle.md` |
| Query | answering a question from the brain | routing table: `references/agent-playbook.md` (also `references/retrieval-strategy.md`) |
| Build/refresh graph | code or docs changed; user asks how pieces connect | `references/brain-lifecycle.md` → Build or refresh graph; policy: `references/graphify-workflow.md` |
| Consolidate memory | after significant conversations or decisions | `references/brain-lifecycle.md` → Consolidate memory |
| Mirror to Obsidian | the user asks to view/sync the vault | `references/obsidian-workflow.md` |
| Audit / lint | periodic health check | `references/brain-lifecycle.md` → Audit / lint |
| Self-correction scan | doctor sub-score < 70, or brief > 7 days old | `references/brain-lifecycle.md` → Self-correction scan |
| Handoff | before ending a large session or compaction | `references/handoff-protocol.md` |
| Cross-brain | multi-project coordination | `references/cross-brain-workflow.md` |

## Behavioral contracts

**1. Verify before calling any tool unavailable.** A tool is unavailable only if it is in NEITHER the tool list NOR the deferred-tools list. A deferred tool exists — load its schema first with ONE ToolSearch call (query `select:<full name 1>,<full name 2>` — comma-separated exact full names — and `max_results` at least the number of names; success = the names appear in the returned `<functions>` block), then call it; for MemPalace the verification call is `mempalace_status`. Report a failing call as the real failure it is, with the tool and the error. Never probe with shell/node/pip, never write a check that always succeeds, never build a workaround client. Covers ANY tool (including `TaskCreate`). Details: `references/deferred-tools.md`.

**2. Never reinvent graphify — keep its precedence straight.** Do not write scripts to parse code structure or extract relationships. Precedence: `/graphify` skill = PRIMARY builder (it runs the semantic pass through the session's own model — per this project's setup, reported, verify on first use); graphify MCP tools = query surface once a graph exists (deferred; reconnect the server after ANY change to graph.json — first build, full rebuild, or incremental `graphify update .` — it reads the graph at startup); CLI = FALLBACK (`graphify .` full build, `graphify update .` code-only; `GRAPHIFY_BACKEND=none` on BOTH `extract` and `cluster-only` when no API access, or you get "Community N" placeholders). Details: `references/graphify-workflow.md`.

**3. Never let wiki edits be the last step.** Follow the post-wiki loop below.

**4. The session brief must be readable in under 2 minutes.** Over 400 words,
trim it. The brief is a map to the wiki, not a replacement for it; task
checklists live in `.brain/tasks/next-actions.md` only.

**5. Obsidian vault mirror is opt-in.** Never push without the user asking.

**6. Route to the right layer first.** Code navigation → graphify; decisions → MemPalace; status → session brief. Routing: `references/retrieval-strategy.md`, `references/agent-playbook.md`.

**7. Primary source verification.** Before documenting any claim about a file's status, purpose, imports, or behavior, read that file directly — secondary sources (READMEs, critic reports, AI analyses) are opinions, not evidence; document contradictions under `## Known Inaccuracies in This Source` on the source page. Before labeling a file orphaned, search the whole codebase for imports and dynamic references.

**8. No speculative language in architecture pages.** "Likely", "probably",
"appears to", "seems to" are banned unless tagged as a hypothesis under an
open question. If you do not know, write "Integration method not yet verified"
and add the question to `open-questions.md`.

**9. Wiki authoring discipline.** Read `references/wiki-schema.md` before the first wiki write of a session; cite line numbers verified against the code (`grep -n` / bounded Read), never copied from docs; never hand-edit `.brain/wiki/index.md` (regenerate with `project-brain-lint <project-root> --reindex`); wikilinks target wiki pages only.

**10. Edit discipline.** Read the page immediately before every Edit and again after compaction or any failed Edit; prefer Write for whole-page rewrites; never batch dependent edits to one file in a single parallel turn; retry an Edit once, then switch to Write. State only actions you actually emitted. Details: `references/edit-discipline.md`.

<!-- ponytail: skill-size ceiling; extend procedures, not repeated contracts. -->

## Post-wiki loop (after ANY wiki change)

1. Regenerate the index with `project-brain-lint <project-root> --reindex`,
   never by hand. Add cross-links and backlinks; extract decisions.
2. Resolve open questions: for each question in `open-questions.md`, attempt
   an answer from files already read; leave it open only if the answer needs
   a file not yet ingested (name it) or genuinely does not exist.
3. Read `references/post-wiki-checklist.md` → Required graph refresh: follow its doctor-reason routing and MCP reconnect rule; skip wiki-only changes.
4. Consolidate MemPalace memory (diary entry) if session context changed;
   record contradictions and open questions; update the session brief; append
   a log entry; run lint for large changes.

## Brain reset (only on an explicit user request to delete or start clean)

Reset is irreversible (`.brain/`, `graphify-out/`, MemPalace drawers). Do not
reset when a smaller repair suffices (re-compile affected pages; fix one
page; delete one wing's drawers via MCP). The full procedure — identity-first
wing resolution, batched drawer deletion, graph cleanup, dry run, explicit
confirmation, the re-creation hazard — lives in the `/project-brain:reset`
skill; follow it exactly. Hard rules: drawers only via
`mempalace_delete_drawers`, batches of at most 500 IDs, never the
single-drawer tool; the reset script has no MCP access, so unreachable tools
mean stop and report, never claim deletion. When the normal route cannot
complete safely, recommend `/project-brain:hard-reset` (its own dry run,
backup, authorization) — never for an unresolved ownership question.

## References (load only on the trigger)

- `references/brain-lifecycle.md` — full per-mode procedures.
- `references/agent-playbook.md` — decision tree + retrieval routing table.
- `references/audit-workflow.md` — processing human feedback files.
- `references/brain-architecture.md` — the six layers in depth.
- `references/brain-health-metrics.md` — what the doctor scores mean.
- `references/cross-brain-workflow.md` — multi-project brains.
- `references/deferred-tools.md` — any tool unavailable or deferred.
- `references/edit-discipline.md` — before page edits; after any failed Edit.
- `references/evidence-lifecycle.md` — raw evidence intake and aging.
- `references/wiki-ledger.md` — page history: status/snapshot/log/diff/restore.
- `references/graphify-workflow.md` — graph builds, MCP tools, CLI fallback.
- `references/handoff-protocol.md` — preparing a handoff brief.
- `references/harness-detection.md` — harness detection; plugin-root edges.
- `references/install-and-integration.md` — dependency state; CLAUDE.md
  integration.
- `references/mempalace-tools.md` — BEFORE any MemPalace call.
- `references/mempalace-workflow.md` — diary format; palace lock; failures.
- `references/obsidian-workflow.md` — vault mirror.
- `references/post-wiki-checklist.md` — checklist form of the loop above.
- `references/retrieval-strategy.md` — layer strengths and blind spots.
- `references/wing-ownership.md` — which wings belong to the brain.
- `references/wiki-schema.md` — BEFORE the first wiki write of a session.

## Completion standard

An operation is complete only when you can answer: what changed, why, which
evidence supports it, which relationships matter, what memory should survive,
what the next model should read first, and what should happen next — each
backed by a script exit code or an honest "not done" statement.
