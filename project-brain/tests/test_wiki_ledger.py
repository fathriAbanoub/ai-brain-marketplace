"""WP1: the wiki ledger — local version history for .brain/wiki only.

Storage is a separate bare git dir at .brain/state/wiki.git with work tree
.brain/wiki (never a .git inside the wiki — it would clash with the project's
repo). These tests drive the real CLI (scripts/wiki_ledger.py via the bin
shim path used by the skill) and the real scaffold/reset scripts as
subprocesses, so every claim is exercised against the installed git.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

import wiki_ledger  # noqa: E402

LEDGER = PLUGIN_ROOT / "scripts" / "wiki_ledger.py"
WIKI_GIT_REL = Path(".brain") / "state" / "wiki.git"
CLI_TIMEOUT_SECS = 30
# status prints one section header + the truncation note + the snapshot hint
# on top of a page list capped at MAX_STATUS_PAGES.
STATUS_SECTION_OVERHEAD = 3
# Pages written beyond the cap so truncation must trigger.
PAGES_BEYOND_CAP = 10


def run_cli(root: Path, *args: str, env: dict | None = None,
            timeout: int = CLI_TIMEOUT_SECS) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(LEDGER), str(root), *args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                          env=env if env is not None else os.environ.copy())


def run_script_env(script: str, args: list[str], env: dict,
                   timeout: int = CLI_TIMEOUT_SECS) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(PLUGIN_ROOT / "scripts" / script), *args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)


def base_env(**overrides: str) -> dict:
    env = os.environ.copy()
    env.update(overrides)
    return env


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    root = tmp_path / "ledger-project"
    (root / ".brain" / "wiki").mkdir(parents=True)
    (root / ".brain" / "state").mkdir(parents=True)
    return root


@pytest.fixture
def scaffolded(run_script, tmp_path: Path) -> Path:
    root = tmp_path / "scaffolded-project"
    root.mkdir()
    result = run_script("scaffold_brain.py", [str(root), "Ledger Proj"])
    assert result.returncode == 0, result.stderr
    return root


def write_page(root: Path, rel: str, text: str) -> Path:
    page = root / ".brain" / "wiki" / rel
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(text, encoding="utf-8")
    return page


# --- lifecycle -----------------------------------------------------------------

class TestLedgerLifecycle:
    def test_status_without_ledger_is_not_an_error(self, proj: Path):
        r = run_cli(proj, "status")
        assert r.returncode == 0
        assert "no ledger yet" in r.stdout

    def test_snapshot_creates_ledger_lazily(self, proj: Path):
        write_page(proj, "concepts/A.md", "# A\n")
        r = run_cli(proj, "snapshot")
        assert r.returncode == 0, r.stderr
        assert (proj / WIKI_GIT_REL / "HEAD").is_file()
        # The whole point of the storage layout: no .git inside the wiki.
        assert not (proj / ".brain" / "wiki" / ".git").exists()
        assert "snapshot" in r.stdout

    def test_snapshot_is_noop_when_clean(self, proj: Path):
        write_page(proj, "concepts/A.md", "# A\n")
        run_cli(proj, "snapshot")
        r = run_cli(proj, "snapshot")
        assert r.returncode == 0
        assert "nothing to snapshot" in r.stdout

    def test_status_reports_changed_pages(self, proj: Path):
        write_page(proj, "concepts/A.md", "# A\n")
        run_cli(proj, "snapshot")
        write_page(proj, "concepts/A.md", "# A changed\n")
        write_page(proj, "System Overview.md", "# overview\n")
        r = run_cli(proj, "status")
        assert r.returncode == 0
        assert "uncommitted:" in r.stdout
        assert "concepts/A.md" in r.stdout
        assert "System Overview.md" in r.stdout
        assert "snapshot with:" in r.stdout
        # A is also in the last snapshot's page set, but uncommitted wins:
        # a page is listed once, in the actionable section.
        assert r.stdout.count("concepts/A.md") == 1
        assert "recently snapshotted" not in r.stdout

    def test_log_lists_snapshots_with_default_message(self, proj: Path):
        write_page(proj, "concepts/A.md", "# A\n")
        write_page(proj, "concepts/B.md", "# B\n")
        run_cli(proj, "snapshot")
        r = run_cli(proj, "log", "5")
        assert r.returncode == 0
        assert "snapshot: 2 page(s) changed" in r.stdout

    def test_history_reports_page_touches(self, proj: Path):
        write_page(proj, "concepts/A.md", "# A\n")
        write_page(proj, "concepts/B.md", "# B\n")
        run_cli(proj, "snapshot")
        write_page(proj, "concepts/A.md", "# A v2\n")
        run_cli(proj, "snapshot", "-m", "work: a v2")
        r = run_cli(proj, "history", "concepts/A.md")
        assert r.returncode == 0
        assert "work: a v2" in r.stdout
        assert "snapshot: 2 page(s) changed" in r.stdout

    def test_spaces_and_non_ascii_survive(self, proj: Path):
        write_page(proj, "System Overview.md", "# overview\n")
        write_page(proj, "concepts/Naïve Päge.md", "# ünïcode\n")
        r = run_cli(proj, "snapshot")
        assert r.returncode == 0, r.stderr
        write_page(proj, "concepts/Naïve Päge.md", "# ünïcode v2\n")
        r = run_cli(proj, "diff", "concepts/Naïve Päge.md")
        assert r.returncode == 0, r.stderr
        assert "+# ünïcode v2" in r.stdout
        r = run_cli(proj, "history", "System Overview.md")
        assert r.returncode == 0 and r.stdout.strip()

    def test_output_is_bounded(self, proj: Path):
        page = write_page(proj, "concepts/Big.md", "# big\n")
        run_cli(proj, "snapshot")
        page.write_text("# big\n" + "\n".join(f"line {i}" for i in range(500)),
                        encoding="utf-8")
        r = run_cli(proj, "diff", "concepts/Big.md")
        assert r.returncode == 0
        lines = r.stdout.splitlines()
        assert len(lines) <= wiki_ledger.MAX_DIFF_LINES + 1
        assert "truncated" in lines[-1]


# --- restore -------------------------------------------------------------------

class TestRestore:
    def _seed(self, proj: Path) -> str:
        page = write_page(proj, "concepts/A.md", "# A v1\n")
        run_cli(proj, "snapshot", "-m", "work: v1")
        rev1 = run_cli(proj, "log", "1").stdout.split()[0]
        page.write_text("# A v2\n", encoding="utf-8")
        run_cli(proj, "snapshot", "-m", "work: v2")
        return rev1

    def test_dry_run_is_default_and_changes_nothing(self, proj: Path):
        rev1 = self._seed(proj)
        r = run_cli(proj, "restore", "concepts/A.md", "--rev", rev1)
        assert r.returncode == 0
        assert "dry run" in r.stdout and "run with --apply" in r.stdout
        assert "# A v2" in (proj / ".brain" / "wiki" / "concepts" / "A.md").read_text(encoding="utf-8")

    def test_apply_restores_content_and_commits(self, proj: Path):
        rev1 = self._seed(proj)
        r = run_cli(proj, "restore", "concepts/A.md", "--rev", rev1, "--apply")
        assert r.returncode == 0, r.stderr
        assert "# A v1" in (proj / ".brain" / "wiki" / "concepts" / "A.md").read_text(encoding="utf-8")
        log = run_cli(proj, "log", "3").stdout
        assert "restore: concepts/A.md" in log
        # The working tree is clean vs HEAD (explicit --from semantics), and
        # status names the restored page via the restore snapshot.
        assert "no differences" in run_cli(proj, "diff", "concepts/A.md",
                                           "--from", "HEAD").stdout
        assert "concepts/A.md" in run_cli(proj, "status").stdout

    def test_refuses_uncommitted_changes_without_force(self, proj: Path):
        self._seed(proj)
        write_page(proj, "concepts/A.md", "# A draft (uncommitted)\n")
        r = run_cli(proj, "restore", "concepts/A.md", "--rev", "HEAD~1", "--apply")
        assert r.returncode == 1
        assert "uncommitted" in r.stderr
        assert "uncommitted" in (proj / ".brain" / "wiki" / "concepts" / "A.md").read_text(encoding="utf-8")

    def test_force_takes_automatic_snapshot_first(self, proj: Path):
        rev1 = self._seed(proj)
        write_page(proj, "concepts/A.md", "# A draft (uncommitted)\n")
        r = run_cli(proj, "restore", "concepts/A.md", "--rev", rev1, "--apply", "--force")
        assert r.returncode == 0, r.stderr
        log = run_cli(proj, "log", "3").stdout
        # The draft state was committed BEFORE the restore, so it is recoverable.
        assert "snapshot: 1 page(s) changed" in log
        assert "restore: concepts/A.md" in log
        assert "# A v1" in (proj / ".brain" / "wiki" / "concepts" / "A.md").read_text(encoding="utf-8")

    def test_restore_never_writes_outside_the_wiki(self, proj: Path):
        rev1 = self._seed(proj)
        outside = proj / "outside.txt"
        outside.write_text("project file\n", encoding="utf-8")
        r = run_cli(proj, "restore", "../outside.txt", "--rev", rev1)
        assert r.returncode == 2
        assert outside.read_text(encoding="utf-8") == "project file\n"


# --- trust boundary ------------------------------------------------------------

class TestTrustBoundary:
    def test_absolute_path_rejected(self, proj: Path):
        run_cli(proj, "snapshot")
        r = run_cli(proj, "diff", str(proj / ".brain" / "wiki" / "x.md"))
        assert r.returncode == 2
        assert "wiki-relative" in r.stderr

    def test_dotdot_rejected(self, proj: Path):
        run_cli(proj, "snapshot")
        for arg in ("../x.md", "concepts/../../x.md"):
            r = run_cli(proj, "diff", arg)
            assert r.returncode == 2, arg
            assert "'..'" in r.stderr

    def test_symlink_escape_rejected(self, proj: Path):
        write_page(proj, "concepts/A.md", "# A\n")
        run_cli(proj, "snapshot")
        outside = proj / "secret.md"
        outside.write_text("secret\n", encoding="utf-8")
        link = proj / ".brain" / "wiki" / "concepts" / "link.md"
        link.symlink_to(outside)
        r = run_cli(proj, "restore", "concepts/link.md", "--rev", "HEAD")
        assert r.returncode == 2
        assert "escapes the wiki" in r.stderr

    def test_unknown_revision_rejected(self, proj: Path):
        write_page(proj, "concepts/A.md", "# A\n")
        run_cli(proj, "snapshot")
        r = run_cli(proj, "restore", "concepts/A.md", "--rev", "deadbeef")
        assert r.returncode == 1
        assert "unknown revision" in r.stderr

    def test_missing_git_is_exit_127_with_clear_message(self, proj, tmp_path_factory):
        empty = tmp_path_factory.mktemp("pathless")
        pylink = empty / "python3"
        pylink.write_text("#!/bin/sh\nexec %s \"$@\"\n" % sys.executable)
        pylink.chmod(0o755)
        env = base_env(PATH=str(empty))
        write_page(proj, "concepts/A.md", "# A\n")
        r = run_cli(proj, "snapshot", env=env)
        assert r.returncode == 127
        assert "git is required" in r.stderr


# --- concurrency -----------------------------------------------------------------

class TestConcurrency:
    def test_locked_index_fails_fast_and_reports(self, proj: Path):
        write_page(proj, "concepts/A.md", "# A\n")
        run_cli(proj, "snapshot")
        lock = proj / WIKI_GIT_REL / "index.lock"
        lock.write_text("", encoding="utf-8")
        write_page(proj, "concepts/A.md", "# A changed\n")
        start = time.monotonic()
        r = run_cli(proj, "snapshot", timeout=20)
        elapsed = time.monotonic() - start
        assert r.returncode == 75, r.stderr
        assert "lock" in r.stderr
        assert elapsed < 15, "a locked ledger must fail fast, never hang"


# --- environment sandbox ---------------------------------------------------------

class TestEnvSandbox:
    def test_user_git_config_never_reaches_ledger_commits(self, proj, tmp_path):
        """A hostile global config must not own the ledger identity or hooks."""
        home = tmp_path / "hostile-home"
        home.mkdir()
        (home / ".gitconfig").write_text(
            "[user]\n\tname = hostile\n\temail = hostile@evil\n"
            "[core]\n\thooksPath = /nonexistent-evil-hooks\n", encoding="utf-8")
        write_page(proj, "concepts/A.md", "# A\n")
        env = base_env(HOME=str(home))
        # GIT_CONFIG_GLOBAL is git >= 2.32; set it too so this test does not
        # depend on the module's version probe.
        env["GIT_CONFIG_GLOBAL"] = str(tmp_path / "empty.cfg")
        (tmp_path / "empty.cfg").write_text("", encoding="utf-8")
        r = run_cli(proj, "snapshot", env=env)
        assert r.returncode == 0, r.stderr
        argv = ["git", f"--git-dir={proj / WIKI_GIT_REL}", "log", "--format=%an|%ae"]
        proc = subprocess.run(argv, capture_output=True, text=True, check=True)
        assert proc.stdout.strip() == "project-brain|project-brain@localhost"

    def test_git_dir_env_redirect_is_stripped(self, proj, tmp_path):
        """A GIT_DIR/GIT_WORK_TREE pair in the environment must not steer the
        ledger's git calls at some other repository."""
        other = tmp_path / "other-repo"
        other.mkdir()
        subprocess.run(["git", "init", "-q", str(other)], check=True)
        write_page(proj, "concepts/A.md", "# A\n")
        env = base_env(GIT_DIR=str(other / ".git"), GIT_WORK_TREE=str(other))
        r = run_cli(proj, "snapshot", env=env)
        assert r.returncode == 0, r.stderr
        # The snapshot landed in the LEDGER, not in the redirected repo.
        log = subprocess.run(["git", "-C", str(other), "log", "--oneline"],
                             capture_output=True, text=True)
        assert log.returncode != 0 or not log.stdout.strip()


