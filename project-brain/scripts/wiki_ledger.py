#!/usr/bin/env python3
"""Wiki ledger: local version history for `.brain/wiki` only.

A safety net so an agent can see what changed, undo a bad edit, and recover
after compaction without re-reading whole pages. It has nothing to do with the
project's own git: the ledger is a SEPARATE bare repository at
`.brain/state/wiki.git` whose work tree is `.brain/wiki`. Never a `.git`
inside the wiki dir (that would clash with the project's repo).

Subcommands (stdlib only, no MCP server):
  status                  two labeled sections: "uncommitted:" (staged,
                          unstaged, untracked pages, individually), then
                          "recently snapshotted:" (pages touched by the last
                          STATUS_RECENT_SNAPSHOTS snapshots); a section is
                          omitted when empty ("no ledger yet" -> exit 0)
  snapshot [-m MSG]       commit all wiki changes; no-op when clean; creates the ledger lazily
  log [N]                 last N snapshots (bounded)
  history <page>          snapshots that touched one page (--follow)
  diff [page] [--from R] [--to R]   default = the most recent change: a page's
                          last two snapshot versions plus any uncommitted change
                          on top (a single-version page says so instead of an
                          empty diff); whole tree: last snapshot's changes plus
                          uncommitted ones (untracked pages show as new files)
  restore <page> [--rev R] [--apply]  default rev = the version before the
                          page's latest change; dry-run diff shows worktree ->
                          target (a legend marks which side is which); --force
                          only needed for --apply on a dirty page;
                          auto-snapshots before applying; the rev is pinned to
                          a full hash before any snapshot can move HEAD

Trust boundary: page arguments are resolved against the wiki root; `..`,
absolute paths, and any symlink in the page path are rejected (an in-wiki
symlink alias would operate on its target, not the named page). Every git call
goes through one argv builder (--git-dir/--work-tree, fixed identity, hooks
disabled, no autocrlf/quotepath surprises) and a sandboxed environment that
strips GIT_* redirector variables and never reads user/global/system git
config. Missing git -> clear message, non-zero exit (explicit CLI use). A
locked or corrupt ledger fails fast with a report; nothing hangs.

ponytail: single-file stdlib module, no daemon, no index cache — the ledger is
re-read per command. Upgrade path: a `verify` subcommand (git fsck) if ledger
corruption is ever observed in practice.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# --- named constants (all tunables live here) --------------------------------
BRAIN_DIR_REL = Path(".brain")
STATE_DIR_REL = BRAIN_DIR_REL / "state"
LEDGER_GIT_DIR_REL = STATE_DIR_REL / "wiki.git"
WIKI_DIR_REL = BRAIN_DIR_REL / "wiki"
GIT_IDENTITY_NAME = "project-brain"
GIT_IDENTITY_EMAIL = "project-brain@localhost"
# Per-git-call timeout: a locked index must fail fast, never hang. Every call
# is bounded again by the caller's deadline when one is set (the hook passes a
# deadline below its hooks.json timeout).
GIT_TIMEOUT_SECS = 10.0
# Hook callers must finish well inside the hooks.json timeout (10 s), so they
# pass a tighter total deadline covering init+add+commit worst case.
HOOK_LEDGER_DEADLINE_SECS = 6.0
# Output bounds. Every list this script prints is truncated at a named bound.
MAX_STATUS_PAGES = 200
DEFAULT_LOG_COUNT = 20
MAX_LOG_ENTRIES = 200
MAX_HISTORY_ENTRIES = 100
MAX_DIFF_LINES = 200
TRUNCATION_NOTE = "… (output truncated at {bound} lines — narrow the query)"
# status lists pages touched by this many most-recent snapshots.
# ponytail: 5 = the last handful of edits (the auto-snapshot hook commits
# roughly one snapshot per edit), matching the post-compaction pairing
# `status` + `log 5`; deeper history is `log`'s job, and a wider window made
# a fresh project list its scaffold pages as "changed" long after the fact.
# Upgrade path: raise it if a real session needs a wider "what changed
# lately" window; each section stays bounded by MAX_STATUS_PAGES.
STATUS_RECENT_SNAPSHOTS = 5
# Snapshots whose pages count for a page's "most recent change" (diff default)
# and the restore default rev: exactly the last two versions of that page.
PAGE_RECENT_VERSION_COUNT = 2
# Subject bound inside the one-line SessionStart ledger line.
LEDGER_LINE_SUBJECT_MAX_CHARS = 80
# Exit codes (explicit CLI use).
EXIT_OK = 0
EXIT_ERROR = 1  # corrupt or unusable ledger, restore refused, generic failure
EXIT_USAGE = 2  # bad arguments / unresolvable rev / invalid page path
EXIT_BUSY = 75  # another git operation holds the ledger (fail fast, report)
EXIT_GIT_MISSING = 127
# git >= 2.32 understands GIT_CONFIG_GLOBAL/GIT_CONFIG_SYSTEM; older git falls
# back to a null HOME (git reads global config from $HOME/.gitconfig).
GIT_CONFIG_GLOBAL_SINCE = (2, 32)
# GIT_* variables that redirect git at other repos/objects/config; stripped so
# the ledger always addresses exactly its own git dir. Also stripped: author/
# committer env overrides (they would beat our -c identity) and config-fragment
# variables (GIT_CONFIG_KEY_n/GIT_CONFIG_VALUE_n are stripped by prefix).
GIT_ENV_STRIP = (
    "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR", "GIT_NAMESPACE",
    "GIT_CEILING_DIRECTORIES", "GIT_CONFIG", "GIT_CONFIG_COUNT",
    "GIT_CONFIG_SYSTEM", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM",
    "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME",
    "GIT_COMMITTER_EMAIL", "GIT_TEMPLATE_DIR",
)
GIT_ENV_STRIP_PREFIXES = ("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")
GIT_ENV_NULL_GLOBAL = "GIT_CONFIG_GLOBAL"
GIT_ENV_NULL_SYSTEM = "GIT_CONFIG_SYSTEM"
GIT_ENV_NOSYSTEM = "GIT_CONFIG_NOSYSTEM"
NULL_GLOBAL_VALUE = "/dev/null"
# Separator bytes for -z / record parsing of git output (spaces and non-ASCII
# page names must survive parsing untouched).
NUL = "\0"
UNIT_SEP = "\x1f"
RECORD_SEP = "\x1e"
LOG_FORMAT = UNIT_SEP.join(("%H", "%h", "%at", "%s")) + RECORD_SEP
AUTO_SNAPSHOT_PREFIX = "auto"
SNAPSHOT_DEFAULT_PREFIX = "snapshot"
RESTORE_MESSAGE_PREFIX = "restore"
BASELINE_SNAPSHOT_MESSAGE = "baseline: brain scaffold"
PAGE_SEP_NOTE = "--"
_NO_COMMIT_YET_MARKERS = ("does not have any commits yet", "bad revision 'HEAD'",
                          "unknown revision")

_supports_null_config_env: bool | None = None  # resolved once per process


class LedgerError(Exception):
    """Ledger failure with a message meant for the user."""


class GitMissing(LedgerError):
    """The git executable is not available."""


class LedgerBusy(LedgerError):
    """Another git operation holds the ledger lock (index.lock), or a git call
    exceeded its timeout. Fail fast; never wait it out."""


class ArgumentError(LedgerError):
    """A bad page argument or revision — a usage error (exit EXIT_USAGE)."""


# --- environment sandbox ------------------------------------------------------

def _resolve_supports_null_config_env() -> bool:
    """One `git --version` probe; parse failure means 'do not rely on the new
    env vars' (the HOME fallback is safe on every git)."""
    exe = shutil.which("git")
    if not exe:
        return False
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True,
                             timeout=GIT_TIMEOUT_SECS).stdout
        match = re.search(r"git version (\d+)\.(\d+)", out)
        if not match:
            return False
        return (int(match.group(1)), int(match.group(2))) >= GIT_CONFIG_GLOBAL_SINCE
    except (OSError, subprocess.SubprocessError):
        return False


