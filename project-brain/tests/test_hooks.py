"""Tests for the plugin-bundled awareness hooks (hooks/brain_hooks.py).

Covers: silent no-op without .brain, SessionStart context injection across
freshness states, PostToolUse throttle + dedupe (throttle BEFORE the git
cost), env opt-out, garbage payload, bounded output, harness detection, and
state-file location.
0.9.2: project-root walk-up (FIX 1), per-project bounded throttle state
(FIX 2), .brain/graphify-out edit immunity (FIX 3), CLAUDE_PLUGIN_DATA alone
is inconclusive (FIX 7), and doc guards for FIX 4/5/6/8/9 (wing-scoped search
recipes, older-diary note, watch extra, diary lock, wiki-wing scope).
Also guards the hook output shape against OpenClaude 0.33.0's
hookSpecificOutput union (src/types/hooks.ts:83-90, :100-106 — discriminator
key hookEventName), and the doc fixes: no nonexistent graphify subcommands in
docs, .brain/ excluded from the recommended .graphifyignore, no nonexistent
OPENCLAUDE env-var claim.
"""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
HOOK = PLUGIN_ROOT / "hooks" / "brain_hooks.py"
SKILLS_REFS = PLUGIN_ROOT / "skills" / "brain" / "references"

# Load the hook module directly so tests can read its named constants without
# duplicating values (state bounds etc.).
_SPEC = importlib.util.spec_from_file_location("brain_hooks_under_test", HOOK)
brain_hooks_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(brain_hooks_mod)

# hookSpecificOutput union keys, transcribed from OpenClaude 0.33.0
# src/types/hooks.ts:83-90 (SessionStart) and :100-106 (PostToolUse).
SCHEMA_KEYS = {
    "SessionStart": {"hookEventName", "additionalContext", "initialUserMessage", "watchPaths"},
    "PostToolUse": {"hookEventName", "additionalContext", "updatedMCPToolOutput"},
}

ISOLATED_ENV_KEYS = ("OPENCLAUDE_CONFIG_DIR", "CLAUDE_PLUGIN_DATA",
                     "PROJECT_BRAIN_HOOKS_DISABLED")


def base_env(**overrides: str) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ISOLATED_ENV_KEYS}
    env["CLAUDE_PLUGIN_DATA"] = str(overrides.pop("state_dir"))
    env.update(overrides)
    return env


def run_hook(args: list[str], payload: str, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOK)] + args,
        input=payload, capture_output=True, text=True, timeout=30, env=env,
    )


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True,
                          text=True, check=True).stdout