# --- integration: scaffold and reset ---------------------------------------------

class TestScaffoldIntegration:
    def test_scaffold_creates_ledger_with_baseline_snapshot(self, scaffolded: Path):
        assert (scaffolded / WIKI_GIT_REL / "HEAD").is_file()
        r = run_cli(scaffolded, "log", "5")
        assert "baseline: brain scaffold" in r.stdout
        assert not (scaffolded / ".brain" / "wiki" / ".git").exists()

    def test_scaffold_without_git_warns_and_continues(self, tmp_path, tmp_path_factory):
        empty = tmp_path_factory.mktemp("pathless2")
        pylink = empty / "python3"
        pylink.write_text("#!/bin/sh\nexec %s \"$@\"\n" % sys.executable)
        pylink.chmod(0o755)
        root = tmp_path / "nogit-project"
        root.mkdir()
        result = run_script_env("scaffold_brain.py", [str(root), "NoGit"],
                                base_env(PATH=str(empty)))
        assert result.returncode == 0, result.stderr
        assert "git is missing" in result.stdout
        assert not (root / WIKI_GIT_REL).exists()

    def test_scaffold_notes_unignored_outer_repo(self, scaffolded: Path):
        """The user's .gitignore is never edited; a note prints instead."""
        subprocess.run(["git", "init", "-q", str(scaffolded)], check=True)
        r = run_script_env("scaffold_brain.py", [str(scaffolded), "Ledger Proj"],
                           base_env())
        assert r.returncode == 0
        assert "does not exclude .brain/state/" in r.stdout
        gitignore = scaffolded / ".gitignore"
        assert not gitignore.exists() or ".brain/state/" not in gitignore.read_text(encoding="utf-8")

    def test_scaffold_silent_when_outer_repo_ignores_state(self, tmp_path: Path):
        root = tmp_path / "ignored-state-project"
        root.mkdir()
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        (root / ".gitignore").write_text(".brain/state/\n", encoding="utf-8")
        r = run_script_env("scaffold_brain.py", [str(root), "Ignored"],
                           base_env())
        assert r.returncode == 0
        assert "does not exclude" not in r.stdout

    def test_scaffolded_claude_md_documents_the_ledger(self, scaffolded: Path):
        text = (scaffolded / ".brain" / "CLAUDE.md").read_text(encoding="utf-8")
        assert "## Wiki ledger" in text
        assert ".brain/state/wiki.git" in text
        assert "project-brain-wiki" in text

    def test_removal_leaves_no_stale_ledger(self, run_script, tmp_path: Path):
        """reset_brain --confirm removes .brain/ including .brain/state/wiki.git."""
        proj = tmp_path / "reset-ledger"
        proj.mkdir()
        result = run_script("scaffold_brain.py", [str(proj), "Reset Ledger"])
        assert result.returncode == 0
        assert (proj / WIKI_GIT_REL / "HEAD").is_file()
        env = base_env(PROJECT_BRAIN_RESET_WAIT_SECONDS="0")
        result = run_script_env("reset_brain.py", [str(proj), "--confirm"], env)
        assert result.returncode == 0, result.stderr
        assert not (proj / ".brain").exists()
        assert not (proj / WIKI_GIT_REL).exists()