def build_git_env() -> dict:
    """Environment for every ledger git call: strip GIT_* redirectors and
    identity overrides, disable system/global config, nothing else touched."""
    global _supports_null_config_env
    env = {k: v for k, v in os.environ.items() if k not in GIT_ENV_STRIP
           and not k.startswith(GIT_ENV_STRIP_PREFIXES)}
    env[GIT_ENV_NOSYSTEM] = "1"
    if _supports_null_config_env is None:
        _supports_null_config_env = _resolve_supports_null_config_env()
    if _supports_null_config_env:
        env[GIT_ENV_NULL_GLOBAL] = NULL_GLOBAL_VALUE
        env[GIT_ENV_NULL_SYSTEM] = NULL_GLOBAL_VALUE
    else:
        # Older git: a null HOME points global config lookup at /dev/null.
        env["HOME"] = NULL_GLOBAL_VALUE
    return env


# --- one argv builder for every git call --------------------------------------

def git_argv(git_dir: Path, work_tree: Path, *args: str) -> list[str]:
    """The ONE argv builder: git dir/work tree, fixed identity, hooks and
    whitespace surprises disabled, then the caller's arguments."""
    exe = shutil.which("git")
    if not exe:
        raise GitMissing(
            "git is required for the wiki ledger (project-brain-wiki): "
            "install git and re-run")
    return [
        exe,
        f"--git-dir={git_dir}",
        f"--work-tree={work_tree}",
        "-c", f"user.name={GIT_IDENTITY_NAME}",
        "-c", f"user.email={GIT_IDENTITY_EMAIL}",
        "-c", "commit.gpgsign=false",
        "-c", "core.autocrlf=false",
        "-c", "core.quotepath=false",
        "-c", "core.hooksPath=/dev/null",
        *args,
    ]


# --- path trust boundary ------------------------------------------------------