def _brain_repo_at(path: Path) -> Path:
    """Git repo with a .brain dir and a fresh graphify report at HEAD."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@example.com")
    _git(path, "config", "user.name", "t")
    (path / ".brain" / "wiki").mkdir(parents=True)
    (path / ".brain" / "state").mkdir(parents=True)
    (path / ".brain" / "wiki" / "index.md").write_text("# index\n", encoding="utf-8")
    (path / ".brain" / "state" / "session-brief.md").write_text("# brief\n", encoding="utf-8")
    (path / "a.py").write_text("x = 1\n", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-qm", "init")
    head = _git(path, "rev-parse", "HEAD").strip()
    out = path / "graphify-out"
    out.mkdir()
    (out / "GRAPH_REPORT.md").write_text(f"- Built from commit: `{head[:8]}`\n", encoding="utf-8")
    return path


def _make_stale(repo: Path) -> None:
    """Uncommitted source file newer than the graph report (stale graph)."""
    (repo / "new.py").write_text("y = 2\n", encoding="utf-8")
    report = repo / "graphify-out" / "GRAPH_REPORT.md"
    m = report.stat().st_mtime
    os.utime(repo / "new.py", (m + 10, m + 10))


@pytest.fixture
def brain_repo(tmp_path: Path) -> Path:
    """Git repo with a .brain dir and a fresh graphify report at HEAD."""
    return _brain_repo_at(tmp_path / "proj")


# --- session start ------------------------------------------------------------

def test_session_start_no_brain_is_silent(tmp_path: Path):
    env = base_env(state_dir=tmp_path / "state")
    r = run_hook(["session-start"], json.dumps({"cwd": str(tmp_path)}), env)
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_session_start_fresh_graph(brain_repo: Path, tmp_path: Path):
    env = base_env(state_dir=tmp_path / "state")
    r = run_hook(["session-start"], json.dumps({"cwd": str(brain_repo)}), env)
    assert r.returncode == 0
    out = json.loads(r.stdout)
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "session-brief.md" in ctx and "index.md" in ctx
    assert "fresh" in ctx


def test_hook_output_matches_openclaude_schema(brain_repo: Path, tmp_path: Path):
    """Both events must emit exactly the hookSpecificOutput variant keys from
    OpenClaude 0.33.0 src/types/hooks.ts:83-90 (SessionStart) and :100-106
    (PostToolUse): discriminator hookEventName + only the documented optional
    keys. Any other key (e.g. the old wrong "hookEvent") fails
    hookJSONOutputSchema and is demoted to a non_blocking_error instead of
    being injected (src/utils/hooks.ts:2703-2731).
    """
    env = base_env(state_dir=tmp_path / "state")
    for event, name in (("session-start", "SessionStart"), ("post-tool-use", "PostToolUse")):
        r = run_hook([event], json.dumps({"cwd": str(brain_repo)}), env)
        assert r.returncode == 0
        raw = r.stdout.strip()
        if not raw:  # post-tool-use on a fresh graph emits nothing
            assert event == "post-tool-use"
            continue
        out = json.loads(raw)
        assert set(out.keys()) == {"hookSpecificOutput"}
        spec = out["hookSpecificOutput"]
        assert set(spec.keys()) <= SCHEMA_KEYS[name], f"{event}: keys {set(spec.keys())} outside {name} variant"
        assert spec["hookEventName"] == name
        assert isinstance(spec["additionalContext"], str) and spec["additionalContext"]


def test_post_tool_use_output_event_name_matches(brain_repo: Path, tmp_path: Path):
    """The stale reminder must carry hookEventName 'PostToolUse' (the exact
    literal of the PostToolUse variant at src/types/hooks.ts:101)."""
    (brain_repo / "new.py").write_text("y = 2\n", encoding="utf-8")
    report = brain_repo / "graphify-out" / "GRAPH_REPORT.md"
    m = report.stat().st_mtime
    os.utime(brain_repo / "new.py", (m + 10, m + 10))
    env = base_env(state_dir=tmp_path / "state")
    r = run_hook(["post-tool-use"], json.dumps({"cwd": str(brain_repo)}), env)
    spec = json.loads(r.stdout)["hookSpecificOutput"]
    assert spec["hookEventName"] == "PostToolUse"
    assert set(spec.keys()) <= SCHEMA_KEYS["PostToolUse"]


def test_session_start_stale_after_commit_change(brain_repo: Path, tmp_path: Path):
    (brain_repo / "a.py").write_text("x = 2\n", encoding="utf-8")
    _git(brain_repo, "commit", "-aqm", "change")
    env = base_env(state_dir=tmp_path / "state")
    r = run_hook(["session-start"], json.dumps({"cwd": str(brain_repo)}), env)
    ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "STALE" in ctx
    assert "graph built at" in ctx


def test_session_start_garbage_payload_no_crash(tmp_path: Path):
    env = base_env(state_dir=tmp_path / "state")
    r = run_hook(["session-start"], "!!!not json!!!", env)
    assert r.returncode == 0
    assert r.stdout.strip() == ""  # no cwd derivable -> no .brain -> silent


def test_session_start_output_bounded(brain_repo: Path, tmp_path: Path):
    env = base_env(state_dir=tmp_path / "state")
    r = run_hook(["session-start"], json.dumps({"cwd": str(brain_repo)}), env)
    ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
    assert len(ctx) <= 700


# --- post tool use ------------------------------------------------------------

def test_post_tool_use_stale_reminds_then_throttles(brain_repo: Path, tmp_path: Path):
    (brain_repo / "new.py").write_text("y = 2\n", encoding="utf-8")
    report = brain_repo / "graphify-out" / "GRAPH_REPORT.md"
    m = report.stat().st_mtime
    os.utime(brain_repo / "new.py", (m + 10, m + 10))
    env = base_env(state_dir=tmp_path / "state")
    payload = json.dumps({"cwd": str(brain_repo), "tool_name": "Write"})
    first = run_hook(["post-tool-use"], payload, env)
    assert first.returncode == 0
    ctx = json.loads(first.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "mempalace_diary_write" in ctx and len(ctx) <= 700
    second = run_hook(["post-tool-use"], payload, env)
    assert second.returncode == 0
    assert second.stdout.strip() == ""  # throttled within interval


def test_post_tool_use_fresh_is_silent(brain_repo: Path, tmp_path: Path):
    env = base_env(state_dir=tmp_path / "state")
    r = run_hook(["post-tool-use"], json.dumps({"cwd": str(brain_repo)}), env)
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_post_tool_use_state_file_in_plugin_data(brain_repo: Path, tmp_path: Path):
    state_dir = tmp_path / "state"
    (brain_repo / "new.py").write_text("y = 2\n", encoding="utf-8")
    report = brain_repo / "graphify-out" / "GRAPH_REPORT.md"
    m = report.stat().st_mtime
    os.utime(brain_repo / "new.py", (m + 10, m + 10))
    env = base_env(state_dir=state_dir)
    run_hook(["post-tool-use"], json.dumps({"cwd": str(brain_repo)}), env)
    assert (state_dir / "project-brain-hooks-state.json").exists()


def test_post_tool_use_same_reason_dedupe_persists(brain_repo: Path, tmp_path: Path):
    state_dir = tmp_path / "state"
    _make_stale(brain_repo)
    env = base_env(state_dir=state_dir)
    payload = json.dumps({"cwd": str(brain_repo)})
    run_hook(["post-tool-use"], payload, env)
    # Push last-fire past the 300s interval but within the 1800s same-reason
    # window, in THIS project's v2 state entry.
    state_file = state_dir / "project-brain-hooks-state.json"
    state = json.loads(state_file.read_text(encoding="utf-8"))
    state["projects"][str(brain_repo)]["ts"] = time.time() - 400
    state_file.write_text(json.dumps(state), encoding="utf-8")
    r = run_hook(["post-tool-use"], payload, env)
    assert r.stdout.strip() == ""  # same reason, still deduped


def test_opt_out_env_disables_hooks(brain_repo: Path, tmp_path: Path):
    (brain_repo / "new.py").write_text("y = 2\n", encoding="utf-8")
    env = base_env(state_dir=tmp_path / "state", PROJECT_BRAIN_HOOKS_DISABLED="1")
    for event in ("session-start", "post-tool-use"):
        r = run_hook([event], json.dumps({"cwd": str(brain_repo)}), env)
        assert r.returncode == 0
        assert r.stdout.strip() == ""


# --- harness detection ----------------------------------------------------------

def test_harness_openclaude_config_dir(brain_repo: Path, tmp_path: Path):
    env = base_env(state_dir=tmp_path / "state", OPENCLAUDE_CONFIG_DIR=str(tmp_path / "oc"))
    r = run_hook(["session-start"], json.dumps({"cwd": str(brain_repo)}), env)
    assert "openclaude" in json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]


def test_harness_claude_code_via_transcript(brain_repo: Path, tmp_path: Path):
    env = base_env(state_dir=tmp_path / "state")
    payload = json.dumps({"cwd": str(brain_repo),
                          "transcript_path": "/home/u/.claude/projects/x/y.jsonl"})
    r = run_hook(["session-start"], payload, env)
    assert "claude-code" in json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]


# --- doc-fix regressions ---------------------------------------------------------

def test_docs_do_not_reference_nonexistent_graphify_commands():
    for md in SKILLS_REFS.glob("*.md"):
        text = md.read_text(encoding="utf-8")
        # Only flag backtick-quoted command usage; prose like
        # "graphify report older than 14 days" refers to the report file.
        assert "`graphify build`" not in text, f"{md.name}: `graphify build` does not exist"
        assert "`graphify report" not in text, f"{md.name}: `graphify report` does not exist"


def test_install_doc_excludes_brain_from_graph():
    text = (SKILLS_REFS / "install-and-integration.md").read_text(encoding="utf-8")
    assert ".brain/\ngraphify-out/" in text
    assert "Do not ignore `.brain/wiki/`" not in text


def test_post_tool_use_throttled_skips_git(brain_repo: Path, tmp_path: Path):
    """FIX 2: inside the interval throttle the hook must return BEFORE any git
    subprocess starts. Proven with a fake `git` earlier on PATH that records
    every invocation; the throttled second run must add zero calls."""
    (brain_repo / "new.py").write_text("y = 2\n", encoding="utf-8")
    report = brain_repo / "graphify-out" / "GRAPH_REPORT.md"
    m = report.stat().st_mtime
    os.utime(brain_repo / "new.py", (m + 10, m + 10))

    real_git = shutil.which("git")
    assert real_git, "git must be installed for this test"
    fake_bin = tmp_path / "fakebin"
    fake_bin.mkdir()
    git_log = tmp_path / "git-calls.log"
    fake_git = fake_bin / "git"
    fake_git.write_text(
        f'#!/bin/sh\necho "$@" >> "{git_log}"\nexec {real_git} "$@"\n'
    )
    fake_git.chmod(0o755)

    env = base_env(state_dir=tmp_path / "state")
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    payload = json.dumps({"cwd": str(brain_repo), "tool_name": "Write"})

    first = run_hook(["post-tool-use"], payload, env)
    assert first.returncode == 0
    spec = json.loads(first.stdout)["hookSpecificOutput"]
    assert spec["hookEventName"] == "PostToolUse"
    calls_unthrottled = git_log.read_text(encoding="utf-8").count("\n")
    assert calls_unthrottled > 0  # sanity: the unthrottled run did consult git

    second = run_hook(["post-tool-use"], payload, env)
    assert second.returncode == 0
    assert second.stdout.strip() == ""  # throttled
    calls_throttled = git_log.read_text(encoding="utf-8").count("\n")
    assert calls_throttled == calls_unthrottled  # zero git calls while throttled


def test_hooks_json_command_survives_space_in_plugin_path(brain_repo: Path, tmp_path: Path):
    """FIX 5: OpenClaude substitutes ${CLAUDE_PLUGIN_ROOT} into the command
    string textually and runs it through a shell (src/utils/hooks.ts:1035;
    spawn with shell at :1155/:1165). The quoted path in hooks.json must
    survive a plugin install path containing a space — and the unquoted form
    must demonstrably fail, so the quoting is load-bearing."""
    spaced_root = tmp_path / "plug ins"
    (spaced_root / "hooks").mkdir(parents=True)
    (spaced_root / "scripts").mkdir()
    shutil.copytree(PLUGIN_ROOT / "hooks", spaced_root / "hooks", dirs_exist_ok=True)
    shutil.copy2(PLUGIN_ROOT / "scripts" / "doctor.py", spaced_root / "scripts" / "doctor.py")

    hooks_json = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    cmd = hooks_json["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert '"${CLAUDE_PLUGIN_ROOT}' in cmd  # the fix: path is quoted
    final_cmd = cmd.replace("${CLAUDE_PLUGIN_ROOT}", str(spaced_root))

    env = base_env(state_dir=tmp_path / "state")
    r = subprocess.run(
        ["/bin/bash", "-c", final_cmd],
        input=json.dumps({"cwd": str(brain_repo)}),
        capture_output=True, text=True, timeout=30, env=env,
    )
    assert r.returncode == 0
    spec = json.loads(r.stdout)["hookSpecificOutput"]
    assert spec["hookEventName"] == "SessionStart"

    # Control: without the quotes the same command word-splits and fails.
    unquoted = final_cmd.replace(f'"{spaced_root}/hooks/brain_hooks.py"', f"{spaced_root}/hooks/brain_hooks.py")
    r2 = subprocess.run(
        ["/bin/bash", "-c", unquoted],
        input=json.dumps({"cwd": str(brain_repo)}),
        capture_output=True, text=True, timeout=30, env=env,
    )
    assert r2.returncode != 0 or r2.stdout.strip() == ""


def test_harness_doc_has_no_openclaude_env_var_claim():
    text = (SKILLS_REFS / "harness-detection.md").read_text(encoding="utf-8")
    assert "the `OPENCLAUDE` environment variable is set" not in text


# --- 0.9.2 FIX 1: resolve_root walks up to the nearest .brain ------------------

def test_session_start_from_subdirectory_finds_brain(brain_repo: Path, tmp_path: Path):
    """FIX 1: a session two levels below the project root still finds .brain
    and reports the brain's real freshness."""
    deep = brain_repo / "src" / "pkg"
    deep.mkdir(parents=True)
    env = base_env(state_dir=tmp_path / "state")
    r = run_hook(["session-start"], json.dumps({"cwd": str(deep)}), env)
    assert r.returncode == 0
    ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "fresh" in ctx  # brain found from two levels down