# --- hook helper -------------------------------------------------------------------

class TestLedgerStatusLine:
    def test_absent_without_ledger(self, proj: Path):
        assert wiki_ledger.ledger_status_line(proj) is None

    def test_reports_uncommitted_and_last_snapshot_separately(self, proj: Path):
        write_page(proj, "concepts/A.md", "# A\n")
        run_cli(proj, "snapshot")
        line = wiki_ledger.ledger_status_line(proj)
        assert line is not None
        assert "no uncommitted changes" in line and "last snapshot" in line
        write_page(proj, "concepts/B.md", "# B\n")
        line = wiki_ledger.ledger_status_line(proj)
        assert line is not None
        # The pending work and the history pointer are separate facts.
        assert "1 uncommitted" in line
        assert "last snapshot" in line

    def test_without_snapshots_counts_uncommitted(self, proj: Path):
        run_cli(proj, "snapshot")  # empty ledger: exists, no snapshots
        write_page(proj, "concepts/A.md", "# A\n")
        line = wiki_ledger.ledger_status_line(proj)
        assert line is not None
        assert "1 uncommitted" in line and "no snapshots yet" in line

    def test_corrupt_ledger_yields_none(self, proj: Path):
        (proj / WIKI_GIT_REL).mkdir(parents=True)
        (proj / WIKI_GIT_REL / "HEAD").write_text("garbage\n", encoding="utf-8")
        assert wiki_ledger.ledger_status_line(proj) is None


