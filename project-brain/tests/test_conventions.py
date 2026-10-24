"""Tests for wing naming, .graphifyignore handling, graphify gating, and tool-list drift."""

import json
import os
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
    "diary_agent",  # frontmatter field name, not a tool
}


def documented_tools() -> set[str]:
    return set(TOOL_ROW_RE.findall(TOOLS_DOC.read_text(encoding="utf-8")))


# --- item 3: wing naming ----------------------------------------------------


def test_mempalace_diary_agent_documented():
    """All key documentation files mention mempalace_diary_agent."""
    key_files = [
        PLUGIN_ROOT / "skills" / "brain" / "references" / "mempalace-workflow.md",
        PLUGIN_ROOT / "skills" / "brain" / "references" / "mempalace-tools.md",
        PLUGIN_ROOT / "skills" / "brain" / "references" / "brain-lifecycle.md",
        PLUGIN_ROOT / "skills" / "brain" / "SKILL.md",
    ]
    for path in key_files:
        text = path.read_text(encoding="utf-8")
        assert "mempalace_diary_agent" in text, f"{path.name} must mention mempalace_diary_agent"


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
    _git(root, "config", "commit.gpgsign", "false")
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
    a_file = git_repo / "a.txt"
    report_path = git_repo / "graphify-out" / "GRAPH_REPORT.md"
    report_m = report_path.stat().st_mtime
    # Set report mtime first, then write the file change after
    os.utime(report_path, (report_m, report_m))
    a_file.write_text("dirty\n", encoding="utf-8")
    os.utime(a_file, (report_m + 10, report_m + 10))  # file newer than report
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
    new_file = git_repo / "new_module.py"
    new_file.write_text("x = 1\n", encoding="utf-8")
    # Pin mtimes explicitly: filesystems with coarse timestamp granularity
    # (e.g. overlayfs) give same-tick writes identical mtimes, which makes the
    # mtime comparison in doctor.graphify_freshness order-dependent otherwise.
    report_path = git_repo / "graphify-out" / "GRAPH_REPORT.md"
    report_m = report_path.stat().st_mtime
    os.utime(report_path, (report_m, report_m))
    os.utime(new_file, (report_m + 10, report_m + 10))
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


def test_gate_fresh_with_scaffolded_graphifyignore_then_graph(git_repo: Path):
    # FIX 3a: .graphifyignore is NOT excluded from the dirty check anymore.
    # Scaffold order (ignore created untracked, graph built after) must report
    # fresh via the report-mtime check, not via an exclusion.
    ignore = git_repo / ".graphifyignore"
    ignore.write_text("node_modules/\n", encoding="utf-8")
    head = _git(git_repo, "rev-parse", "HEAD").strip()
    _write_report(git_repo, head)
    report_path = git_repo / "graphify-out" / "GRAPH_REPORT.md"
    m = report_path.stat().st_mtime
    os.utime(report_path, (m + 10, m + 10))  # report strictly newer than ignore
    status, reason = graphify_freshness(git_repo)
    assert status == "fresh", reason


def test_gate_stale_when_graphifyignore_edited_after_graph(git_repo: Path):
    # FIX 3b: editing .graphifyignore after the report changes which files
    # graphify indexes — it must count as real staleness.
    head = _git(git_repo, "rev-parse", "HEAD").strip()
    _write_report(git_repo, head)
    report_path = git_repo / "graphify-out" / "GRAPH_REPORT.md"
    m = report_path.stat().st_mtime
    ignore = git_repo / ".graphifyignore"
    ignore.write_text("dist/\n", encoding="utf-8")
    os.utime(ignore, (m + 10, m + 10))  # ignore strictly newer than report
    status, reason = graphify_freshness(git_repo)
    assert status == "stale"
    assert ".graphifyignore" in reason


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


# --- Finding 1: Recall step mentions both search and diary_read ---------------


