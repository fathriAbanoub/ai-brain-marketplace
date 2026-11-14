# Project Brain

A local-first AI memory plugin for OpenClaude and Claude Code-style harnesses. It gives an assistant a durable project brain: a source-grounded wiki with local version history, session handoffs, health gates with an honest repair limit, optional MemPalace semantic memory, and optional graphify dependency maps.

When a model changes, a chat resets, or context compacts, the project context should not disappear — and it should never be rebuilt from a model's memory of a transcript.

> Project Brain is not a source-code deletion tool, not a cloud sync service, and not a replacement for reading the repository. It is a structured memory layer built around the source of truth: the project files on disk.

## The six layers

1. **Evidence** — `.brain/raw/` and the repository files. The source of truth.
2. **Synthesis** — `.brain/wiki/`. Small, linked markdown pages maintained by the agent, every claim cited inline as `{{src path/to/file.ts:10-20 "anchorText"}}`. Page history lives in the wiki ledger (below).
3. **Memory** — MemPalace (optional MCP). Verbatim recall, user preferences, and the session diary, mined from the wiki into a per-project wing.
4. **Map** — graphify output in `graphify-out/` (optional). Relationships, communities, and structural hints built from real source code.
5. **Handoff** — `.brain/state/session-brief.md`. The short briefing a future model reads first.
6. **Vault** — Obsidian MCP (optional, opt-in). Mirror selected wiki pages to the user's vault on request; never automatically.

## Install

```bash
openclaude
/plugin marketplace add /path/to/ai-brain-marketplace
/plugin install project-brain@ai-brain-marketplace
```

Requires Python 3.9+ (stdlib only) and `git` for the wiki ledger (everything else degrades gracefully without it).

## The commands in `bin/`

The wrappers are not on `PATH` inside a session. Resolve the plugin root first:

```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}"
: "${PLUGIN_ROOT:=$(ls -d ~/.openclaude/plugins/cache/ai-brain-marketplace/project-brain/*/ 2>/dev/null | sort -V | tail -1)}"
: "${PLUGIN_ROOT:=$HOME/.openclaude/plugins/marketplaces/ai-brain-marketplace/project-brain}"
```

| Command | Purpose |
| --- | --- |
| `project-brain-init <project-root> "<Title>" [--force] [--wing <name>]` | Create or refresh the `.brain/` scaffold, the wiki ledger with a baseline snapshot, and `.graphifyignore` (see the init lifecycle below) |
| `project-brain-inventory <project-root> inventory\|crossrefs\|git-digest\|graph-digest [--json]` | Unit table with coverage tiers; doc cross-reference check; git/graph digests |
| `project-brain-lint <project-root> [--json] [--reindex] [--verify]` | Lint wiki structure, links, citations; `--reindex` regenerates `wiki/index.md`; `--verify` stamps clean pages in `.brain/verification.json` |
| `project-brain-doctor [<project-root>] [--strict] [--json]` | Health score with four sub-scores (repair threshold 70); `--strict` runs the gates, writes a receipt under `.brain/audit/runs/` |
| `project-brain-wiki <project-root> status\|snapshot\|log\|history\|diff\|restore` | The wiki ledger (below) |
| `project-brain-reset [<project-root>] [--dry-run] --confirm` | Delete local brain files (`.brain/`, `graphify-out/`, CLAUDE.md block); `--verify-reset-transcript WING` and `--classify-wings FILE` are the reset-skill evidence helpers |
| `project-brain-hard-reset --wing <exact-wing-name> [--db-path <file>] [--confirm --plan-hash <hash>] [--allow-live]` | The separate database-level MemPalace deletion: dry run by default, plan hash binding, backup, single transaction. Wing-tagged SQLite palaces only — the default ChromaDB backend is refused (data must be removed through the Chroma API) |
| `project-brain-audit-open <project-root>` | List open audit artifacts |
| `project-brain-update-check` | Compare installed plugin/MemPalace/graphify versions (numeric compare, so 0.10.0 sorts above 0.9.4) |
| `project-brain-hook-install <project-root>` | Install an optional git `post-commit` hook that runs a fast lint and appends a summary to `.brain/log/git-hooks.md` |