def resolve_page_path(wiki: Path, page_arg: str) -> Path:
    """Resolve a page argument against the wiki root; reject anything that
    escapes it (absolute paths, `..`) and any symlink in the path (an in-wiki
    alias would operate on its target instead of the named page). Returns the
    absolute path; git arguments use the wiki-relative form separately."""
    if not page_arg or not page_arg.strip():
        raise ArgumentError("empty page argument")
    candidate = Path(page_arg)
    if candidate.is_absolute() or page_arg.startswith(("/", "~")):
        raise ArgumentError(f"page argument must be wiki-relative, got {page_arg!r}")
    parts = candidate.parts
    if any(part == ".." for part in parts):
        raise ArgumentError(f"page argument must not contain '..': {page_arg!r}")
    resolved = (wiki / candidate).resolve()
    wiki_resolved = wiki.resolve()
    if resolved != wiki_resolved and wiki_resolved not in resolved.parents:
        raise ArgumentError(f"page argument escapes the wiki: {page_arg!r}")
    # Reject symlink aliases: an in-wiki symlink (page or directory) would
    # resolve to its target, so history/diff/restore would operate on the
    # target through the alias instead of the named page.
    probe = wiki
    for part in candidate.parts:
        probe = probe / part
        if probe.is_symlink():
            raise ArgumentError(f"page argument crosses a symlink: {page_arg!r}")
    return resolved


def page_rel_for_git(wiki: Path, resolved: Path) -> str:
    """Wiki-relative path with forward slashes (git's separator)."""
    return resolved.relative_to(wiki.resolve()).as_posix()


def literal_spec(rel: str) -> str:
    """Pathspec for one page: the (literal) magic prefix stops git from
    reading *, ? and [] in a page name as wildcards (which would match a
    DIFFERENT page's history, diff or restore)."""
    return f":(literal){rel}"


# --- ledger core ----------------------------------------------------------------