def test_post_tool_use_from_subdirectory_reminds(brain_repo: Path, tmp_path: Path):
    deep = brain_repo / "src" / "pkg"
    deep.mkdir(parents=True)
    _make_stale(brain_repo)
    env = base_env(state_dir=tmp_path / "state")
    payload = json.dumps({"cwd": str(deep), "tool_name": "Write",
                          "tool_input": {"file_path": str(brain_repo / "a.py")}})
    r = run_hook(["post-tool-use"], payload, env)
    spec = json.loads(r.stdout)["hookSpecificOutput"]
    assert spec["hookEventName"] == "PostToolUse"
    assert "source changed" in spec["additionalContext"]


def test_no_brain_anywhere_stays_silent(tmp_path: Path):
    """FIX 1: no .brain in any ancestor -> still a silent no-op."""
    deep = tmp_path / "plain" / "src" / "pkg"
    deep.mkdir(parents=True)
    (deep / "code.py").write_text("x = 1\n", encoding="utf-8")
    env = base_env(state_dir=tmp_path / "state")
    for event in ("session-start", "post-tool-use"):
        payload = json.dumps({"cwd": str(deep), "tool_name": "Write",
                              "tool_input": {"file_path": str(deep / "code.py")}})
        r = run_hook([event], payload, env)
        assert r.returncode == 0
        assert r.stdout.strip() == ""


