# Wiki Ledger (page history)

Local version history for `.brain/wiki` only: a separate bare git repo at
`.brain/state/wiki.git` whose work tree is the wiki. It has nothing to do with
the project's own git, and `.brain/wiki/` never contains a `.git` (that would
clash with the project's repo). Read this when you need to see what changed,
verify an edit, or undo a bad page edit.

The PostToolUse hook auto-snapshots wiki edits made through Write, Edit, and
MultiEdit (`auto: <tool> <page>`), so the working tree is usually clean a
moment after each of those edits. The hook may silently ignore failures, and
edits made by other means (shell commands, scripts) are never snapshotted:
after such edits, run `status` and, if anything is uncommitted, `snapshot`
by hand. That is why the defaults below answer from snapshot history —
uncommitted-only output would always be empty under the hook.

## Commands

Every subcommand takes `<project-root>` first, run by full path:
`"$PLUGIN_ROOT/bin/project-brain-wiki" <project-root> <subcommand>`.

- `status` — two labeled sections, each capped at 200 lines: `uncommitted:`
  (staged, unstaged, and untracked pages, listed individually — the pending
  work; "no uncommitted changes" when there is none) and `recently
  snapshotted:` (the pages touched by the last few snapshots — the window is
  printed in the section header; omitted when empty). A page appears in one
  section only: uncommitted wins. The `snapshot with:` hint prints only when
  something is uncommitted. "no ledger yet" means git was missing at init or
  history was never created — one `snapshot` creates it.
- `snapshot [-m MSG]` — commit all wiki changes; no-op when clean; creates the
  ledger lazily. Message convention: `work: <what>` for agent batches; the
  hook writes `auto: <tool> <page>` per edit.
- `log [N]` — last N snapshots (default 20, capped at 200).
- `history <page>` — snapshots that touched one page (rename-aware).
- `diff [<page>] [--from REV] [--to REV]` — default with a page: the page's
  most recent change — the diff between its last two snapshot versions plus
  any uncommitted change on top (an untracked page shows as a new file; a
  page with a single version says so — "page has one version, created in
  <hash> — nothing earlier to compare" — instead of an empty diff).
  Default without a page: the last snapshot's changes plus uncommitted ones.
  `--from` alone: that revision vs the working tree; both: revision range
  (explicit revs never use the defaults). Output capped at 200 lines.
- `restore <page> [--rev REV] [--apply]` — dry-run diff by default (read-only,
  allowed on a dirty page); the dry run shows the page's CURRENT working-tree
  content against the target, with a legend marking the direction ("- lines
  are in the page now, + lines are in the target" — the swapped a/ b/ labels
  in the diff headers are a display artifact, not the diff direction).
  Without `--rev`, the target is the version before the page's latest change
  — the undo default. `--apply` restores;
  over uncommitted changes it requires `--force`, which discards them into
  the automatic pre-restore snapshot — the current state is never lost. The
  revision is pinned to a full hash before anything runs (a relative rev like
  `HEAD` cannot drift when the automatic snapshot moves HEAD), the restored
  file is verified against the target blob, and the restore commits
  `restore: <page> (from <rev>)`.

## When (the only four triggers)

1. After compaction or on resume: `status` + `log 5` — that is the wiki's
   change state; do not re-read whole pages to find what changed.
2. Before a large rewrite of a page: `snapshot`.
3. After any edit: `diff <page>` shows the change — cheaper than re-reading
   the page.
4. After a bad edit: `diff <page>`, then `restore <page>` (dry run first;
   `--apply` to commit the restore). Without `--rev` it undoes the page's
   latest change; pass `--rev <rev>` from `history <page>` to go further back.

## Failure paths

- `git` missing → init prints `Ledger: not created`; `status`, `log`, and
  `history` then print `no ledger yet` and exit 0 (they never invoke git),
  while `snapshot` tries to invoke git and exits 127. Other commands that
  need the ledger (diff, restore) report the missing ledger as an error. The
  wiki still works; only history is unavailable.
- `error: ... holds the ledger lock` (exit 75) → another git operation is
  mid-flight; let it finish, then retry. A refused command changes nothing.
- A corrupt ledger → commands report the git error and exit 1; the wiki
  itself is untouched. Recovery: delete `.brain/state/wiki.git` and run
  `snapshot` again — history resets, pages stay.
- `restore --apply` refuses with "has uncommitted changes" → that is the
  data-loss guard: `snapshot` first, or pass `--force` to fold the changes
  into the automatic pre-restore snapshot. (The dry run never refuses — it
  changes nothing.) `restore` errors with "verification failed" if the
  checked-out file ever diverges from the target snapshot — inspect the page
  and the ledger before retrying; nothing was reported as restored.
- `restore <page>` with no earlier version ("only one snapshot version") →
  the page was created by its only touching snapshot, so nothing earlier
  exists and an explicit `--rev` cannot undo the creation. To undo the
  creation, delete the page and snapshot the deletion. (A page that also has
  uncommitted edits can revert them with `--rev <creation rev> --apply
  --force` — that restores the created state without deleting the page.)
- Page arguments are validated at the wiki boundary: absolute paths, `..`,
  and any symlink in the page path are rejected (exit 2) — an in-wiki
  symlink alias would silently operate on its target instead of the named
  page. Spaces and non-ASCII page names work in every subcommand.