class WikiLedger:
    """All git access for one project's wiki ledger."""

    def __init__(self, root: Path, deadline: float | None = None):
        self.root = root.expanduser().resolve()
        self.git_dir = self.root / LEDGER_GIT_DIR_REL
        self.wiki = self.root / WIKI_DIR_REL
        self.deadline = deadline  # monotonic deadline or None

    # -- plumbing ------------------------------------------------------------
    def _remaining(self) -> float:
        if self.deadline is None:
            return GIT_TIMEOUT_SECS
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise LedgerBusy("wiki ledger time budget exhausted (another "
                             "operation or a slow disk); try again")
        return remaining

    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        argv = git_argv(self.git_dir, self.wiki, *args)
        try:
            # Explicit UTF-8: the locale encoding can be ASCII, and page names
            # are user-controlled (non-ASCII must survive -z parsing).
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace",
                                  timeout=self._remaining(), env=build_git_env(),
                                  cwd=str(self.root))
        except subprocess.TimeoutExpired as exc:
            raise LedgerBusy(f"git {args[0]} timed out after {GIT_TIMEOUT_SECS:g}s — "
                             "the ledger may be locked; retry after it finishes") from exc
        except OSError as exc:
            raise LedgerError(f"git {args[0]} failed to run: {exc}") from exc
        if check and proc.returncode != 0:
            stderr = (proc.stderr or proc.stdout or "").strip().splitlines()
            detail = stderr[0] if stderr else f"exit {proc.returncode}"
            if "index.lock" in detail or "index.lock" in (proc.stderr or ""):
                raise LedgerBusy("another git operation holds the ledger lock "
                                 f"({self.git_dir}/index.lock); retry after it finishes")
            raise LedgerError(f"git {args[0]} failed: {detail}")
        return proc

    def exists(self) -> bool:
        """A ledger exists when its HEAD file is present (bare repo marker)."""
        return (self.git_dir / "HEAD").is_file()

    def ensure(self) -> None:
        """Create the bare ledger lazily (idempotent)."""
        if self.exists():
            return
        self.git_dir.parent.mkdir(parents=True, exist_ok=True)
        exe = shutil.which("git")
        if not exe:
            raise GitMissing(
                "git is required for the wiki ledger (project-brain-wiki): "
                "install git and re-run")
        try:
            subprocess.run(
                [exe, "-c", "init.defaultbranch=main", "init", "--bare", "-q",
                 str(self.git_dir)],
                capture_output=True, text=True, timeout=self._remaining(),
                env=build_git_env(), check=True,
            )
        except subprocess.SubprocessError as exc:
            raise LedgerError(f"could not create the wiki ledger at "
                              f"{LEDGER_GIT_DIR_REL}: {exc}") from exc

    # -- queries -------------------------------------------------------------
    def changed_pages(self) -> list[str]:
        """Wiki-relative page paths with any change vs the last snapshot
        (staged, unstaged, untracked — files individually, never a collapsed
        directory: the first pages of a fresh wiki must each be named).
        Parsed with -z: safe for spaces and non-ASCII names."""
        proc = self._run("status", "--porcelain=v1", "-z", "--untracked-files=all",
                         "--", ".")
        pages: list[str] = []
        tokens = proc.stdout.split(NUL)
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if not token:
                i += 1
                continue
            xy, path = token[:2], token[3:]
            # Rename records carry the original path as a second NUL field.
            if xy and xy[0] in ("R", "C"):
                i += 2
            else:
                i += 1
            # -z output is raw: git never quotes or pads paths here, so strip
            # nothing — a root-level filename may legitimately start with a
            # space or contain quotes.
            if path:
                pages.append(path)
        return sorted(set(pages))

    def _rev_exists(self, rev: str) -> bool:
        proc = self._run("rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}",
                         check=False)
        return proc.returncode == 0

    def untracked_pages(self) -> list[str]:
        """Wiki-relative untracked page paths, individually (a fresh wiki's
        first pages live in one new directory each)."""
        proc = self._run("ls-files", "-o", "--exclude-standard", "-z", "--", ".")
        return sorted(p for p in proc.stdout.split(NUL) if p)

    def touching_commits(self, rel: str, count: int) -> list[str]:
        """Full hashes of the `count` most recent snapshots that touched rel
        (rename-aware, like history). The path is a literal pathspec: page
        names containing *, ? or [] must never be read as wildcards, or the
        revision selection could pick commits of a DIFFERENT page."""
        proc = self._run("log", "--follow", f"--max-count={count}", "--format=%H",
                         "--", literal_spec(rel))
        return [h for h in proc.stdout.split() if h]

    def recent_snapshot_pages(self) -> list[str]:
        """Deduped page names touched by the STATUS_RECENT_SNAPSHOTS most
        recent snapshots (--root so the baseline snapshot counts too). Callers
        that also list uncommitted pages exclude them, so a page is never
        printed in both sections."""
        if not self.has_snapshots():
            return []
        proc = self._run("log", f"--max-count={STATUS_RECENT_SNAPSHOTS}",
                         "--format=%H")
        pages: set[str] = set()
        for commit in proc.stdout.split():
            touched = self._run("diff-tree", "--no-commit-id", "--name-only",
                                "-r", "--root", "-z", commit, check=False)
            pages.update(p for p in touched.stdout.split(NUL) if p)
        return sorted(pages)

    def _page_in_rev(self, page_rel: str, rev: str) -> bool:
        proc = self._run("cat-file", "-e", f"{rev}:{page_rel}", check=False)
        return proc.returncode == 0

    def _pre_rename_source(self, rel: str, rev: str) -> str:
        """The filename under which rev carries rel's content.

        A revision can predate a rename: `cat-file rev:rel` fails even though
        the page's history (--follow) reaches it under an earlier name. The
        follow-log lists every name the page has had; the most recent one
        that exists in rev is the restore source. Empty when none resolves.
        The listing is parsed from -z output split on NUL without any
        stripping or quoting: a historical name with leading/trailing spaces
        or embedded quotes must survive exactly, or the restore would look
        up (or verify) a different page than the one the snapshot carries."""
        proc = self._run("log", "--follow", "--format=", "--name-only", "-z",
                         "--", literal_spec(rel))
        names: dict[str, None] = {}
        for name in proc.stdout.split(NUL):
            if name:
                names.setdefault(name, None)
        for name in names:
            if name != rel and self._page_in_rev(name, rev):
                return name
        return ""

    def has_snapshots(self) -> bool:
        return self._run("rev-parse", "--verify", "--quiet", "HEAD",
                         check=False).returncode == 0

    # -- commands ------------------------------------------------------------
    def init_ledger(self) -> bool:
        """Create the ledger if missing; True when a ledger now exists."""
        self.ensure()
        return self.exists()

    def snapshot(self, message: str | None = None) -> tuple[bool, str, str]:
        """Commit all wiki changes. Returns (committed, short_hash, detail).
        No-op when clean; creates the ledger lazily."""
        self.ensure()
        self._run("add", "-A", "--", ".")
        clean = self._run("diff", "--cached", "--quiet", check=False)
        if clean.returncode == 0:
            return False, "", "nothing to snapshot"
        count = len({p for p in self._run("diff", "--cached", "--name-only", "-z",
                                          "--", ".").stdout.split(NUL) if p})
        if not message:
            message = f"{SNAPSHOT_DEFAULT_PREFIX}: {count} page(s) changed"
        self._run("commit", "-m", message)
        short = self._run("rev-parse", "--short", "HEAD").stdout.strip()
        return True, short, message

    def log(self, count: int) -> list[tuple[str, str, str, str]]:
        """Last `count` snapshots as (full_hash, short_hash, epoch, subject)."""
        count = max(1, min(count, MAX_LOG_ENTRIES))
        if not self.exists() or not self.has_snapshots():
            return []
        proc = self._run("log", f"--max-count={count}", f"--format={LOG_FORMAT}")
        entries = []
        for record in proc.stdout.split(RECORD_SEP):
            record = record.lstrip("\n")
            if not record.strip():
                continue
            fields = record.split(UNIT_SEP)
            if len(fields) == 4:
                entries.append(tuple(fields))  # type: ignore[arg-type]
        return entries[:MAX_LOG_ENTRIES]

    def history(self, page_arg: str, count: int) -> list[tuple[str, str, str, str]]:
        """Snapshots that touched one page (--follow rename detection)."""
        page = resolve_page_path(self.wiki, page_arg)
        rel = page_rel_for_git(self.wiki, page)
        count = max(1, min(count, MAX_HISTORY_ENTRIES))
        if not self.exists() or not self.has_snapshots():
            return []
        proc = self._run("log", "--follow", f"--max-count={count}",
                         f"--format={LOG_FORMAT}", "--", literal_spec(rel))
        entries = []
        for record in proc.stdout.split(RECORD_SEP):
            record = record.lstrip("\n")
            if not record.strip():
                continue
            fields = record.split(UNIT_SEP)
            if len(fields) == 4:
                entries.append(tuple(fields))  # type: ignore[arg-type]
        return entries[:MAX_HISTORY_ENTRIES]

    def diff(self, page_arg: str | None, from_rev: str | None,
             to_rev: str | None) -> list[str]:
        """Diff lines, bounded. Explicit --from/--to keep git semantics; the
        default shows the most recent change (see the module docstring) —
        working-tree-vs-HEAD alone is empty whenever the hook commits each
        edit, which neutered `diff <page>` in 0.10.0."""
        # Usage validation before state errors: a bad page argument is always
        # exit 2, regardless of ledger state.
        page_rel = None
        if page_arg:
            page = resolve_page_path(self.wiki, page_arg)
            page_rel = page_rel_for_git(self.wiki, page)
        if not self.exists():
            raise LedgerError("no ledger yet — run `project-brain-wiki snapshot` first")
        if from_rev or to_rev:
            lines = self._diff_revs(page_rel, from_rev, to_rev)
        elif page_rel:
            lines = self._diff_page_recent(page_rel)
        else:
            lines = self._diff_tree_recent()
        if len(lines) > MAX_DIFF_LINES:
            lines = lines[:MAX_DIFF_LINES] + [TRUNCATION_NOTE.format(bound=MAX_DIFF_LINES)]
        return lines

    def _diff_lines(self, *args: str) -> list[str]:
        proc = self._run(*args, check=False)
        if proc.returncode not in (0, 1):
            raise LedgerError(f"git diff failed: {(proc.stderr or '').strip().splitlines()[0]}")
        return proc.stdout.splitlines()

    def _diff_revs(self, page_rel: str | None, from_rev: str | None,
                   to_rev: str | None) -> list[str]:
        """Explicit --from/--to semantics (unchanged)."""
        args = ["diff", "--no-color", "--no-ext-diff"]
        if from_rev and to_rev:
            self._resolve_rev(from_rev)
            self._resolve_rev(to_rev)
            args += [from_rev, to_rev]
        elif from_rev:
            self._resolve_rev(from_rev)
            args.append(from_rev)  # FROM vs working tree
        elif to_rev:
            self._resolve_rev(to_rev)
            self._require_head()
            args += ["HEAD", to_rev]
        else:
            self._require_head()
            args.append("HEAD")
        args.append("--")
        if page_rel:
            args.append(literal_spec(page_rel))
        return self._diff_lines(*args)

    def _diff_page_recent(self, page_rel: str) -> list[str]:
        """A page's most recent change: the diff between its last two
        snapshot versions plus any uncommitted change on top. An untracked
        page (never snapshotted) shows as a new file; a page with a single
        version says so — an empty result would print "no differences",
        indistinguishable from "unchanged vs an explicit rev"."""
        untracked = self._run("ls-files", "-o", "--exclude-standard", "-z",
                              "--", literal_spec(page_rel)).stdout
        if any(p for p in untracked.split(NUL) if p):
            return self._new_file_diff(page_rel)
        lines: list[str] = []
        commits = self.touching_commits(page_rel, PAGE_RECENT_VERSION_COUNT)
        if len(commits) == PAGE_RECENT_VERSION_COUNT:
            lines += self._diff_lines("diff", "--no-color", "--no-ext-diff",
                                      commits[1], commits[0], "--",
                                      literal_spec(page_rel))
        lines += self._diff_lines("diff", "--no-color", "--no-ext-diff",
                                  "HEAD", "--", literal_spec(page_rel))
        if not lines and commits:
            return [f"page has one version, created in "
                    f"{self._short_rev(commits[0])} — nothing earlier to compare"]
        return lines

    def _diff_tree_recent(self) -> list[str]:
        """Whole tree, no page: the last snapshot's changes plus uncommitted
        ones (untracked pages show as new files)."""
        lines: list[str] = []
        if self.has_snapshots():
            if self._rev_exists("HEAD~1"):
                lines += self._diff_lines("diff", "--no-color", "--no-ext-diff",
                                          "HEAD~1", "HEAD", "--", ".")
            lines += self._diff_lines("diff", "--no-color", "--no-ext-diff",
                                      "HEAD", "--", ".")
        for page in self.untracked_pages()[:MAX_STATUS_PAGES]:
            lines += self._new_file_diff(page)
        return lines

    def _new_file_diff(self, rel: str) -> list[str]:
        """Diff of a page git does not track yet: /dev/null vs the file.
        Paths are given relative to the project root (the subprocess cwd);
        --no-index ignores the ledger repo and always exits 1 on differences."""
        proc = self._run("diff", "--no-index", "--no-color", "--no-ext-diff",
                         "--", "/dev/null", f"{WIKI_DIR_REL.as_posix()}/{rel}",
                         check=False)
        return proc.stdout.splitlines()

    def _require_head(self) -> None:
        if not self.has_snapshots():
            raise LedgerError("no snapshots yet — run `project-brain-wiki snapshot` first")

    def _pre_rename_preview(self, rel: str, full: str, pre_rename: str) -> list[str]:
        """Dry-run preview for a restore whose rev predates a rename.

        Compares the CURRENT rel content with the target pre_rename blob, so
        the preview shows exactly what --apply will replace (and with what):
        diffing the pre-rename spec against the worktree would compare the
        target blob with the ABSENT pre-rename path (git's -R swaps the two
        diff sides; it does not substitute the current filename) and show an
        addition that hides the replaced content. The blob is copied to a
        temp file and diffed --no-index; temp and worktree paths are rewritten
        back to rel so the output reads like the ordinary restore preview.
        """
        try:
            proc = subprocess.run(
                git_argv(self.git_dir, self.wiki, "cat-file", "blob", f"{full}:{pre_rename}"),
                capture_output=True, timeout=self._remaining(), env=build_git_env(),
                cwd=str(self.root))
        except subprocess.TimeoutExpired as exc:
            raise LedgerBusy(f"git cat-file timed out after {GIT_TIMEOUT_SECS:g}s — "
                             "the ledger may be locked; retry after it finishes") from exc
        except OSError as exc:
            raise LedgerError(f"git cat-file failed to run: {exc}") from exc
        if proc.returncode != 0:
            raise LedgerError(
                f"could not read the target content {full}:{pre_rename}: "
                f"{proc.stderr.decode('utf-8', errors='replace').strip()}")
        current_path = self.wiki / rel
        from_side = str(current_path) if current_path.is_file() else "/dev/null"
        fd, tmp_name = tempfile.mkstemp(prefix="wiki-restore-target-")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(proc.stdout)
            diff_proc = self._run("diff", "--no-index", "--no-color", "--no-ext-diff",
                                  "--", from_side, tmp_name, check=False)
        finally:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
        lines: list[str] = []
        for line in diff_proc.stdout.splitlines():
            if tmp_name in line:
                line = line.replace(tmp_name, rel)
            if str(current_path) in line:
                line = line.replace(str(current_path), rel)
            lines.append(line)
        return lines

    def _resolve_rev(self, rev: str) -> str:
        """Validate a revision and pin it to a full commit hash. Restores must
        resolve BEFORE the automatic pre-restore snapshot: a relative rev
        (HEAD) would otherwise drift onto the new snapshot and silently
        restore nothing (0.10.0 D2)."""
        # ~ and ^ suffixes (REV~1) are valid git revisions and must pass.
        if not re.fullmatch(r"[0-9A-Za-z._/\-~^]{1,64}", rev):
            raise ArgumentError(f"invalid revision: {rev!r}")
        proc = self._run("rev-parse", "--verify", f"{rev}^{{commit}}", check=False)
        if proc.returncode != 0:
            raise LedgerError(f"unknown revision {rev!r} — pick one from `project-brain-wiki log`")
        return proc.stdout.strip()

    def _short_rev(self, full_hash: str) -> str:
        return self._run("rev-parse", "--short", full_hash).stdout.strip()

    def _default_restore_rev(self, rel: str) -> str:
        """Rev for `restore <page>` with no --rev: the version before the
        page's latest change (parent of the newest snapshot that touched it;
        its page content equals the second-most-recent touching snapshot's)."""
        commits = self.touching_commits(rel, PAGE_RECENT_VERSION_COUNT)
        if not commits:
            raise LedgerError(f"{rel} has no snapshot history — nothing to "
                              "restore; snapshot it first")
        if len(commits) < PAGE_RECENT_VERSION_COUNT:
            raise LedgerError(f"{rel} has only one snapshot version and no "
                              "earlier version to restore — an explicit --rev "
                              "cannot undo the page's creation; delete the "
                              "page and snapshot the deletion instead")
        return f"{commits[0]}^"

    def restore(self, page_arg: str, rev: str | None, apply: bool = False,
                force: bool = False) -> tuple[list[str], str, str]:
        """Dry-run diff (default) or restore a page from a snapshot.

        rev None = the version before the page's latest change (the undo
        default). The rev is pinned to a full hash before anything runs, so
        the automatic pre-restore snapshot cannot shift a relative rev. The
        dry run is read-only and diffs the page's CURRENT working-tree
        content to the target; --force is required only to --apply over
        uncommitted changes (an automatic snapshot commits them first, so
        the current state is never lost). Never writes outside the wiki.
        The page path is passed to git as a literal pathspec, so a name
        containing *, ? or [] targets exactly that page. When the selected
        revision predates a rename, the content is retrieved under the
        page's pre-rename name and written to the current name.
        Returns (dry-run lines, post-restore snapshot id, shown rev)."""
        if not self.exists():
            raise LedgerError("no ledger yet — run `project-brain-wiki snapshot` first")
        # Usage validation before state errors (same order as diff).
        page = resolve_page_path(self.wiki, page_arg)
        rel = page_rel_for_git(self.wiki, page)
        self._require_head()
        if rev is None:
            rev = self._default_restore_rev(rel)
        full = self._resolve_rev(rev)
        short = self._short_rev(full)
        spec = literal_spec(rel)
        pre_rename = ""
        if not self._page_in_rev(rel, full):
            pre_rename = self._pre_rename_source(rel, full)
            if not pre_rename:
                raise LedgerError(f"{rel} does not exist in {rev} — "
                                  "pick a revision from `project-brain-wiki history <page>`")
            if (self.wiki / pre_rename).exists():
                raise LedgerError(
                    f"{rev} carries {rel} under its pre-rename name {pre_rename!r}, but a file "
                    f"with that name exists in the wiki now; restore {pre_rename!r} manually "
                    "(snapshot, copy its content from `history`) and retry")
            spec = literal_spec(pre_rename)
        dirty = self._run("status", "--porcelain=v1", "-z", "--",
                          literal_spec(rel)).stdout.strip() != ""
        if dirty and apply and not force:
            raise LedgerError(
                f"{rel} has uncommitted changes — snapshot them first "
                "(`project-brain-wiki snapshot`) or pass --force to discard "
                "them into an automatic snapshot")
        # Dry run shows worktree -> target, i.e. exactly what --apply would
        # write. For a pre-rename restore the target lives under the
        # pre-rename name, so the preview is built from the current rel
        # content vs the target blob instead (see _pre_rename_preview).
        if pre_rename:
            lines = self._pre_rename_preview(rel, full, pre_rename)
        else:
            proc = self._run("diff", "--no-color", "--no-ext-diff", "-R", full,
                             "--", spec, check=False)
            lines = proc.stdout.splitlines()
        if len(lines) > MAX_DIFF_LINES:
            lines = lines[:MAX_DIFF_LINES] + [TRUNCATION_NOTE.format(bound=MAX_DIFF_LINES)]
        if pre_rename:
            lines.append(f"note: {rev} predates the rename of {pre_rename} to {rel} — "
                         "--apply writes that earlier content to the current page name")
        if not apply:
            return lines, "", short
        # Data-loss guard: commit the current state before overwriting it.
        committed, _short, detail = self.snapshot()
        if dirty and not committed:
            raise LedgerError("could not snapshot the current state before "
                              f"restoring ({detail}); nothing was changed")
        self._run("checkout", full, "--", spec)
        if pre_rename:
            # The checked-out content landed on the pre-rename path; move it
            # onto the current page name and verify by blob hash (rev:rel
            # does not exist for a pre-rename revision).
            os.replace(self.wiki / pre_rename, self.wiki / rel)
            target = self._run("rev-parse", f"{full}:{pre_rename}").stdout.strip()
            actual = self._run("hash-object", str(self.wiki / rel)).stdout.strip()
            if not target or actual != target:
                raise LedgerError(f"restore verification failed: {rel} does not "
                                  f"match {short} after checkout; inspect the page "
                                  "and the ledger before retrying")
        elif self._run("diff", "--quiet", full, "--", spec, check=False).returncode != 0:
            raise LedgerError(f"restore verification failed: {rel} does not "
                              f"match {short} after checkout; inspect the page "
                              "and the ledger before retrying")
        _ok, new_short, _msg = self.snapshot(f"{RESTORE_MESSAGE_PREFIX}: {rel} "
                                             f"(from {short})")
        return lines, new_short, short