# --- 0.10.1 D1: hook-driven semantics --------------------------------------------
# The PostToolUse hook commits every wiki edit (`auto:` snapshots), so answers
# must come from snapshot history, not just the working tree.

def run_hook_edit(root: Path, page: Path, tool: str = "Write") -> subprocess.CompletedProcess:
    """Drive one wiki edit through the real PostToolUse hook (real stdin JSON)."""
    payload = json.dumps({
        "hook_event_name": "PostToolUse",
        "tool_name": tool,
        "tool_input": {"file_path": str(page)},
        "cwd": str(root),
    })
    return subprocess.run(
        [sys.executable, str(PLUGIN_ROOT / "hooks" / "brain_hooks.py"),
         "post-tool-use"],
        input=payload, capture_output=True, text=True, timeout=30,
        env={**os.environ, "CLAUDE_PLUGIN_DATA": str(root / "hook-state")},
    )


class TestHookDrivenLedger:
    def test_hook_edits_are_visible_to_status_diff_and_restore(self, scaffolded: Path):
        root = scaffolded
        page = root / ".brain" / "wiki" / "concepts" / "Latch.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("# Latch\n\nv1 body\n", encoding="utf-8")
        assert run_hook_edit(root, page).returncode == 0
        page.write_text("# Latch\n\nv2 body (edited)\n", encoding="utf-8")
        assert run_hook_edit(root, page, tool="Edit").returncode == 0
        # No manual snapshot happened: the hook committed both edits.
        assert "auto: Edit concepts/Latch.md" in run_cli(root, "log", "5").stdout

        # status names the page even though the working tree is clean.
        r = run_cli(root, "status")
        assert r.returncode == 0
        assert "concepts/Latch.md" in r.stdout

        # diff <page> shows the page's most recent change (the edit).
        r = run_cli(root, "diff", "concepts/Latch.md")
        assert r.returncode == 0
        assert "-v1 body" in r.stdout and "+v2 body (edited)" in r.stdout

        # restore <page> (no --rev) undoes it: dry run shows worktree -> the
        # version before the latest change.
        r = run_cli(root, "restore", "concepts/Latch.md")
        assert r.returncode == 0
        assert "dry run" in r.stdout and "run with --apply" in r.stdout
        assert "-v2 body (edited)" in r.stdout and "+v1 body" in r.stdout
        assert "v2 body (edited)" in page.read_text(encoding="utf-8")

        r = run_cli(root, "restore", "concepts/Latch.md", "--apply")
        assert r.returncode == 0, r.stderr
        assert page.read_text(encoding="utf-8") == "# Latch\n\nv1 body\n"
        assert "restore: concepts/Latch.md" in run_cli(root, "log", "3").stdout

    def test_diff_default_layers_uncommitted_change_on_last_versions(self, proj: Path):
        page = write_page(proj, "concepts/A.md", "# A v1\n")
        run_cli(proj, "snapshot")
        page.write_text("# A v2\n", encoding="utf-8")
        run_cli(proj, "snapshot")
        page.write_text("# A v2 draft\n", encoding="utf-8")  # uncommitted
        r = run_cli(proj, "diff", "concepts/A.md")
        assert r.returncode == 0
        # Both layers: v1 -> v2 (committed) and v2 -> draft (uncommitted).
        assert "-# A v1" in r.stdout and "+# A v2" in r.stdout
        assert "-# A v2\n" in r.stdout  # v2 removed on the uncommitted layer
        assert "+# A v2 draft" in r.stdout

    def test_diff_without_page_shows_last_snapshot_and_uncommitted(self, proj: Path):
        page = write_page(proj, "concepts/A.md", "# A v1\n")
        run_cli(proj, "snapshot")
        page.write_text("# A v2\n", encoding="utf-8")
        run_cli(proj, "snapshot")
        write_page(proj, "concepts/B.md", "# B\n")   # uncommitted
        write_page(proj, "concepts/C.md", "# C\n")   # untracked new page
        r = run_cli(proj, "diff")
        assert r.returncode == 0
        assert "+# A v2" in r.stdout       # last snapshot's change (v1 -> v2)
        assert "-# A v1" in r.stdout
        assert "+# B" in r.stdout          # uncommitted
        assert "+# C" in r.stdout          # untracked shows as a new file

    def test_diff_of_untracked_page_shows_new_file(self, proj: Path):
        run_cli(proj, "snapshot")  # empty ledger; the page is never snapshotted
        write_page(proj, "concepts/Fresh.md", "# Fresh\n")
        r = run_cli(proj, "diff", "concepts/Fresh.md")
        assert r.returncode == 0
        assert "+# Fresh" in r.stdout