def test_skill_step7_mentions_both_mempalace_tools():
    """SKILL.md step 7 must mention both mempalace_search and mempalace_diary_read."""
    skill_md = PLUGIN_ROOT / "skills" / "brain" / "SKILL.md"
    content = skill_md.read_text(encoding="utf-8")

    # Find step 7 section (starts with "7. Check MemPalace")
    step7_start = content.find("7. Check MemPalace")
    assert step7_start != -1, "Step 7 not found in SKILL.md"

    # Find next numbered step (8.) to bound the section
    step8_start = content.find("\n8. ", step7_start)
    if step8_start == -1:
        step7_section = content[step7_start:]
    else:
        step7_section = content[step7_start:step8_start]

    assert "mempalace_search" in step7_section, "Step 7 must mention mempalace_search"
    assert "mempalace_diary_read" in step7_section, "Step 7 must mention mempalace_diary_read"


def test_lifecycle_consolidate_mentions_both_mempalace_tools():
    """brain-lifecycle.md consolidate memory section must mention both tools."""
    lifecycle_md = PLUGIN_ROOT / "skills" / "brain" / "references" / "brain-lifecycle.md"
    content = lifecycle_md.read_text(encoding="utf-8")

    # Find "Consolidate memory" section
    section_start = content.find("### Consolidate memory")
    assert section_start != -1, "Consolidate memory section not found"

    # Find next ### heading to bound the section
    next_section = content.find("\n### ", section_start + 1)
    if next_section == -1:
        section = content[section_start:]
    else:
        section = content[section_start:next_section]

    assert "mempalace_search" in section, "Consolidate memory must mention mempalace_search"
    assert "mempalace_diary_read" in section, "Consolidate memory must mention mempalace_diary_read"


# --- Finding 2: Diary read recipe links to existing brains procedure ----------


def test_diary_read_recipe_links_to_existing_brains():
    """mempalace-tools.md diary read recipe must link to existing brains procedure."""
    tools_md = PLUGIN_ROOT / "skills" / "brain" / "references" / "mempalace-tools.md"
    workflow_md = PLUGIN_ROOT / "skills" / "brain" / "references" / "mempalace-workflow.md"

    tools_content = tools_md.read_text(encoding="utf-8")
    workflow_content = workflow_md.read_text(encoding="utf-8")

    # Find diary read recipe section
    recipe_start = tools_content.find("### 5. Read Diary at Wake-up")
    assert recipe_start != -1, "Diary read recipe not found"

    # Find next ### to bound the section
    next_recipe = tools_content.find("\n### ", recipe_start + 1)
    if next_recipe == -1:
        recipe_section = tools_content[recipe_start:]
    else:
        recipe_section = tools_content[recipe_start:next_recipe]

    # Must link to existing brains procedure
    assert "mempalace-workflow.md#existing-brains-older-diary-entries" in recipe_section, \
        "Diary read recipe must link to existing brains procedure"

    # Verify the heading exists in mempalace-workflow.md
    assert "### Existing brains: older diary entries" in workflow_content, \
        "Existing brains heading must exist in mempalace-workflow.md"


# --- Finding 3: Missing wing guard ---------------------------------------------


def test_skill_step7_has_missing_wing_guard():
    """SKILL.md step 7 must guard against missing mempalace_wing."""
    skill_md = PLUGIN_ROOT / "skills" / "brain" / "SKILL.md"
    content = skill_md.read_text(encoding="utf-8")

    step7_start = content.find("7. Check MemPalace")
    assert step7_start != -1, "Step 7 not found"

    step8_start = content.find("\n8. ", step7_start)
    step7_section = content[step7_start:step8_start] if step8_start != -1 else content[step7_start:]

    # Must mention missing/not defined check
    assert "missing or does not define" in step7_section.lower(), \
        "Step 7 must check if .brain/CLAUDE.md is missing or has no mempalace_wing"

    # Must tell user to initialize
    assert "initialize" in step7_section.lower() or "project-brain-init" in step7_section, \
        "Step 7 must tell user to run project-brain-init"

    # Must warn against inferring wing
    assert "never infer" in step7_section.lower(), \
        "Step 7 must warn against inferring a wing"