# --- project-level helpers (used by scaffold and the hooks) ---------------------

def note_if_outer_repo_could_track_ledger(root: Path) -> str | None:
    """One-line note when the project's own repo would track .brain/state/
    (the ledger is local version history and embeds a git dir; tracking it in
    the outer repo adds an embedded-repo gitlink and churn). Never edits
    .gitignore."""
    outer = root / ".git"
    if not outer.exists():
        return None
    if not shutil.which("git"):
        return None
    proc = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", "--",
                           str(LEDGER_GIT_DIR_REL)], capture_output=True)
    if proc.returncode == 1:  # 1 = not ignored; 0 = ignored; other = no repo -> silent
        return ("note: your project repo does not exclude .brain/state/ — add "
                "'.brain/state/' to .gitignore to keep the wiki ledger local "
                "(left untouched)")
    return None


def ledger_status_line(root: Path) -> str | None:
    """One bounded line for SessionStart: the uncommitted page count (the
    pending work) and the last snapshot (id, subject, age) reported
    separately. None without a ledger or on any failure (a corrupt or locked
    ledger must never break a session)."""
    try:
        ledger = WikiLedger(root, deadline=time.monotonic() + HOOK_LEDGER_DEADLINE_SECS)
        if not ledger.exists():
            return None
        uncommitted = len(ledger.changed_pages())
        entries = ledger.log(1)
        if not entries:
            return f"wiki ledger: {uncommitted} uncommitted; no snapshots yet"
        _full, short, epoch, subject = entries[0]
        age = max(0, int(time.time() - int(epoch)))
        subject = subject[:LEDGER_LINE_SUBJECT_MAX_CHARS]
        pending = f"{uncommitted} uncommitted" if uncommitted else "no uncommitted changes"
        return (f"wiki ledger: {pending}; "
                f"last snapshot {short} '{subject}' ({human_age(age)} ago)")
    except Exception:
        return None