# --- 0.10.1 D2: --rev is pinned before the automatic snapshot ---------------------

class TestRestoreRevPinning:
    """restore --rev HEAD used to resolve AFTER the automatic pre-restore
    snapshot moved HEAD: it printed success and restored nothing."""

    def _two_versions(self, proj: Path) -> Path:
        page = write_page(proj, "concepts/Relay.md", "# Relay v1\n")
        run_cli(proj, "snapshot")
        page.write_text("# Relay v2\n", encoding="utf-8")
        run_cli(proj, "snapshot")
        return page

    def test_restore_head_after_overwrite_restores_committed_content(self, proj: Path):
        page = self._two_versions(proj)
        page.write_text("# Relay BAD\n", encoding="utf-8")
        r = run_cli(proj, "restore", "concepts/Relay.md", "--rev", "HEAD",
                    "--apply", "--force")
        assert r.returncode == 0, r.stderr
        assert "GOOD" not in page.read_text(encoding="utf-8")
        assert "# Relay v2" in page.read_text(encoding="utf-8")

    def test_restore_head_minus_one_after_overwrite(self, proj: Path):
        page = self._two_versions(proj)
        page.write_text("# Relay BAD\n", encoding="utf-8")
        r = run_cli(proj, "restore", "concepts/Relay.md", "--rev", "HEAD~1",
                    "--apply", "--force")
        assert r.returncode == 0, r.stderr
        assert "# Relay v1" in page.read_text(encoding="utf-8")

    def test_restore_full_hash_after_overwrite(self, proj: Path):
        page = self._two_versions(proj)
        rev = run_cli(proj, "log", "1").stdout.split()[0]  # HEAD (v2) hash
        page.write_text("# Relay BAD\n", encoding="utf-8")
        r = run_cli(proj, "restore", "concepts/Relay.md", "--rev", rev,
                    "--apply", "--force")
        assert r.returncode == 0, r.stderr
        assert "# Relay v2" in page.read_text(encoding="utf-8")

    def test_dry_run_allowed_on_dirty_page(self, proj: Path):
        page = self._two_versions(proj)
        page.write_text("# Relay BAD\n", encoding="utf-8")
        r = run_cli(proj, "restore", "concepts/Relay.md", "--rev", "HEAD")
        assert r.returncode == 0
        assert "dry run" in r.stdout
        # The diff runs from the CURRENT working-tree content to the target.
        assert "-# Relay BAD" in r.stdout and "+# Relay v2" in r.stdout

    def test_apply_without_force_still_refused_on_dirty_page(self, proj: Path):
        page = self._two_versions(proj)
        page.write_text("# Relay BAD\n", encoding="utf-8")
        r = run_cli(proj, "restore", "concepts/Relay.md", "--rev", "HEAD", "--apply")
        assert r.returncode == 1
        assert "uncommitted" in r.stderr
        assert "# Relay BAD" in page.read_text(encoding="utf-8")

    def test_option_like_revisions_are_rejected_not_executed(self, proj: Path):
        """A revision that looks like a git option must be refused, not run:
        the space-separated form is caught by argparse, the =-glued form by
        the rev-parsing pin (nothing option-shaped reaches checkout)."""
        page = self._two_versions(proj)
        page.write_text("# Relay BAD\n", encoding="utf-8")
        for rev in ("-C/tmp/evil", "--quiet", "-x"):
            r = run_cli(proj, "restore", "concepts/Relay.md", "--rev", rev,
                        "--apply", "--force")
            assert r.returncode != 0, rev
            r = run_cli(proj, "restore", "concepts/Relay.md", f"--rev={rev}",
                        "--apply", "--force")
            assert r.returncode == 1, rev
            assert "unknown revision" in r.stderr
        assert "# Relay BAD" in page.read_text(encoding="utf-8")  # nothing ran

    def test_post_apply_verification_failure_raises_loudly(self, proj: Path):
        """If the checked-out file ever diverges from the target blob, restore
        must error instead of reporting success (0.10.0 printed success while
        the file kept the bad content)."""
        page = self._two_versions(proj)
        ledger = wiki_ledger.WikiLedger(proj)
        real_run = wiki_ledger.WikiLedger._run

        def failing_verification(self, *args, check=True, **kwargs):
            # Match ONLY the post-checkout verification call ("diff", "--quiet",
            # <hash>, "--", <rel>); snapshot's staged check is "--cached" first.
            if args[:2] == ("diff", "--quiet"):
                return subprocess.CompletedProcess(args, 1, "", "simulated divergence")
            return real_run(self, *args, check=check, **kwargs)

        with patch.object(wiki_ledger.WikiLedger, "_run", failing_verification):
            with pytest.raises(wiki_ledger.LedgerError, match="verification failed"):
                ledger.restore("concepts/Relay.md", "HEAD", apply=True, force=True)
        # No restore snapshot was committed after the failed verification.
        assert "restore:" not in run_cli(proj, "log", "5").stdout
        assert page.is_file()


