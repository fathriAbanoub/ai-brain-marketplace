"""Tests for wing naming, .graphifyignore handling, graphify gating, and tool-list drift."""

import json
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
    import time
    time.sleep(0.01)
    (git_repo / "a.txt").write_text("dirty\n", encoding="utf-8")
    status, reason = graphify_freshness(git_repo)
    assert status == "stale"
    assert "uncommitted" in reason
    assert "a.txt" in reason


def test_gate_stale_with_no_commit_line(git_repo: Path):
    out = git_repo / "graphify-out"
    out.mkdir()
    (out / "GRAPH_REPORT.md").write_text("# Report\nNo commit info here.\n", encoding="utf-8")
    status, reason = graphify_freshness(git_repo)
    assert status == "stale"
    assert "Built from commit" in reason


def test_gate_stale_with_new_untracked_source_file(git_repo: Path):
    head = _git(git_repo, "rev-parse", "HEAD").strip()
    _write_report(git_repo, head)
    # New untracked source file — graphify indexes it, so the graph is stale.
    (git_repo / "new_module.py").write_text("x = 1\n", encoding="utf-8")
    status, reason = graphify_freshness(git_repo)
    assert status == "stale"
    assert "uncommitted" in reason


def test_gate_fresh_with_untracked_brain_file(git_repo: Path):
    head = _git(git_repo, "rev-parse", "HEAD").strip()
    _write_report(git_repo, head)
    # Untracked file under .brain/ — excluded from graph, so still fresh.
    brain = git_repo / ".brain"
    brain.mkdir()
    (brain / "note.md").write_text("notes\n", encoding="utf-8")
    status, reason = graphify_freshness(git_repo)
    assert status == "fresh", reason


def test_gate_fresh_with_tracked_brain_edit(git_repo: Path):
    # Track a .brain/ file, then edit it — should still be fresh.
    brain = git_repo / ".brain"
    brain.mkdir()
    page = brain / "page.md"
    page.write_text("v1\n", encoding="utf-8")
    _git(git_repo, "add", ".")
    _git(git_repo, "commit", "-qm", "add brain page")
    head = _git(git_repo, "rev-parse", "HEAD").strip()
    _write_report(git_repo, head)
    page.write_text("v2\n", encoding="utf-8")  # tracked edit, not committed
    status, reason = graphify_freshness(git_repo)
    assert status == "fresh", reason


def test_gate_fresh_with_tracked_graphify_out_edit(git_repo: Path):
    # Track graphify-out/, rewrite GRAPH_REPORT.md — should still be fresh.
    out = git_repo / "graphify-out"
    out.mkdir()
    report = out / "GRAPH_REPORT.md"
    head = _git(git_repo, "rev-parse", "HEAD").strip()
    report.write_text(f"- Built from commit: `{head[:8]}`\n", encoding="utf-8")
    _git(git_repo, "add", ".")
    _git(git_repo, "commit", "-qm", "add graphify-out")
    head = _git(git_repo, "rev-parse", "HEAD").strip()
    # Rewrite the report to current HEAD (simulating a fresh graphify run).
    report.write_text(f"- Built from commit: `{head[:8]}`\n", encoding="utf-8")
    status, reason = graphify_freshness(git_repo)
    assert status == "fresh", reason


def test_gate_stale_with_tracked_source_edit(git_repo: Path):
    head = _git(git_repo, "rev-parse", "HEAD").strip()
    _write_report(git_repo, head)
    # Edit a tracked source file without committing.
    import time
    time.sleep(0.01)
    (git_repo / "a.txt").write_text("modified\n", encoding="utf-8")
    status, reason = graphify_freshness(git_repo)
    assert status == "stale"
    assert "uncommitted" in reason


def test_gate_fresh_after_graphify_with_newer_report(git_repo: Path):
    # Edit a source file, then rebuild the graph. Report mtime should be newer than source.
    head = _git(git_repo, "rev-parse", "HEAD").strip()
    _write_report(git_repo, head)
    (git_repo / "a.txt").write_text("edited\n", encoding="utf-8")
    # Simulate graphify rebuild: rewrite report with newer mtime.
    import time
    time.sleep(0.01)
    _write_report(git_repo, head)
    status, reason = graphify_freshness(git_repo)
    assert status == "fresh", reason


def test_gate_stale_with_edit_after_report(git_repo: Path):
    # Build graph, then edit a source file after the report mtime.
    head = _git(git_repo, "rev-parse", "HEAD").strip()
    _write_report(git_repo, head)
    import time
    time.sleep(0.01)
    (git_repo / "a.txt").write_text("newer\n", encoding="utf-8")
    status, reason = graphify_freshness(git_repo)
    assert status == "stale"
    assert "uncommitted" in reason


def test_gate_fresh_with_wiki_only_edit(git_repo: Path):
    # Edit a .brain/ file after the report — should still be fresh.
    head = _git(git_repo, "rev-parse", "HEAD").strip()
    _write_report(git_repo, head)
    brain = git_repo / ".brain"
    brain.mkdir()
    wiki = brain / "wiki.md"
    wiki.write_text("old\n", encoding="utf-8")
    import time
    time.sleep(0.01)
    wiki.write_text("new\n", encoding="utf-8")
    status, reason = graphify_freshness(git_repo)
    assert status == "fresh", reason


