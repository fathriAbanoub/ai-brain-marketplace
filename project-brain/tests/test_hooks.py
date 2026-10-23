"""Tests for the plugin-bundled awareness hooks (hooks/brain_hooks.py).

Covers: silent no-op without .brain, SessionStart context injection across
freshness states, PostToolUse throttle + dedupe (throttle BEFORE the git
cost), env opt-out, garbage payload, bounded output, harness detection, and
state-file location.
Also guards the hook output shape against OpenClaude 0.33.0's
hookSpecificOutput union (src/types/hooks.ts:83-90, :100-106 — discriminator
key hookEventName), and the doc fixes: no nonexistent graphify subcommands in
docs, .brain/ excluded from the recommended .graphifyignore, no nonexistent
OPENCLAUDE env-var claim.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
HOOK = PLUGIN_ROOT / "hooks" / "brain_hooks.py"
SKILLS_REFS = PLUGIN_ROOT / "skills" / "brain" / "references"

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


@pytest.fixture
def brain_repo(tmp_path: Path) -> Path:
    """Git repo with a .brain dir and a fresh graphify report at HEAD."""
    root = tmp_path / "proj"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    (root / ".brain" / "wiki").mkdir(parents=True)
    (root / ".brain" / "state").mkdir(parents=True)
    (root / ".brain" / "wiki" / "index.md").write_text("# index\n", encoding="utf-8")
    (root / ".brain" / "state" / "session-brief.md").write_text("# brief\n", encoding="utf-8")
    (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "init")
    head = _git(root, "rev-parse", "HEAD").strip()
    out = root / "graphify-out"
    out.mkdir()
    (out / "GRAPH_REPORT.md").write_text(f"- Built from commit: `{head[:8]}`\n", encoding="utf-8")
    return root


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
    (brain_repo / "new.py").write_text("y = 2\n", encoding="utf-8")
    report = brain_repo / "graphify-out" / "GRAPH_REPORT.md"
    m = report.stat().st_mtime
    os.utime(brain_repo / "new.py", (m + 10, m + 10))
    env = base_env(state_dir=state_dir)
    payload = json.dumps({"cwd": str(brain_repo)})
    run_hook(["post-tool-use"], payload, env)
    # Push last-fire past the 300s interval but within the 1800s same-reason window.
    state_file = state_dir / "project-brain-hooks-state.json"
    state = json.loads(state_file.read_text(encoding="utf-8"))
    import time as _time
    state["post_tool_use_ts"] = _time.time() - 400
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