# --- 0.10.1 D3: untracked pages are individual, never one directory ----------------

class TestUntrackedStatus:
    def test_three_new_pages_in_empty_dir_count_three(self, proj: Path):
        run_cli(proj, "snapshot")  # empty ledger: exists, no snapshots yet
        for name in ("Alpha", "Beta", "Gamma"):
            write_page(proj, f"concepts/{name}.md", f"# {name}\n")
        r = run_cli(proj, "status")
        assert r.returncode == 0
        assert "uncommitted:" in r.stdout
        for name in ("Alpha.md", "Beta.md", "Gamma.md"):
            assert f"concepts/{name}" in r.stdout
        assert "concepts/\n" not in r.stdout  # the collapsed directory is gone
        # The SessionStart line inherits the same honest count.
        line = wiki_ledger.ledger_status_line(proj)
        assert line is not None and "3 uncommitted" in line

    def test_changed_pages_lists_each_first_page(self, scaffolded: Path):
        for name in ("Alpha", "Beta", "Gamma"):
            write_page(scaffolded, f"concepts/{name}.md", f"# {name}\n")
        pages = wiki_ledger.WikiLedger(scaffolded).changed_pages()
        assert pages == ["concepts/Alpha.md", "concepts/Beta.md", "concepts/Gamma.md"]