def test_gate_stale_with_new_edit_after_fresh(git_repo: Path):
    # Build graph, edit source (stale), rebuild graph (fresh), edit again (stale).
    head = _git(git_repo, "rev-parse", "HEAD").strip()
    _write_report(git_repo, head)
    (git_repo / "a.txt").write_text("v1\n", encoding="utf-8")
    import time
    time.sleep(0.01)
    _write_report(git_repo, head)
    time.sleep(0.01)
    (git_repo / "a.txt").write_text("v2\n", encoding="utf-8")
    status, reason = graphify_freshness(git_repo)
    assert status == "stale"
    assert "uncommitted" in reason


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


# --- item B3: tools doc args match fixture ----------------------------------

FIXTURE_PATH = PLUGIN_ROOT / "tests" / "fixtures" / "mcp-tools-3.11.0.json"

# Regex to extract arguments cell from the table rows:
# | tool_name | description | <args cell> | access | policy |
TABLE_ROW_RE = re.compile(
    r"^\| ([a-z][a-z0-9_]+) \| [^|]* \| ([^|]*) \| [^|]* \| [^|]* \|",
    re.MULTILINE,
)
# Strip bold markers from required args like **wing?**
BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
# Strip trailing ? from arg names
ARG_NAME_RE = re.compile(r"([a-z][a-z0-9_]*)(\?)?")


def _parse_args_cell(cell: str) -> tuple[set[str], set[str]]:
    """Return (required_args, optional_args) from a table cell."""
    required: set[str] = set()
    optional: set[str] = set()
    # bold = required
    for bold in BOLD_RE.findall(cell):
        name = bold.rstrip("?")
        required.add(name)
    # remove bold spans then scan remaining arg tokens
    remainder = BOLD_RE.sub("", cell)
    for m in ARG_NAME_RE.finditer(remainder):
        name = m.group(1)
        if name in ("none",):
            continue
        optional.add(name)
    return required, optional


def _check_args_match(doc_text: str, fixture: dict, tool_name: str, cell: str) -> list[str]:
    """Check if documented args match fixture. Returns list of mismatches."""
    if tool_name not in fixture:
        return [f"{tool_name}: in doc but not in fixture"]

    fix = fixture[tool_name]
    fix_required = set(fix["required"])
    fix_props = set(fix["properties"])

    doc_required, doc_optional = _parse_args_cell(cell)
    doc_all = doc_required | doc_optional

    mismatches: list[str] = []

    # Every required arg in fixture must be bold in doc
    missing_required = fix_required - doc_required
    if missing_required:
        mismatches.append(f"{tool_name}: fixture required {sorted(missing_required)} not bold in doc")

    # No optional arg in fixture should be bold in doc
    bold_optional = doc_required - fix_required
    if bold_optional:
        mismatches.append(f"{tool_name}: doc bolds optional args {sorted(bold_optional)}")

    # Every fixture property must appear somewhere in doc args
    missing_props = fix_props - doc_all
    if missing_props:
        mismatches.append(f"{tool_name}: fixture props {sorted(missing_props)} missing from doc")

    # No doc arg that isn't in fixture (catches stale args)
    extra = doc_all - fix_props - fix_required
    if extra:
        mismatches.append(f"{tool_name}: doc args {sorted(extra)} not in fixture")

    return mismatches


def test_tools_doc_args_match_fixture():
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    doc_text = TOOLS_DOC.read_text(encoding="utf-8")
    mismatches: list[str] = []

    for tool_name, cell in TABLE_ROW_RE.findall(doc_text):
        mismatches.extend(_check_args_match(doc_text, fixture, tool_name, cell))

    assert not mismatches, "Tool doc args drift from fixture:\n" + "\n".join(mismatches)


def test_bold_optional_arg_detected():
    """Verify that bolding an optional arg in doc is caught as a mismatch."""
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    # diary_read has last_n as optional in fixture
    assert "diary_read" in fixture
    assert "last_n" in fixture["diary_read"]["properties"]
    assert "last_n" not in fixture["diary_read"]["required"]

    # Simulate bolding last_n in the doc
    fake_cell = "**agent_name**, **last_n?**, topic?"
    mismatches = _check_args_match("", fixture, "diary_read", fake_cell)

    assert any("bolds optional args" in m and "last_n" in m for m in mismatches), \
        f"Expected bold optional arg mismatch, got: {mismatches}"


def test_no_mine_project_root_in_docs():
    """Verify docs don't contain mine <project-root> command."""
    docs_to_check = [
        TOOLS_DOC,
        PLUGIN_ROOT / "skills" / "brain" / "SKILL.md",
        PLUGIN_ROOT / "skills" / "brain" / "references" / "mempalace-workflow.md",
    ]

    violations = []
    for doc_path in docs_to_check:
        if not doc_path.exists():
            continue
        content = doc_path.read_text()
        if "mine <project-root>" in content or "mine $PROJECT_ROOT" in content:
            violations.append(f"{doc_path.relative_to(PLUGIN_ROOT)}: contains mine <project-root>")

    assert not violations, "Found mine <project-root> in docs:\n" + "\n".join(violations)