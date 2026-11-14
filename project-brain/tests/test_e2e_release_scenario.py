"""WP6: one deterministic, offline end-to-end release scenario.

A real temporary git project walks the full 0.10.0 path exactly the way a
session would:

  init (bin shim) -> author pages the way a careless agent would -> lint ->
  follow the printed hints to green -> snapshot -> run the hooks with real
  stdin JSON payloads (schema + bounds) -> compaction-style recovery
  (`status`, `log` in fresh processes) -> restore after a bad edit ->
  cold read of SKILL.md confirming every named reference exists.

Everything is offline: no MCP, no network; the graph report is seeded like
the hook tests do (a "Built from commit" line) so freshness checks run.
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "tests"))

from conftest import GIT_REPO_LOCATION_ENV_VARS  # noqa: E402

BIN = PLUGIN_ROOT / "bin"
HOOK = PLUGIN_ROOT / "hooks" / "brain_hooks.py"
SKILL = PLUGIN_ROOT / "skills" / "brain" / "SKILL.md"
REFERENCE_NAME_RE = re.compile(r"references/([a-z0-9-]+\.md)")
WIKI_GIT = Path(".brain") / "state" / "wiki.git"

PAGE_FM = ("---\ntitle: {title}\ntype: concept\ncreated: 2026-01-01\n"
           "updated: 2026-01-01\nstatus: active\n{sources}tags: [t]\n---\n")
FILLER = "This page carries a real, checkable summary of the demo engine. " * 4


def sh(cmd: list[str], cwd: Path | None = None, env: dict | None = None,
        stdin: str | None = None, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, env=env, input=stdin, capture_output=True,
                          text=True, timeout=timeout)


def git(root: Path, *args: str) -> str:
    # Strip inherited Git repository-location variables so every call targets
    # the explicitly selected repository, never one inherited from the
    # runner's environment.
    env = {k: v for k, v in os.environ.items()
           if k not in GIT_REPO_LOCATION_ENV_VARS}
    r = sh(["git", "-C", str(root), *args], env=env)
    assert r.returncode == 0, r.stderr
    return r.stdout


def bin_cmd(name: str) -> list[str]:
    return [str(BIN / f"project-brain-{name}")]


def hook_env(state_dir: Path) -> dict:
    env = {k: v for k, v in os.environ.items()
           if k not in ("OPENCLAUDE_CONFIG_DIR", "CLAUDE_PLUGIN_DATA",
                        "PROJECT_BRAIN_HOOKS_DISABLED")}
    env["CLAUDE_PLUGIN_DATA"] = str(state_dir)
    return env


def write_page(root: Path, rel: str, body: str, sources: str = "sources: []\n") -> Path:
    page = root / ".brain" / "wiki" / rel
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(PAGE_FM.format(title=page.stem, sources=sources) + "\n" + body,
                    encoding="utf-8")
    return page


def lint_json(root: Path) -> tuple[int, list[dict]]:
    r = sh(bin_cmd("lint") + [str(root), "--json"])
    assert r.returncode in (0, 1), r.stderr
    return r.returncode, json.loads(r.stdout)["issues"]


def test_release_scenario_end_to_end(run_script, tmp_path: Path):
    root = tmp_path / "e2e-release"
    root.mkdir()
    sh(["git", "init", "-q", str(root)])
    sh(["git", "-C", str(root), "config", "user.email", "e2e@example.com"])
    sh(["git", "-C", str(root), "config", "user.name", "e2e"])
    (root / "src").mkdir()
    (root / "src" / "engine.ts").write_text("export const rate = 48000;\n" * 10,
                                            encoding="utf-8")
    (root / "package.json").write_text('{"name": "e2e-release"}\n', encoding="utf-8")
    sh(["git", "-C", str(root), "add", "."])
    sh(["git", "-C", str(root), "commit", "-qm", "init"])

    # --- 1. init through the real bin shim -------------------------------
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(PLUGIN_ROOT),
               PYTHON_BIN=sys.executable, PROJECT_BRAIN_RESET_WAIT_SECONDS="0")
    r = sh(bin_cmd("init") + [str(root), "E2E Release"], env=env)
    assert r.returncode == 0, r.stderr
    assert (root / ".brain" / "CLAUDE.md").is_file()
    assert (root / ".brain" / "state" / "session-brief.md").is_file()
    assert (root / ".brain" / "wiki" / "index.md").is_file()
    assert (root / WIKI_GIT / "HEAD").is_file(), "init must create the wiki ledger"
    assert "baseline snapshot" in r.stdout

    # The graph report is seeded so the doctor's freshness line is real.
    head = git(root, "rev-parse", "HEAD").strip()
    out = root / "graphify-out"
    out.mkdir()
    (out / "GRAPH_REPORT.md").write_text(f"- Built from commit: `{head[:8]}`\n",
                                         encoding="utf-8")

    # --- 2. author pages the way a careless agent would -------------------
    (root / "README.md").write_text(
        "# E2E demo\n\nThe engine boots in order: kernel, then audio graph.\n",
        encoding="utf-8")
    write_page(root, "concepts/Careless.md",
               FILLER + "Rate: engine.ts:1 and [[README.md](../../README.md)].\n"
                        "Related: [[Ghost Topic]] and [[graphify-out/GRAPH_REPORT.md]].\n",
               sources="sources: [{ path: README.md, reliability: primary }]\n")
    write_page(root, "concepts/Drift.md",
               FILLER + 'Boots {{src README.md:1-1 "Usage: install and run"}}.\n')
    (root / ".brain" / "wiki" / "index.md").write_text(
        "# Project Brain Index - E2E Release\n\n## Concepts\n\n"
        "- [[concepts/Careless]] — once\n- [[concepts/Careless]] — twice\n- [[Ghost Page]]\n",
        encoding="utf-8")

    # --- 3. lint, follow the hints, reach green ---------------------------
    _, issues = lint_json(root)
    cats = {i["category"] for i in issues if i["severity"] == "error"}
    assert {"invalid_sources_entry", "broken_wikilink", "duplicate_index_entry",
            "index_entry_target_missing", "citation_drift"} <= cats

    # Repairs exactly as the hints describe (grep -n equivalent: we know the
    # real line contents because this test wrote them).
    write_page(root, "concepts/Careless.md",
               FILLER + 'Rate {{src src/engine.ts:1 "export const rate = 48000;"}} '
                        "and `README.md`.\nRelated: [[Ghost Topic]]. `graphify-out/GRAPH_REPORT.md`.\n",
               sources="sources: [README.md]\n")
    write_page(root, "concepts/Drift.md",
               FILLER + 'Boots {{src README.md:2-2 "The engine boots in order"}}.\n')
    write_page(root, "concepts/Ghost Topic.md", FILLER + "Created by the hint flow.\n")
    r = sh(bin_cmd("lint") + [str(root), "--reindex"])
    assert r.returncode in (0, 1)
    assert "reindexed" in r.stdout
    code, issues_after = lint_json(root)
    errors = [i for i in issues_after if i["severity"] == "error"]
    assert code == 0 and errors == [], json.dumps(errors, indent=2)

    # --- 4. snapshot the green state --------------------------------------
    r = sh(bin_cmd("wiki") + [str(root), "snapshot", "-m", "work: e2e batch"])
    assert r.returncode == 0, r.stderr
    r = sh(bin_cmd("wiki") + [str(root), "status"])
    # The batch is committed: nothing pending, the pages are the
    # recently-snapshotted set.
    assert r.returncode == 0 and "no uncommitted changes" in r.stdout
    assert "recently snapshotted" in r.stdout
    assert "concepts/Careless.md" in r.stdout

    # --- 5. hooks with real stdin JSON payloads ---------------------------
    state = tmp_path / "hook-state"
    state.mkdir()
    # 5a. a wiki edit: silent, but the ledger gains an auto snapshot.
    #     (In a real harness the Write tool has already written the file
    #     before PostToolUse fires — so write the change here too.)
    page = root / ".brain" / "wiki" / "concepts" / "Ghost Topic.md"
    page.write_text(page.read_text(encoding="utf-8") + "\nHook-driven edit.\n",
                    encoding="utf-8")
    payload = json.dumps({"cwd": str(root), "tool_name": "Write",
                          "tool_input": {"file_path": str(page)}})
    r = sh([sys.executable, str(HOOK), "post-tool-use"], env=hook_env(state),
           stdin=payload)
    assert r.returncode == 0 and r.stdout.strip() == ""
    log = sh(bin_cmd("wiki") + [str(root), "log", "5"]).stdout
    assert "auto: Write concepts/Ghost Topic.md" in log
    # 5b. a source edit with a stale graph: bounded PostToolUse reminder.
    (root / "src" / "extra.ts").write_text("export const b = 2;\n", encoding="utf-8")
    report = root / "graphify-out" / "GRAPH_REPORT.md"
    m = report.stat().st_mtime
    os.utime(root / "src" / "extra.ts", (m + 10, m + 10))
    r = sh([sys.executable, str(HOOK), "post-tool-use"], env=hook_env(state),
           stdin=json.dumps({"cwd": str(root), "tool_name": "Write",
                             "tool_input": {"file_path": str(root / "src" / "extra.ts")}}))
    assert r.returncode == 0
    spec = json.loads(r.stdout)["hookSpecificOutput"]
    assert spec["hookEventName"] == "PostToolUse"
    assert set(spec.keys()) <= {"hookEventName", "additionalContext",
                                "updatedMCPToolOutput"}
    assert 0 < len(spec["additionalContext"]) <= 700
    assert "source changed" in spec["additionalContext"]
    # 5c. SessionStart: schema, bounds, ledger line, snapshot semantics.
    r = sh([sys.executable, str(HOOK), "session-start"], env=hook_env(state),
           stdin=json.dumps({"cwd": str(root)}))
    assert r.returncode == 0
    spec = json.loads(r.stdout)["hookSpecificOutput"]
    assert spec["hookEventName"] == "SessionStart"
    assert len(spec["additionalContext"]) <= 700
    assert "launch-time snapshot" in spec["additionalContext"]
    assert "wiki ledger:" in spec["additionalContext"]

    # --- 6. compaction-style recovery (fresh processes, disk only) --------
    # A compacted session knows nothing but the files. status + log 5 must
    # reconstruct the wiki's change state from snapshot history (the hook
    # committed every edit, so uncommitted-only output would be empty).
    r = sh(bin_cmd("wiki") + [str(root), "status"])
    assert r.returncode == 0
    assert "no uncommitted changes" in r.stdout
    assert "recently snapshotted" in r.stdout
    r = sh(bin_cmd("wiki") + [str(root), "log", "5"])
    assert "work: e2e batch" in r.stdout and "auto: Write" in r.stdout

    # --- 7. restore after a bad edit ---------------------------------------
    good = page.read_text(encoding="utf-8")
    rev_before = sh(bin_cmd("wiki") + [str(root), "log", "1"]).stdout.split()[0]
    page.write_text("# garbage overwrite\n", encoding="utf-8")
    sh(bin_cmd("wiki") + [str(root), "snapshot", "-m", "work: bad edit"])
    r = sh(bin_cmd("wiki") + [str(root), "restore", "concepts/Ghost Topic.md",
                              "--rev", rev_before, "--apply"])
    assert r.returncode == 0, r.stderr
    assert page.read_text(encoding="utf-8") == good
    assert "restore: concepts/Ghost Topic.md" in sh(
        bin_cmd("wiki") + [str(root), "log", "3"]).stdout

    # --- 8. cold read of SKILL.md as a model that sees only that file -----
    text = SKILL.read_text(encoding="utf-8")
    # One authoritative procedure per mode (the 0.10.0 hygiene contract).
    assert len(re.findall(r"^## Work loop\b", text, re.M)) == 1
    assert len(re.findall(r"^## Initialize\b", text, re.M)) == 1
    # The first move is on the first screen: resolve the plugin root before
    # any command, and the harness facts that keep a weak model alive.
    assert "Resolve the plugin root" in text
    assert "Never type a bare `project-brain-*` command" in text
    # Every reference the skill names must exist on disk (the cold-read
    # contract: a dangling "read X" trigger sends a model hunting).
    refs_dir = PLUGIN_ROOT / "skills" / "brain" / "references"
    missing = sorted(name for name in REFERENCE_NAME_RE.findall(text)
                     if not (refs_dir / name).is_file())
    assert not missing, f"SKILL.md names references that do not exist: {missing}"
    # And the wiki-ledger section a post-compaction model needs is present,
    # with the 0.10.1 hook-aware semantics (undo needs no explicit rev).
    assert "Wiki ledger" in text
    assert "`diff <page>`" in text and "`restore <page>`" in text
    assert "restore <page> --rev <rev>" not in text  # --rev is optional now


def test_release_scenario_is_deterministic(run_script, tmp_path: Path):
    """Run the scenario's core twice in separate trees; the observable state
    (ledger subjects, lint categories) must be identical — no clocks, no
    network, no ordering hazards in the assertions above."""
    def build_and_measure(tmp: Path) -> tuple[list[str], set[str]]:
        tmp.mkdir(parents=True)
        root = tmp / "det"
        root.mkdir()
        sh(["git", "init", "-q", str(root)])
        sh(["git", "-C", str(root), "config", "user.email", "d@example.com"])
        sh(["git", "-C", str(root), "config", "user.name", "d"])
        (root / "README.md").write_text("# D\n\nline two here.\n", encoding="utf-8")
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(PLUGIN_ROOT),
                   PYTHON_BIN=sys.executable)
        r = sh(bin_cmd("init") + [str(root), "Det"], env=env)
        assert r.returncode == 0, r.stderr
        write_page(root, "concepts/X.md",
                   FILLER + 'Claim {{src README.md:9-9 "not there"}}.\n')
        _, issues = lint_json(root)
        cats = {i["category"] for i in issues if i["severity"] == "error"}
        sh(bin_cmd("wiki") + [str(root), "snapshot", "-m", "work: det"])
        # Subjects only: the human age column ("0s ago") is timing noise.
        subjects = [line.split(" ago  ", 1)[-1] for line in
                    sh(bin_cmd("wiki") + [str(root), "log", "10"]).stdout.splitlines()]
        return subjects, cats

    subjects_a, cats_a = build_and_measure(tmp_path / "a")
    subjects_b, cats_b = build_and_measure(tmp_path / "b")
    assert cats_a == cats_b
    assert subjects_a == subjects_b
    assert "work: det" in subjects_a[0]