# --- 0.10.2 F1: status separates uncommitted work from recent history ----------
# "N page(s) changed recently (uncommitted + last 20 snapshots)" was identical
# in form whether anything was uncommitted or not, and a fresh project
# permanently listed its scaffold pages.

class TestStatusSections:
    def test_clean_ledger_says_no_uncommitted(self, proj: Path):
        run_cli(proj, "snapshot")  # ledger exists, nothing snapshotted, no pages
        r = run_cli(proj, "status")
        assert r.returncode == 0
        assert r.stdout.strip() == "no uncommitted changes"

    def test_recent_only_after_snapshot(self, proj: Path):
        write_page(proj, "concepts/A.md", "# A\n")
        run_cli(proj, "snapshot")
        r = run_cli(proj, "status")
        assert r.returncode == 0
        assert "no uncommitted changes" in r.stdout
        assert "recently snapshotted" in r.stdout
        assert "concepts/A.md" in r.stdout
        assert "snapshot with:" not in r.stdout  # nothing to snapshot

    def test_uncommitted_only_after_unhooked_edit(self, proj: Path):
        """An edit that bypasses the hook (or lint --reindex) is uncommitted
        work, not history — it must land in the uncommitted section."""
        page = write_page(proj, "concepts/A.md", "# A\n")
        run_cli(proj, "snapshot")
        page.write_text("# A changed\n", encoding="utf-8")
        r = run_cli(proj, "status")
        assert r.returncode == 0
        assert "uncommitted:" in r.stdout and "concepts/A.md" in r.stdout
        assert "snapshot with:" in r.stdout
        # The page is uncommitted, not merely recent: no snapshotted section.
        assert "recently snapshotted" not in r.stdout

    def test_reindex_shows_as_uncommitted(self, scaffolded: Path):
        write_page(scaffolded, "concepts/Extra.md", "# Extra\n")
        r = run_script_env("lint_brain.py", [str(scaffolded), "--reindex"], base_env())
        assert r.returncode in (0, 1)
        r = run_cli(scaffolded, "status")
        assert "uncommitted:" in r.stdout
        assert "index.md" in r.stdout  # rewritten by --reindex, outside the hook
        assert "concepts/Extra.md" in r.stdout
        assert "snapshot with:" in r.stdout

    def test_both_sections_page_appears_once(self, proj: Path):
        write_page(proj, "concepts/A.md", "# A\n")
        write_page(proj, "concepts/B.md", "# B\n")
        run_cli(proj, "snapshot")
        write_page(proj, "concepts/A.md", "# A changed\n")
        r = run_cli(proj, "status")
        assert r.returncode == 0
        assert "uncommitted:" in r.stdout and "recently snapshotted" in r.stdout
        assert "concepts/B.md" in r.stdout  # history section
        assert "snapshot with:" in r.stdout
        # A appears exactly once (uncommitted), B exactly once (snapshotted).
        assert r.stdout.count("concepts/A.md") == 1
        assert r.stdout.count("concepts/B.md") == 1

    def test_untracked_page_listed_individually_in_uncommitted(self, proj: Path):
        write_page(proj, "concepts/A.md", "# A\n")
        run_cli(proj, "snapshot")
        write_page(proj, "concepts/New.md", "# New\n")  # untracked
        r = run_cli(proj, "status")
        assert r.returncode == 0
        assert "uncommitted:" in r.stdout and "concepts/New.md" in r.stdout
        assert "recently snapshotted" in r.stdout and "concepts/A.md" in r.stdout

    def test_bounded_by_existing_limits(self, proj: Path):
        run_cli(proj, "snapshot")
        for i in range(wiki_ledger.MAX_STATUS_PAGES + PAGES_BEYOND_CAP):
            write_page(proj, f"bulk/p{i:03d}.md", f"# {i}\n")
        r = run_cli(proj, "status")
        assert r.returncode == 0
        lines = r.stdout.splitlines()
        assert len(lines) <= wiki_ledger.MAX_STATUS_PAGES + STATUS_SECTION_OVERHEAD
        assert "truncated" in "\n".join(lines)