def human_age(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


# --- CLI ------------------------------------------------------------------------

def _print_bounded(lines: list[str], bound: int) -> None:
    if len(lines) > bound:
        lines = lines[:bound] + [TRUNCATION_NOTE.format(bound=bound)]
    for line in lines:
        print(line)


def _ledger_from_args(args: argparse.Namespace) -> WikiLedger:
    return WikiLedger(Path(args.project_root).expanduser())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="project-brain-wiki",
        description="Local version history for .brain/wiki (separate git dir "
                    ".brain/state/wiki.git; nothing to do with the project's own git).")
    parser.add_argument("project_root", help="project root (the dir containing .brain/)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status",
                   help="uncommitted pages, then recently snapshotted pages")

    p = sub.add_parser("snapshot", help="commit all wiki changes (no-op when clean)")
    p.add_argument("-m", "--message", default=None, help="snapshot message")

    p = sub.add_parser("log", help="last N snapshots (default 20, bounded)")
    p.add_argument("count", nargs="?", type=int, default=DEFAULT_LOG_COUNT)

    p = sub.add_parser("history", help="snapshots that touched one page")
    p.add_argument("page")
    p.add_argument("count", nargs="?", type=int, default=MAX_HISTORY_ENTRIES)

    p = sub.add_parser("diff", help="page or whole-tree diff (default: vs last snapshot)")
    p.add_argument("page", nargs="?", default=None)
    p.add_argument("--from", dest="from_rev", default=None, metavar="REV")
    p.add_argument("--to", dest="to_rev", default=None, metavar="REV")

    p = sub.add_parser("restore", help="restore a page from a snapshot (dry run by default)")
    p.add_argument("page")
    p.add_argument("--rev", default=None, metavar="REV",
                   help="revision to restore (default: the version before the "
                        "page's latest change)")
    p.add_argument("--apply", action="store_true", help="actually restore (default: dry run)")
    p.add_argument("--force", action="store_true",
                   help="with --apply: discard uncommitted changes into the "
                        "automatic pre-restore snapshot")
    return parser