Every `bin/` wrapper execs the matching `scripts/<name>.py`; all scripts are stdlib-only.

## The init lifecycle (what `project-brain-init` actually does)

One command scaffolds everything local; it is idempotent (re-runs preserve protected areas: `raw/`, `wiki/sources/`, `log/`, `audit/`) and never regenerates an existing brain's recorded wing:

1. Creates `.brain/` with `CLAUDE.md` (records `mempalace_wing: wiki_<project-slug>_<UTC-timestamp>` and `mempalace_diary_agent`), seed wiki pages (`architecture/System Overview.md`, `open-questions.md`), `state/session-brief.md`, `tasks/next-actions.md`, and `log/`. `raw/` and `audit/` are lazy directories: scaffold does not create them — the later step that fills them does (digests/reports create `raw/…`, doctor/lint create `audit/…`).
2. Generates `wiki/index.md` from the real page tree — the index is script-owned; regenerate with `project-brain-lint <project-root> --reindex`, never by hand.
3. Writes `.brain/state/plugin-root.txt` so later shells resolve the plugin without guessing.
4. Creates the **wiki ledger** at `.brain/state/wiki.git` with a baseline snapshot. `git` missing → warns and continues (everything else still works). If the project's own repo does not exclude `.brain/state/`, init prints a one-line note; it never edits your `.gitignore`.
5. Ensures `.graphifyignore` excludes `.brain/`, `graphify-out/`, and common secret paths.
6. Appends a log entry and prints the resolved plugin root and version.

What init does **not** do: it does not call MemPalace (the agent mines the wiki wing via MCP recipes after verifying the generated wing name against the palace), and it does not run graphify (the agent builds the graph once per session, only when the doctor says stale).

## The wiki ledger (local version history for `.brain/wiki`)

A safety net so an agent can see what changed, undo a bad edit, and recover after compaction without re-reading whole pages. Storage is a separate bare git dir at `.brain/state/wiki.git` whose work tree is `.brain/wiki` — never a `.git` inside the wiki dir, and nothing to do with the project's own git.

```bash
"$PLUGIN_ROOT/bin/project-brain-wiki" <project-root> status      # uncommitted pages, then recently snapshotted pages
"$PLUGIN_ROOT/bin/project-brain-wiki" <project-root> snapshot    # commit all wiki changes (no-op when clean)
"$PLUGIN_ROOT/bin/project-brain-wiki" <project-root> log 5       # last 5 snapshots
"$PLUGIN_ROOT/bin/project-brain-wiki" <project-root> history "architecture/System Overview.md"
"$PLUGIN_ROOT/bin/project-brain-wiki" <project-root> diff "architecture/System Overview.md" [--from REV --to REV]
"$PLUGIN_ROOT/bin/project-brain-wiki" <project-root> restore "architecture/System Overview.md" [--rev REV] [--apply] [--force]
```