def test_nested_brain_nearest_wins(tmp_path: Path):
    """FIX 1: with nested .brain directories the nearest ancestor wins —
    proven by freshness: the inner project is fresh, the outer is stale."""
    outer = tmp_path / "outer"
    inner = outer / "inner"
    (outer / ".brain").mkdir(parents=True)
    _brain_repo_at(inner)  # fresh report at HEAD
    deeper = inner / "deeper"
    deeper.mkdir()
    env = base_env(state_dir=tmp_path / "state")
    r = run_hook(["session-start"], json.dumps({"cwd": str(deeper)}), env)
    ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "fresh" in ctx  # inner (nearest) brain, not the stale outer one
    r2 = run_hook(["session-start"], json.dumps({"cwd": str(outer / "deeper2")}), env)
    ctx2 = json.loads(r2.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "STALE" in ctx2  # outside inner, the outer brain applies


# --- 0.9.2 FIX 2: per-project bounded throttle state ---------------------------

def test_throttle_state_is_per_project(tmp_path: Path):
    """FIX 2: a reminder in project A must not suppress project B (shared
    state file); the interval still holds within one project."""
    a = _brain_repo_at(tmp_path / "a")
    b = _brain_repo_at(tmp_path / "b")
    _make_stale(a)
    _make_stale(b)
    env = base_env(state_dir=tmp_path / "state")
    pa = json.dumps({"cwd": str(a), "tool_name": "Write",
                     "tool_input": {"file_path": str(a / "a.py")}})
    pb = json.dumps({"cwd": str(b), "tool_name": "Write",
                     "tool_input": {"file_path": str(b / "a.py")}})
    ra = run_hook(["post-tool-use"], pa, env)
    assert json.loads(ra.stdout)["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    rb = run_hook(["post-tool-use"], pb, env)
    assert json.loads(rb.stdout)["hookSpecificOutput"]["hookEventName"] == "PostToolUse"  # not suppressed
    ra2 = run_hook(["post-tool-use"], pa, env)
    assert ra2.stdout.strip() == ""  # interval still holds inside project A


def test_legacy_state_file_tolerated(brain_repo: Path, tmp_path: Path):
    """FIX 2: a legacy flat state file (0.9.x format) must not crash and must
    not suppress the reminder; the next fire rewrites it to v2."""
    _make_stale(brain_repo)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    state_file = state_dir / "project-brain-hooks-state.json"
    state_file.write_text(json.dumps({
        "post_tool_use_ts": time.time(),
        "post_tool_use_sig": "graphify-out/GRAPH_REPORT.md missing",
    }), encoding="utf-8")
    env = base_env(state_dir=state_dir)
    r = run_hook(["post-tool-use"], json.dumps({"cwd": str(brain_repo)}), env)
    assert r.returncode == 0
    spec = json.loads(r.stdout)["hookSpecificOutput"]  # no crash, not suppressed
    assert spec["hookEventName"] == "PostToolUse"
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["version"] == brain_hooks_mod.STATE_FORMAT_VERSION
    assert str(brain_repo) in state["projects"]


def test_state_project_bound_prunes_oldest(brain_repo: Path, tmp_path: Path):
    """FIX 2: tracked projects are bounded to MAX_TRACKED_PROJECTS; the
    oldest entries by timestamp are dropped first, the newest kept."""
    _make_stale(brain_repo)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    n = brain_hooks_mod.MAX_TRACKED_PROJECTS + 3
    projects = {f"/phantom/project{i}": {"ts": float(i), "sig": "s"} for i in range(n)}
    (state_dir / "project-brain-hooks-state.json").write_text(
        json.dumps({"projects": projects}), encoding="utf-8")
    env = base_env(state_dir=state_dir)
    r = run_hook(["post-tool-use"], json.dumps({"cwd": str(brain_repo)}), env)
    assert r.returncode == 0
    state = json.loads((state_dir / "project-brain-hooks-state.json").read_text(encoding="utf-8"))
    assert len(state["projects"]) == brain_hooks_mod.MAX_TRACKED_PROJECTS
    assert "/phantom/project0" not in state["projects"]  # oldest dropped
    assert str(brain_repo) in state["projects"]  # newest kept


# --- 0.9.2 FIX 3: .brain/ and graphify-out/ edits are reminder-immune ----------

def test_wiki_edit_silent_even_when_stale(brain_repo: Path, tmp_path: Path):
    """FIX 3: editing .brain/wiki/x.md is the remedy, not a trigger — silent
    even though the graph is stale. Absolute and relative paths both work."""
    _make_stale(brain_repo)
    (brain_repo / ".brain" / "wiki" / "x.md").write_text("# x\n", encoding="utf-8")
    env = base_env(state_dir=tmp_path / "state")
    abs_payload = json.dumps({"cwd": str(brain_repo), "tool_name": "Write",
                              "tool_input": {"file_path": str(brain_repo / ".brain" / "wiki" / "x.md")}})
    r = run_hook(["post-tool-use"], abs_payload, env)
    assert r.returncode == 0
    assert r.stdout.strip() == ""
    rel_payload = json.dumps({"cwd": str(brain_repo), "tool_name": "Edit",
                              "tool_input": {"file_path": ".brain/wiki/x.md"}})
    r2 = run_hook(["post-tool-use"], rel_payload, env)
    assert r2.stdout.strip() == ""


def test_graphify_out_edit_silent_even_when_stale(brain_repo: Path, tmp_path: Path):
    _make_stale(brain_repo)
    env = base_env(state_dir=tmp_path / "state")
    payload = json.dumps({"cwd": str(brain_repo), "tool_name": "Write",
                          "tool_input": {"file_path": str(brain_repo / "graphify-out" / "GRAPH_REPORT.md")}})
    r = run_hook(["post-tool-use"], payload, env)
    assert r.stdout.strip() == ""


def test_notebook_path_key_respected(brain_repo: Path, tmp_path: Path):
    """FIX 3: notebook_path (NotebookEditTool, NotebookEditTool.ts:32) is read
    when file_path is absent."""
    _make_stale(brain_repo)
    env = base_env(state_dir=tmp_path / "state")
    payload = json.dumps({"cwd": str(brain_repo), "tool_name": "NotebookEdit",
                          "tool_input": {"notebook_path": str(brain_repo / ".brain" / "wiki" / "x.ipynb")}})
    r = run_hook(["post-tool-use"], payload, env)
    assert r.stdout.strip() == ""


def test_source_edit_with_tool_input_still_reminds(brain_repo: Path, tmp_path: Path):
    """FIX 3: immunity is scoped to .brain/ and graphify-out/ only; a source
    file path in tool_input still reminds."""
    _make_stale(brain_repo)
    env = base_env(state_dir=tmp_path / "state")
    payload = json.dumps({"cwd": str(brain_repo), "tool_name": "Edit",
                          "tool_input": {"file_path": str(brain_repo / "a.py")}})
    r = run_hook(["post-tool-use"], payload, env)
    spec = json.loads(r.stdout)["hookSpecificOutput"]
    assert "source changed" in spec["additionalContext"]


def test_payload_without_tool_input_still_reminds(brain_repo: Path, tmp_path: Path):
    """FIX 3: no path readable -> current behavior (may remind)."""
    _make_stale(brain_repo)
    env = base_env(state_dir=tmp_path / "state")
    r = run_hook(["post-tool-use"], json.dumps({"cwd": str(brain_repo), "tool_name": "Write"}), env)
    spec = json.loads(r.stdout)["hookSpecificOutput"]
    assert "source changed" in spec["additionalContext"]


def test_brain_edit_outside_project_still_reminds(brain_repo: Path, tmp_path: Path):
    """FIX 3: a .brain path OUTSIDE the project root is not immune (defensive
    edge: relative resolution stays inside the project root)."""
    _make_stale(brain_repo)
    env = base_env(state_dir=tmp_path / "state")
    payload = json.dumps({"cwd": str(brain_repo), "tool_name": "Write",
                          "tool_input": {"file_path": str(tmp_path / "other" / ".brain" / "wiki" / "x.md")}})
    r = run_hook(["post-tool-use"], payload, env)
    spec = json.loads(r.stdout)["hookSpecificOutput"]
    assert "source changed" in spec["additionalContext"]


# --- 0.9.2 FIX 7: CLAUDE_PLUGIN_DATA alone is inconclusive ---------------------

def test_plugin_data_alone_labels_unknown(brain_repo: Path, tmp_path: Path):
    """FIX 7: CLAUDE_PLUGIN_DATA is set by BOTH harnesses (OpenClaude
    src/utils/hooks.ts:1038; Claude Code ~/.claude/plugins/data/<id>/), so
    alone it must label "unknown" — the old "openclaude-compatible" claim is
    gone."""
    env = base_env(state_dir=tmp_path / "state")  # sets CLAUDE_PLUGIN_DATA only
    r = run_hook(["session-start"], json.dumps({"cwd": str(brain_repo)}), env)
    ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "harness: unknown" in ctx
    assert "openclaude-compatible" not in ctx


def test_openclaude_transcript_wins_over_plugin_data(brain_repo: Path, tmp_path: Path):
    env = base_env(state_dir=tmp_path / "state")
    payload = json.dumps({"cwd": str(brain_repo),
                          "transcript_path": "/home/u/.openclaude/projects/x/y.jsonl"})
    r = run_hook(["session-start"], payload, env)
    ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "harness: openclaude" in ctx


def test_hook_source_has_no_openclaude_compatible_label():
    text = HOOK.read_text(encoding="utf-8")
    assert "openclaude-compatible" not in text


def test_harness_doc_marks_plugin_data_inconclusive():
    """FIX 7: the doc must not list CLAUDE_PLUGIN_DATA as an OpenClaude
    signal and must state it is inconclusive."""
    text = (SKILLS_REFS / "harness-detection.md").read_text(encoding="utf-8")
    assert "INCONCLUSIVE" in text
    assert "`CLAUDE_PLUGIN_DATA` is set (OpenClaude sets it" not in text


# --- 0.9.2 FIX 4/5/6/8/9: doc guards -------------------------------------------

def test_docs_mempalace_search_recipes_pass_wing():
    """FIX 4: every fenced mempalace_search recipe in the docs must pass a
    wing — a wingless search scans the whole palace, other projects included."""
    for md in PLUGIN_ROOT.glob("skills/**/*.md"):
        text = md.read_text(encoding="utf-8")
        for block in re.findall(r"```[a-zA-Z]*\n(.*?)```", text, re.S):
            if "mempalace_search(" in block:
                assert re.search(r"\bwing\b", block), f"{md.name}: mempalace_search recipe without wing"


def test_workflow_doc_has_diary_lock_rule_and_wiki_wing_scope():
    """FIX 8 + FIX 9: the diary-lock exception and the wiki-only scope of
    mempalace_wing are documented, with the older-diary subsection (FIX 5)."""
    wf = (SKILLS_REFS / "mempalace-workflow.md").read_text(encoding="utf-8")
    assert "retry ONCE" in wf
    assert "Diary writes and the palace lock" in wf
    assert "applies to wiki mining and wiki search only" in wf
    assert "Existing brains: older diary entries" in wf
    tools = (SKILLS_REFS / "mempalace-tools.md").read_text(encoding="utf-8")
    assert 'wing: "wiki-<project-slug>"' in tools
    assert "Diary writes and the palace lock" in wf  # cross-referenced from tools


def test_graphify_doc_documents_watch_extra():
    """FIX 6: the optional watch extra is documented next to watch mode."""
    text = (SKILLS_REFS / "graphify-workflow.md").read_text(encoding="utf-8")
    assert "graphifyy[watch]" in text


def test_scaffold_generated_mempalace_namespace(tmp_path: Path):
    """FIX 4 + FIX 5: the generated .brain/CLAUDE.md scopes search to the wiki
    wing, names the diary read recipe, and points to the older-diary note."""
    script = PLUGIN_ROOT / "scripts" / "scaffold_brain.py"
    proj = tmp_path / "scaffold-proj"
    proj.mkdir()
    r = subprocess.run([sys.executable, str(script), str(proj), "Scaffold Proj"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    text = (proj / ".brain" / "CLAUDE.md").read_text(encoding="utf-8")
    assert 'wing: "wiki-scaffold-proj"' in text
    assert "mempalace_diary_read" in text
    assert "older" in text and "diary entries" in text