def cmd_status(ledger: WikiLedger) -> int:
    if not ledger.exists():
        print("no ledger yet")
        return EXIT_OK
    uncommitted = ledger.changed_pages()
    if uncommitted:
        print("uncommitted:")
        _print_bounded([f"  {PAGE_SEP_NOTE} {p}" for p in uncommitted],
                       MAX_STATUS_PAGES)
    else:
        print("no uncommitted changes")
    snapshotted = [p for p in ledger.recent_snapshot_pages()
                   if p not in set(uncommitted)]
    if snapshotted:
        print(f"recently snapshotted (last {STATUS_RECENT_SNAPSHOTS} snapshots):")
        _print_bounded([f"  {PAGE_SEP_NOTE} {p}" for p in snapshotted],
                       MAX_STATUS_PAGES)
    if uncommitted:
        print("snapshot with: project-brain-wiki <root> snapshot")
    return EXIT_OK


def cmd_snapshot(ledger: WikiLedger, message: str | None) -> int:
    committed, short, detail = ledger.snapshot(message)
    if not committed:
        print(detail)
        return EXIT_OK
    print(f"snapshot {short}: {detail}")
    return EXIT_OK


def cmd_log(ledger: WikiLedger, count: int) -> int:
    if not ledger.exists():
        print("no ledger yet")
        return EXIT_OK
    entries = ledger.log(count)
    if not entries:
        print("no snapshots yet")
        return EXIT_OK
    for _full, short, epoch, subject in entries:
        print(f"{short}  {human_age(max(0, int(time.time() - int(epoch))))} ago  {subject}")
    return EXIT_OK