# --- 0.10.2 F2: clearer messages ------------------------------------------------

class TestClearerMessages:
    def test_diff_single_version_says_so(self, proj: Path):
        write_page(proj, "concepts/A.md", "# A\n")
        run_cli(proj, "snapshot")
        short = run_cli(proj, "log", "1").stdout.split()[0]
        r = run_cli(proj, "diff", "concepts/A.md")
        assert r.returncode == 0
        assert f"page has one version, created in {short}" in r.stdout
        assert "nothing earlier to compare" in r.stdout
        assert "no differences" not in r.stdout

    def test_diff_single_version_with_uncommitted_change_shows_it(self, proj: Path):
        page = write_page(proj, "concepts/A.md", "# A\n")
        run_cli(proj, "snapshot")
        page.write_text("# A draft\n", encoding="utf-8")
        r = run_cli(proj, "diff", "concepts/A.md")
        assert r.returncode == 0
        assert "+# A draft" in r.stdout  # the change itself, not the notice

    def test_explicit_rev_diff_keeps_no_differences(self, proj: Path):
        """The notice is for the default most-recent-change path only."""
        write_page(proj, "concepts/A.md", "# A\n")
        run_cli(proj, "snapshot")
        r = run_cli(proj, "diff", "concepts/A.md", "--from", "HEAD")
        assert r.returncode == 0 and "no differences" in r.stdout

    def test_restore_dry_run_legend_marks_direction(self, proj: Path):
        page = write_page(proj, "concepts/A.md", "# A v1\n")
        run_cli(proj, "snapshot")
        page.write_text("# A v2\n", encoding="utf-8")
        run_cli(proj, "snapshot")
        r = run_cli(proj, "restore", "concepts/A.md")
        assert r.returncode == 0
        assert "(- lines are in the page now, + lines are in the target)" in r.stdout
        # Direction unchanged: minus = current content, plus = the target.
        assert "-# A v2" in r.stdout and "+# A v1" in r.stdout