def test_mempalace_tools_search_recipe_has_wing_guard():
    """mempalace-tools.md search recipe must guard against missing wing."""
    tools_md = PLUGIN_ROOT / "skills" / "brain" / "references" / "mempalace-tools.md"
    content = tools_md.read_text(encoding="utf-8")

    # Find Recipe 2 (Recall Before Claims)
    recipe_start = content.find("### 2. Recall Before Claims")
    assert recipe_start != -1, "Recall Before Claims recipe not found"

    next_recipe = content.find("\n### ", recipe_start + 1)
    recipe_section = content[recipe_start:next_recipe] if next_recipe != -1 else content[recipe_start:]

    # Must have the guard
    assert "missing or does not define" in recipe_section.lower(), \
        "Recall recipe must check for missing mempalace_wing"
    assert "never infer" in recipe_section.lower(), \
        "Recall recipe must warn against inferring wing"


# --- A1/A2: paths with spaces/non-ASCII, manifest lazy loading ---------------


def test_gate_stale_with_space_in_filename_edited_after_report(git_repo: Path):
    """File with space in name edited after report -> stale."""
    head = _git(git_repo, "rev-parse", "HEAD").strip()
    _write_report(git_repo, head)
    import time
    time.sleep(0.01)
    spaced = git_repo / "my file.py"
    spaced.write_text("print('hello')\n", encoding="utf-8")
    status, reason = graphify_freshness(git_repo)
    assert status == "stale"
    assert "uncommitted changes" in reason
    assert "my file.py" in reason


def test_gate_stale_with_utf8_filename_edited_after_report(git_repo: Path):
    """File with non-ASCII name edited after report -> stale."""
    head = _git(git_repo, "rev-parse", "HEAD").strip()
    _write_report(git_repo, head)
    import time
    time.sleep(0.01)
    utf8_file = git_repo / "café.py"
    utf8_file.write_text("print('bonjour')\n", encoding="utf-8")
    status, reason = graphify_freshness(git_repo)
    assert status == "stale"
    assert "uncommitted changes" in reason
    assert "café.py" in reason


def test_gate_stale_with_spaced_filename_deleted_and_in_manifest(git_repo: Path):
    """Deleted file with space, present in manifest -> stale."""
    spaced = git_repo / "my file.py"
    spaced.write_text("x = 1\n", encoding="utf-8")
    _git(git_repo, "add", ".")
    _git(git_repo, "commit", "-qm", "add spaced file")
    head = _git(git_repo, "rev-parse", "HEAD").strip()
    _write_report(git_repo, head)
    # Write manifest with the spaced file
    manifest = git_repo / "graphify-out" / "manifest.json"
    manifest.write_text(json.dumps({"my file.py": {"mtime": 1000, "seen": 1}}), encoding="utf-8")
    spaced.unlink()
    status, reason = graphify_freshness(git_repo)
    assert status == "stale"
    assert "uncommitted changes" in reason


def test_gate_fresh_with_spaced_filename_deleted_not_in_manifest(git_repo: Path):
    """Deleted file with space, absent from manifest -> fresh."""
    spaced = git_repo / "my file.py"
    spaced.write_text("x = 1\n", encoding="utf-8")
    _git(git_repo, "add", ".")
    _git(git_repo, "commit", "-qm", "add spaced file")
    head = _git(git_repo, "rev-parse", "HEAD").strip()
    _write_report(git_repo, head)
    # Manifest without the spaced file
    manifest = git_repo / "graphify-out" / "manifest.json"
    manifest.write_text(json.dumps({"other.py": {"mtime": 1000, "seen": 1}}), encoding="utf-8")
    spaced.unlink()
    status, reason = graphify_freshness(git_repo)
    assert status == "fresh"


def test_gate_stale_with_renamed_spaced_file_old_path_in_manifest(git_repo: Path):
    """Renamed file with space; old path in manifest -> stale."""
    old_name = git_repo / "my file.py"
    old_name.write_text("x = 1\n", encoding="utf-8")
    _git(git_repo, "add", ".")
    _git(git_repo, "commit", "-qm", "add old file")
    head = _git(git_repo, "rev-parse", "HEAD").strip()
    _write_report(git_repo, head)
    manifest = git_repo / "graphify-out" / "manifest.json"
    manifest.write_text(json.dumps({"my file.py": {"mtime": 1000, "seen": 1}}), encoding="utf-8")
    old_name.rename(git_repo / "new.py")
    status, reason = graphify_freshness(git_repo)
    assert status == "stale"
    assert "uncommitted changes" in reason