- The hook commits every edit, so the defaults answer from snapshot history, not just the working tree. `status` prints two labeled sections: `uncommitted:` (staged, unstaged, and untracked pages, listed individually; says "no uncommitted changes" when there are none) and then `recently snapshotted:` (the pages touched by the last few snapshots — the window is printed in the header); a page appears in one section only, and the `snapshot with:` hint appears only when something is uncommitted. `diff <page>` shows the page's most recent change (its last two snapshot versions plus any uncommitted change on top; a single-version page says so instead of an empty diff); `diff` with no page shows the last snapshot's changes plus uncommitted ones (untracked pages appear as new files).
- `restore <page>` without `--rev` targets the version before the page's latest change — the undo default; the revision is pinned to a full hash before anything runs, so the automatic pre-restore snapshot cannot move a relative rev like `HEAD` out from under the restore. The dry run prints a direction legend ("- lines are in the page now, + lines are in the target") because git's swapped a/ b/ headers read backwards there.
- `restore` is a dry-run diff by default (read-only, so a dirty page is allowed); `--apply` over uncommitted changes requires `--force` (which discards them into the automatic pre-restore snapshot — the current state is never lost), verifies the restored file against the target blob, and commits `restore: <page> (from <rev>)`.
- Wiki edits are also auto-snapshotted by the PostToolUse hook (`auto: <tool> <page>` messages), so history accumulates without agent effort.
- Page arguments are validated: absolute paths, `..`, and any symlink in the page path are rejected (an in-wiki symlink alias would operate on its target, not the named page); spaces and non-ASCII names work everywhere.
- Missing `git` → clear message, exit 127. A locked index fails fast (exit 75), never hangs. Output is bounded.
- Snapshots use a fixed identity (`project-brain <project-brain@localhost>`), no hooks, and never read user/global/system git config.

## Graphify: skill first, MCP for queries, CLI as fallback

- **Primary builder: the `/graphify` skill** (it runs the semantic pass through the session's own model). Build or refresh at most once per session, and only when `project-brain-doctor` reports the graph stale.
- **Query surface: the graphify MCP tools** (`query_graph`, `get_node`, `get_neighbors`, `get_community`, `god_nodes`, `graph_stats`, `shortest_path`, `get_pr_impact`, `list_prs`, `triage_prs`). The tools may be deferred (not in the tool list): load their schemas with ONE ToolSearch call (`query` = `select:<full tool name 1>,<full tool name 2>`, comma-separated exact full names; `max_results` at least the number of names). The server reads the graph at startup — reconnect it after anything that changes `graph.json` (first build, full rebuild, or an incremental `graphify update .`).
- **Fallback: the CLI** — `graphify .` (full build), `graphify update .` (code-only changes, AST-only), with `GRAPHIFY_BACKEND=none` on both `extract` and `cluster-only` when no API access is available (otherwise you get "Community N" placeholders). Never pass `graphify-out` itself as the path.

## Hook behavior (bundled, automatic)

`hooks/hooks.json` registers two events; both are silent no-ops without `.brain/`, never call MemPalace write tools or the CLI, do no network I/O, and always exit 0:

- **SessionStart** (also fires after context compaction) — injects a short, bounded (≤ 700 chars) status: brain presence **stated as a launch-time snapshot** (if reads under `.brain/` fail later, the brain was removed after launch — run init), the doctor's graphify freshness line, pointers to `session-brief.md` / `index.md`, one wiki-ledger line (the uncommitted page count and the last snapshot's id, subject, and age, reported separately) when a ledger exists, and the detected harness.
- **PostToolUse** (matcher `Write|Edit|MultiEdit|NotebookEdit`) — an edit inside `.brain/wiki/` takes a **silent auto-snapshot** of the wiki ledger and emits nothing. Any other edit that leaves the graph stale emits a throttled reminder (at most every 300 s; the same reason at most once per 1800 s).

Opt out with `PROJECT_BRAIN_HOOKS_DISABLED=1` (disables the auto-snapshot too) or by removing `hooks/hooks.json`. A corrupt or locked ledger never breaks or blocks a session: the hook swallows every ledger failure and stays silent.

## Reset: what the script does and does not do

`project-brain-reset` deletes **local files only** — `.brain/` (including `.brain/state/wiki.git`, so no stale ledger survives), `graphify-out/`, the `# Project Brain` block in root `CLAUDE.md`, and `CLAUDE.project-brain.snippet.md`. It never touches project source code and **never deletes MemPalace drawers**: a shell subprocess cannot call in-session MCP tools, and the `mempalace` CLI has no drawer-delete command. Drawer deletion is the `/project-brain:reset` skill's job:

1. Read `mempalace_wing` and `mempalace_diary_agent` from `.brain/CLAUDE.md` before anything is deleted.
2. Call `mempalace_status` first; if it fails, stop — no deletions. Resolve the real wings with `mempalace_list_wings` and MemPalace's normalize rule (lowercase, `-` and space → `_`). Normalized equality is candidate discovery, never ownership proof: distinct wings that normalize identically are shown separately and confirmed individually.
3. Show every candidate wing (exact names, one row per actual wing) with its drawer count and let the user choose.
4. Enumerate every drawer ID (`mempalace_list_drawers`, paginated), then delete with `mempalace_delete_drawers` in batches of at most 500 IDs for every confirmed wing (wiki wing and diary wing) — never the single-drawer tool. Verify each wing is absent or empty afterwards.
5. Clean up in-scope tunnels and hallways by exact record ID — deleting drawers does not remove these graph records.
6. Then run `project-brain-reset <project-root> --dry-run`, show the output, get explicit user confirmation, and only then run `--confirm`.

If the normal MCP route cannot complete safely, the reset skill explains the failed phase with diagnostics and recommends `/project-brain:hard-reset` — a separate, database-level operation (fail-closed discovery, dry-run plan with a binding plan hash, backup, single-transaction deletion, independent verification, reconnect reminder). It is never launched automatically and never replaces bulk deletion for routine resets. The hard reset supports wing-tagged SQLite palaces only: a default ChromaDB palace is refused because its records can only be removed safely through the Chroma API, so the MCP-based reset is the only supported path there. `mempalace delete-wing` is not a valid CLI command and is never used or recommended.

### Wing names

New brains generate a **timestamped, project-specific wiki wing** `wiki_<project-slug>_<UTC-timestamp>` (e.g. `wiki_ambient_studio_20261026T164600Z`), checked against the actual palace before it is recorded; collisions resolve deterministically (higher timestamp precision, then a numeric suffix). Re-initializing an existing brain never regenerates the recorded name. Legacy bare `wiki_<slug>` and hyphenated `wiki-<slug>` names stay supported and are never renamed automatically.

### Re-creation hazard after reset

MemPalace's own session stop hook can re-mine the `MEMPAL_DIR` directory-derived wing after a clean reset. That wing belongs to MemPalace's project mining, not to the brain — do not treat its reappearance as a failed reset, and do not delete it as part of a brain reset.

## Troubleshooting (the three real failure modes)

### The hook said a brain exists, but `.brain/` reads fail

The SessionStart output is a **launch-time snapshot**. If the brain was deleted after launch, every later read fails. Do not trust the snapshot: verify with a read, and when it fails run `project-brain-init <project-root> "<Project Name>"` again. (Since 0.10.0 the hook text itself says this.)

### MemPalace tools are "missing"

They are probably **deferred**, not absent: check the deferred-tools list in the session. Load the schemas with ONE ToolSearch call (`select:<full name 1>,<full name 2>` + `max_results`), then call `mempalace_status` as the preflight. A tool is genuinely unavailable only when it is in neither the tool list nor the deferred-tools list — never probe with shell/node/pip.

### The run hit the turn cap (or was compacted)

The session can end mid-work. Everything durable lives on disk: the inventory (work list), `.brain/state/session-brief.md`, `.brain/state/repair-rounds` (the repair-limit counter), and the wiki ledger. After compaction, re-orient from those files — `project-brain-wiki <root> status` + `log 5` show what changed — instead of re-reading pages or trusting memory. Update the session brief after each batch; the next session resumes from it.

### More

- `project-brain-reset` not found → resolve `PLUGIN_ROOT` as shown above and use `"$PLUGIN_ROOT/bin/..."`.
- `project-brain-doctor` reports graphify missing → install graphify, then rebuild from project source; never run graphify on `.brain/wiki/`.
- A fresh brain has a low health score → expected: it improves after sources are ingested, pages are compiled from primary sources, the graph is built, and memory is mined.

## Slash commands (plugin skills)