def cmd_history(ledger: WikiLedger, page: str, count: int) -> int:
    if not ledger.exists():
        print("no ledger yet")
        return EXIT_OK
    entries = ledger.history(page, count)
    if not entries:
        print(f"no snapshots touch {page}")
        return EXIT_OK
    for _full, short, epoch, subject in entries:
        print(f"{short}  {human_age(max(0, int(time.time() - int(epoch))))} ago  {subject}")
    return EXIT_OK


def cmd_diff(ledger: WikiLedger, page: str | None, from_rev: str | None,
             to_rev: str | None) -> int:
    lines = ledger.diff(page, from_rev, to_rev)
    if not lines:
        print("no differences")
        return EXIT_OK
    _print_bounded(lines, MAX_DIFF_LINES)
    return EXIT_OK


def cmd_restore(ledger: WikiLedger, page: str, rev: str | None, apply: bool,
                force: bool) -> int:
    lines, new_short, rev_shown = ledger.restore(page, rev, apply=apply, force=force)
    if not apply:
        print(f"dry run: restoring {page} from {rev_shown} would change:")
        if lines:
            # git's -R swap makes its a/ b/ headers read backwards here; the
            # legend states the direction instead of rewriting git's output.
            print("  (- lines are in the page now, + lines are in the target)")
        else:
            print("  (nothing — the page already matches this revision)")
        _print_bounded(lines, MAX_DIFF_LINES)
        print("run with --apply to restore")
        return EXIT_OK
    print(f"restored {page} from {rev_shown}" + (f" — snapshot {new_short}" if new_short else ""))
    return EXIT_OK


def main(argv: list[str]) -> int:
    # Page names can be non-ASCII; never crash printing them under a C locale.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv[1:])
    root = Path(args.project_root).expanduser()
    if not (root / BRAIN_DIR_REL).is_dir():
        print(f"no .brain directory at {root}", file=sys.stderr)
        return EXIT_USAGE
    ledger = _ledger_from_args(args)
    try:
        if args.command == "status":
            return cmd_status(ledger)
        if args.command == "snapshot":
            return cmd_snapshot(ledger, args.message)
        if args.command == "log":
            return cmd_log(ledger, args.count)
        if args.command == "history":
            return cmd_history(ledger, args.page, args.count)
        if args.command == "diff":
            return cmd_diff(ledger, args.page, args.from_rev, args.to_rev)
        if args.command == "restore":
            return cmd_restore(ledger, args.page, args.rev, args.apply, args.force)
        print(f"unknown command: {args.command}", file=sys.stderr)
        return EXIT_USAGE
    except GitMissing as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_GIT_MISSING
    except LedgerBusy as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_BUSY
    except LedgerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE if isinstance(exc, ArgumentError) else EXIT_ERROR
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