def test_gate_manifest_not_loaded_when_no_deletions(git_repo: Path, monkeypatch):
    """Manifest helper not called when no files are deleted."""
    from doctor import _load_manifest_keys
    head = _git(git_repo, "rev-parse", "HEAD").strip()
    _write_report(git_repo, head)
    import time
    time.sleep(0.01)
    # Edit an existing file (no deletion)
    (git_repo / "a.txt").write_text("modified\n", encoding="utf-8")

    called = []
    original = _load_manifest_keys
    def spy(root):
        called.append(root)
        return original(root)
    monkeypatch.setattr("doctor._load_manifest_keys", spy)

    status, reason = graphify_freshness(git_repo)
    assert status == "stale"
    assert not called, "Manifest should not be loaded when no deletions"


def test_gate_corrupt_manifest_no_exception(git_repo: Path):
    """Corrupt manifest returns fresh (no crash) when file deleted."""
    victim = git_repo / "victim.py"
    victim.write_text("x = 1\n", encoding="utf-8")
    _git(git_repo, "add", ".")
    _git(git_repo, "commit", "-qm", "add victim")
    head = _git(git_repo, "rev-parse", "HEAD").strip()
    _write_report(git_repo, head)
    manifest = git_repo / "graphify-out" / "manifest.json"
    manifest.write_text("not json at all", encoding="utf-8")
    victim.unlink()
    status, reason = graphify_freshness(git_repo)
    # No crash, returns fresh because manifest failed to load
    assert status == "fresh"

# --- recall instructions must have guard and wing scope -----------------------

def test_guard_key_phrase_in_all_files():
    """Each doc file must contain the guard phrase OR a pointer to the recall rule."""
    guard_phrase = "does not define a non-empty"
    recall_rule_pointer = "recall rule in"
    required_files = [
        "skills/brain/SKILL.md",
        "skills/brain/references/brain-lifecycle.md",
        "skills/brain/references/post-wiki-checklist.md",
        "skills/brain/references/install-and-integration.md",
        "skills/brain/references/mempalace-tools.md",
    ]
    for rel in required_files:
        path = PLUGIN_ROOT / rel
        content = path.read_text(encoding="utf-8")
        has_guard = guard_phrase in content
        has_pointer = recall_rule_pointer in content
        assert has_guard or has_pointer, \
            f"{rel} must contain guard phrase '{guard_phrase}' OR pointer '{recall_rule_pointer}'"


def test_no_unscoped_mempalace_search():
    """No doc line with '(search|query) mempalace' lacks wing/diary/recall-rule."""
    import re
    doc_files = list((PLUGIN_ROOT / "skills").rglob("*.md"))
    doc_files.extend((PLUGIN_ROOT / "scripts").rglob("*.py"))
    doc_files.extend((PLUGIN_ROOT / "hooks").rglob("*.py"))

    search_re = re.compile(r"(search|query|check)\s+mempalace", re.IGNORECASE)
    scope_indicators = ["wing", "mempalace_diary_read", "recall rule"]
    # Skip table rows (lines starting with |)
    table_row_re = re.compile(r"^\s*\|")

    violations = []
    for path in doc_files:
        content = path.read_text(encoding="utf-8")
        for i, line in enumerate(content.splitlines(), 1):
            # Skip table rows
            if table_row_re.match(line):
                continue
            if search_re.search(line):
                line_lower = line.lower()
                if not any(ind in line_lower for ind in scope_indicators):
                    violations.append(f"{path.relative_to(PLUGIN_ROOT)}:{i}")

    assert not violations, \
        f"Lines with '(search|query) mempalace' lack wing/diary/recall-rule:\n" + "\n".join(violations)


# --- Rename and copy handling in git status parsing -------------------------

