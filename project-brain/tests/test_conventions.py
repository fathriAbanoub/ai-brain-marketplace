"""Tests for wing naming, .graphifyignore handling, graphify gating, and tool-list drift."""

import re
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from scaffold_brain import (  # noqa: E402
    BRAIN_DIARY_PREFIX,
    WIKI_WING_PREFIX,
    ensure_graphifyignore,
    sanitize_wing_name,
    wiki_wing_name,
)
from doctor import graphify_freshness  # noqa: E402

TOOLS_DOC = PLUGIN_ROOT / "skills" / "brain" / "references" / "mempalace-tools.md"

# The 47-tool list, taken from the reference table itself.
TOOL_ROW_RE = re.compile(r"^\| ([a-z][a-z0-9_]+) \|", re.MULTILINE)
TOOL_CALL_RE = re.compile(r"\bmempalace_([a-z][a-z0-9_]+)\b")

# Identifiers that look like tool names but are fields, functions, or paths.
NON_TOOL_IDENTIFIERS = {
    "wing",
    "wing_check",
    "bin",
    "cache",
    "preferences_get",
    "preferences_set",
}


def documented_tools() -> set[str]:
    return set(TOOL_ROW_RE.findall(TOOLS_DOC.read_text(encoding="utf-8")))


# --- item 3: wing naming ----------------------------------------------------


def test_wing_constants():
    assert WIKI_WING_PREFIX == "wiki-"
    assert BRAIN_DIARY_PREFIX == "brain-"


def test_wiki_wing_name_uses_prefix_and_slug():
    assert wiki_wing_name("Test Project") == "wiki-test-project"
    assert wiki_wing_name("Ambient Studio") == "wiki-ambient-studio"


def test_wiki_wing_name_matches_sanitize():
    for raw in ("My Cool Project", "Projet Émoji 🚀", "  Weird -- Name  "):
        assert wiki_wing_name(raw) == WIKI_WING_PREFIX + sanitize_wing_name(raw)


# --- item 5: ensure_graphifyignore ------------------------------------------


def test_graphifyignore_creates_file(tmp_path: Path):
    ensure_graphifyignore(tmp_path)
    lines = (tmp_path / ".graphifyignore").read_text(encoding="utf-8").splitlines()
    assert ".brain/" in lines and "graphify-out/" in lines


def test_graphifyignore_adds_newline_before_appending(tmp_path: Path):
    p = tmp_path / ".graphifyignore"
    p.write_text("node_modules/", encoding="utf-8")
    ensure_graphifyignore(tmp_path)
    lines = p.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "node_modules/"
    assert ".brain/" in lines and "graphify-out/" in lines


def test_graphifyignore_idempotent_and_slash_insensitive(tmp_path: Path):
    p = tmp_path / ".graphifyignore"
    p.write_text(".brain/\ngraphify-out\n", encoding="utf-8")
    ensure_graphifyignore(tmp_path)
    assert p.read_text(encoding="utf-8") == ".brain/\ngraphify-out\n"
    # Second call must also be a no-op.
    ensure_graphifyignore(tmp_path)
    assert p.read_text(encoding="utf-8") == ".brain/\ngraphify-out\n"


# --- item 6: graphify gate ---------------------------------------------------


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "init")
    return root


def _write_report(root: Path, commit: str) -> None:
    out = root / "graphify-out"
    out.mkdir(exist_ok=True)
    # Use the real graphify format: bullet + "Built from commit:" + short hash in backticks.
    (out / "GRAPH_REPORT.md").write_text(
        f"- Built from commit: `{commit[:8]}`\n", encoding="utf-8"
    )


def test_gate_stale_when_no_graph(git_repo: Path):
    status, reason = graphify_freshness(git_repo)
    assert status == "stale"
    assert "missing" in reason


def test_gate_fresh_when_commit_unchanged(git_repo: Path):
    head = _git(git_repo, "rev-parse", "HEAD").strip()
    _write_report(git_repo, head)
    status, reason = graphify_freshness(git_repo)
    assert status == "fresh", reason


def test_gate_stale_when_commit_changed(git_repo: Path):
    head = _git(git_repo, "rev-parse", "HEAD").strip()
    _write_report(git_repo, head)
    (git_repo / "a.txt").write_text("b\n", encoding="utf-8")
    _git(git_repo, "commit", "-qam", "change")
    status, reason = graphify_freshness(git_repo)
    assert status == "stale"
    assert "HEAD" in reason or "graph built at" in reason


def test_gate_stale_with_dirty_tree(git_repo: Path):
    head = _git(git_repo, "rev-parse", "HEAD").strip()
    _write_report(git_repo, head)
    # Modify a tracked file without committing.
    (git_repo / "a.txt").write_text("dirty\n", encoding="utf-8")
    status, reason = graphify_freshness(git_repo)
    assert status == "stale"
    assert "uncommitted" in reason


def test_gate_stale_with_no_commit_line(git_repo: Path):
    out = git_repo / "graphify-out"
    out.mkdir()
    (out / "GRAPH_REPORT.md").write_text("# Report\nNo commit info here.\n", encoding="utf-8")
    status, reason = graphify_freshness(git_repo)
    assert status == "stale"
    assert "Built from commit" in reason


# --- item 8: no undocumented MemPalace tool references ----------------------


def test_reference_table_has_47_tools():
    assert len(documented_tools()) == 47


def test_no_plugin_file_references_unknown_tool():
    known = documented_tools()
    offenders = []
    for path in PLUGIN_ROOT.rglob("*"):
        if path.is_dir() or path.suffix not in {".md", ".py", ".json"}:
            continue
        if "tests" in path.parts:
            continue
        for name in TOOL_CALL_RE.findall(path.read_text(encoding="utf-8", errors="replace")):
            if name in NON_TOOL_IDENTIFIERS:
                continue
            if name not in known:
                offenders.append(f"{path.relative_to(PLUGIN_ROOT)}: mempalace_{name}")
    assert not offenders, "Undocumented MemPalace tools referenced:\n" + "\n".join(offenders)