| Command | Purpose |
| --- | --- |
| `/project-brain:brain` | Initialize, ingest, compile, graph, remember, audit, hand off |
| `/project-brain:reset` | Delete MemPalace drawers (MCP) and local brain files |
| `/project-brain:hard-reset` | Database-level wing deletion with dry run, plan hash, backup |
| `/project-brain:doctor` | Health checks and score |
| `/project-brain:lint` | Validate wiki structure and wikilinks |
| `/project-brain:audit` | Review open audit artifacts |
| `/project-brain:update-check` | Installed vs latest versions |

## Development

```bash
cd project-brain
python3 -m pytest -q          # full suite; conftest.py fixtures drive the scripts as subprocesses
```

Dependencies for testing only: `pip install -r requirements-test.txt` (pytest). The scripts themselves are stdlib-only.

## What's new in 0.10.2

- **`status` separates uncommitted work from recent history** — the old "N page(s) changed recently (uncommitted + last 20 snapshots)" looked identical whether anything was pending or not, and a fresh project permanently listed its scaffold pages. Now: an `uncommitted:` section (each page listed individually, hint included only there), a `recently snapshotted:` section (pages of the last few snapshots, window printed in the header), and an explicit "no uncommitted changes" otherwise.
- **SessionStart ledger line splits the counts** — now `wiki ledger: <N> uncommitted; last snapshot <id> '<subject>' (<age>)` (or `no uncommitted changes`), instead of one mixed page count.
- **Clearer `diff` and `restore` messages** — `diff <page>` on a page with a single version says so ("page has one version, created in <hash> — nothing earlier to compare") instead of "no differences", which was indistinguishable from "unchanged"; the restore dry run prints a direction legend ("- lines are in the page now, + lines are in the target") because git's swapped a/ b/ headers read backwards there. Diff directions are unchanged.

## What's new in 0.10.1

- **The auto-snapshot hook no longer blinds the ledger tools** — `status` and the default `diff` read snapshot history (the hook commits every edit, so working-tree-only output was always empty): `status` = uncommitted pages + pages of the last snapshots; `diff <page>` = the page's most recent change (last two versions + uncommitted); `restore <page>` without `--rev` undoes the page's latest change.
- **`restore` pins `--rev` before its automatic snapshot** — `restore --rev HEAD --apply --force` used to resolve `HEAD` after that snapshot and silently restore nothing; the rev is now a pinned full hash, the post-restore file is verified against the target blob, and the dry run works on a dirty page.
- **`status` lists untracked pages individually** — the first pages of a fresh wiki counted as one collapsed directory before.
- **Lint skips code** — wikilink-shaped checks (plain, hybrid, index, decision links) no longer flag `[[ghost]]` inside fenced blocks or inline code spans.

## What's new in 0.10.0

- **Wiki ledger** — local version history for `.brain/wiki` (`project-brain-wiki`), created at init with a baseline snapshot, auto-snapshotted by the PostToolUse hook, with bounded `status/log/history/diff/restore`.
- **Hook fixes** — the SessionStart status now states its launch-time snapshot semantics (the observed failure: it claimed a brain that had been deleted before the first command); wiki edits are silently auto-snapshotted; the ledger line appears in session-start context when a ledger exists.
- **Repair limit that actually stops the loop** — the repair-round counter is keyed per gate (`lint`, `doctor-strict`); the old shared counter was reset by any passing run, so a lint-pass/doctor-fail loop never reached the limit. Over-limit runs print an explicit over-limit message.
- **Numeric version comparison** in `project-brain-update-check` (0.10.0 sorts above 0.9.4).
- **Hybrid `[[target](path)]` wikilinks are now caught** by lint (they used to sail through unflagged), alongside the existing fix hints (`--reindex`, code-span paths, `grep -n` re-citation, `invalid_sources_entry`).
- **Skill restructure** — one Work loop, one Initialize procedure, harness-facts block, ToolSearch contract, graphify skill-first policy, and new references (`deferred-tools.md`, `edit-discipline.md`, `wiki-ledger.md`) within a 24,000-character skill budget.

## License

MIT. See [LICENSE](LICENSE).