def test_gate_stale_with_staged_rename_old_path_in_manifest(git_repo: Path):
    """Staged git mv with old path in manifest reports stale."""
    root = git_repo
    src = root / "old.py"
    src.write_text("print('hello')")
    subprocess.run(["git", "add", "old.py"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
    
    _write_report(root, head)
    manifest = root / "graphify-out" / "manifest.json"
    manifest.write_text(json.dumps({"old.py": {"mtime": 1000, "seen": 1}}))
    
    subprocess.run(["git", "mv", "old.py", "new.py"], cwd=root, check=True, capture_output=True)
    
    status, reason = graphify_freshness(root)
    assert status == "stale", "Staged rename with old path in manifest must report stale"
    assert "uncommitted changes" in reason


def test_gate_stale_with_unstaged_rename_old_path_in_manifest(git_repo: Path):
    """Unstaged rename (D old + ?? new) with old path in manifest reports stale."""
    root = git_repo
    src = root / "old.py"
    src.write_text("print('hello')")
    subprocess.run(["git", "add", "old.py"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
    
    _write_report(root, head)
    manifest = root / "graphify-out" / "manifest.json"
    manifest.write_text(json.dumps({"old.py": {"mtime": 1000, "seen": 1}}))
    
    (root / "old.py").rename(root / "new.py")
    
    status, reason = graphify_freshness(root)
    assert status == "stale", "Unstaged rename with old path in manifest must report stale"


def test_parse_status_z_staged_rename():
    """Parse staged rename: R  new\\0old\\0"""
    from doctor import _parse_status_z
    output = "R  new.py\0old.py\0"
    current, origin = _parse_status_z(output)
    assert current == ["new.py"], f"Expected ['new.py'], got {current}"
    assert origin == ["old.py"], f"Expected ['old.py'], got {origin}"


def test_parse_status_z_worktree_rename():
    """Parse worktree rename:  R new\\0old\\0"""
    from doctor import _parse_status_z
    output = " R new.py\0old.py\0"
    current, origin = _parse_status_z(output)
    assert current == ["new.py"]
    assert origin == ["old.py"]


def test_parse_status_z_copy():
    """Parse copy: C  new\\0old\\0"""
    from doctor import _parse_status_z
    output = "C  new.py\0old.py\0"
    current, origin = _parse_status_z(output)
    assert current == ["new.py"]
    assert origin == ["old.py"]


def test_parse_status_z_mixed():
    """Parse mixed status with rename, modify, untracked."""
    from doctor import _parse_status_z
    output = "R  new.py\0old.py\0M  a.py\0?? b.py\0"
    current, origin = _parse_status_z(output)
    assert current == ["new.py", "a.py", "b.py"]
    assert origin == ["old.py"]


def test_parse_status_z_path_with_space():
    """Parse path with space."""
    from doctor import _parse_status_z
    output = "M  my file.py\0"
    current, origin = _parse_status_z(output)
    assert current == ["my file.py"]
    assert origin == []


def test_gate_deletion_in_manifest_reports_stale(git_repo: Path):
    """Deleted file present in manifest reports stale."""
    src = git_repo / "src.py"
    src.write_text("print('hello')")
    _git(git_repo, "add", "src.py")
    _git(git_repo, "commit", "-m", "init")
    head = _git(git_repo, "rev-parse", "HEAD").strip()

    graphify_out = git_repo / "graphify-out"
    graphify_out.mkdir()
    report = graphify_out / "GRAPH_REPORT.md"
    report.write_text(f"Built from commit: `{head[:12]}`\n")

    manifest = graphify_out / "manifest.json"
    manifest.write_text(json.dumps({"src.py": {"mtime": 1000, "seen": 1}}))

    src.unlink()

    status, reason = graphify_freshness(git_repo)
    assert status == "stale"
    assert "uncommitted changes" in reason


def test_gate_deletion_not_in_manifest_reports_fresh(git_repo: Path):
    """Deleted file not in manifest reports fresh."""
    src = git_repo / "src.py"
    src.write_text("print('hello')")
    _git(git_repo, "add", "src.py")
    _git(git_repo, "commit", "-m", "init")
    head = _git(git_repo, "rev-parse", "HEAD").strip()

    graphify_out = git_repo / "graphify-out"
    graphify_out.mkdir()
    report = graphify_out / "GRAPH_REPORT.md"
    report.write_text(f"Built from commit: `{head[:12]}`\n")

    manifest = graphify_out / "manifest.json"
    manifest.write_text(json.dumps({"other.py": {"mtime": 1000, "seen": 1}}))

    src.unlink()

    status, reason = graphify_freshness(git_repo)
    assert status == "fresh"


def test_gate_deletion_absolute_key_reports_stale(git_repo: Path):
    """Deleted file with absolute path key in manifest reports stale."""
    src = git_repo / "src.py"
    src.write_text("print('hello')")
    _git(git_repo, "add", "src.py")
    _git(git_repo, "commit", "-m", "init")
    head = _git(git_repo, "rev-parse", "HEAD").strip()

    graphify_out = git_repo / "graphify-out"
    graphify_out.mkdir()
    report = graphify_out / "GRAPH_REPORT.md"
    report.write_text(f"Built from commit: `{head[:12]}`\n")

    manifest = graphify_out / "manifest.json"
    manifest.write_text(json.dumps({str(src.resolve()): {"mtime": 1000, "seen": 1}}))

    src.unlink()

    status, reason = graphify_freshness(git_repo)
    assert status == "stale"


def test_gate_missing_manifest_no_exception(git_repo: Path):
    """Missing manifest does not raise exception."""
    src = git_repo / "src.py"
    src.write_text("print('hello')")
    _git(git_repo, "add", "src.py")
    _git(git_repo, "commit", "-m", "init")
    head = _git(git_repo, "rev-parse", "HEAD").strip()

    graphify_out = git_repo / "graphify-out"
    graphify_out.mkdir()
    report = graphify_out / "GRAPH_REPORT.md"
    report.write_text(f"Built from commit: `{head[:12]}`\n")

    src.unlink()

    status, reason = graphify_freshness(git_repo)
    assert status == "fresh"


def test_gate_corrupt_manifest_no_exception(git_repo: Path):
    """Corrupt manifest does not raise exception."""
    src = git_repo / "src.py"
    src.write_text("print('hello')")
    _git(git_repo, "add", "src.py")
    _git(git_repo, "commit", "-m", "init")
    head = _git(git_repo, "rev-parse", "HEAD").strip()

    graphify_out = git_repo / "graphify-out"
    graphify_out.mkdir()
    report = graphify_out / "GRAPH_REPORT.md"
    report.write_text(f"Built from commit: `{head[:12]}`\n")

    manifest = graphify_out / "manifest.json"
    manifest.write_text("not json at all")

    src.unlink()

    status, reason = graphify_freshness(git_repo)
    assert status == "fresh"


def test_gate_list_manifest_no_exception(git_repo: Path):
    """Manifest that is a JSON list does not raise exception."""
    src = git_repo / "src.py"
    src.write_text("print('hello')")
    _git(git_repo, "add", "src.py")
    _git(git_repo, "commit", "-m", "init")
    head = _git(git_repo, "rev-parse", "HEAD").strip()

    graphify_out = git_repo / "graphify-out"
    graphify_out.mkdir()
    report = graphify_out / "GRAPH_REPORT.md"
    report.write_text(f"Built from commit: `{head[:12]}`\n")

    manifest = graphify_out / "manifest.json"
    manifest.write_text(json.dumps(["src.py"]))

    src.unlink()

    status, reason = graphify_freshness(git_repo)
    assert status == "fresh"


def test_gate_renamed_file_old_path_in_manifest_reports_stale(git_repo: Path):
    """Renamed file whose old path is in manifest reports stale."""
    old = git_repo / "old.py"
    old.write_text("print('hello')")
    _git(git_repo, "add", "old.py")
    _git(git_repo, "commit", "-m", "init")
    head = _git(git_repo, "rev-parse", "HEAD").strip()

    graphify_out = git_repo / "graphify-out"
    graphify_out.mkdir()
    report = graphify_out / "GRAPH_REPORT.md"
    report.write_text(f"Built from commit: `{head[:12]}`\n")

    manifest = graphify_out / "manifest.json"
    manifest.write_text(json.dumps({"old.py": {"mtime": 1000, "seen": 1}}))

    old.rename(git_repo / "new.py")

    status, reason = graphify_freshness(git_repo)
    assert status == "stale"
