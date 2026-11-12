"""Tests for scaffold_brain.py script."""

import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from scaffold_brain import scaffold  # noqa: E402


class TestScaffoldBrain:
    """Test suite for scaffold_brain.py."""

    def test_scaffold_creates_brain_directory(self, run_script, tmp_project: Path):
        """Verify scaffold creates .brain directory."""
        project_dir = tmp_project / "test-project"
        project_dir.mkdir(parents=True, exist_ok=True)
        
        result = run_script("scaffold_brain.py", [str(project_dir), "Test Project"])
        
        assert result.returncode == 0
        assert (project_dir / ".brain").exists()
        assert (project_dir / ".brain").is_dir()

    def test_scaffold_creates_expected_subdirectories(self, scaffolded_project: Path):
        """Check all subdirs that actually exist after scaffold."""
        brain = scaffolded_project
        
        # These are the directories created by scaffold_brain.py
        expected_dirs = [
            "wiki",
            "wiki/sources",
            "state",
            "log",
            "wiki/architecture",
            "wiki/concepts",
            "wiki/decisions",
            "wiki/entities",
            "wiki/syntheses",
            "tasks",
        ]
        
        for rel_dir in expected_dirs:
            dir_path = brain / rel_dir
            assert dir_path.exists(), f"Missing directory: {rel_dir}"
            assert dir_path.is_dir(), f"Not a directory: {rel_dir}"

    def test_scaffold_creates_no_gitkeep_files(self, scaffolded_project: Path):
        """KD-10: no .gitkeep markers in lazily-created lifecycle dirs.

        The old test asserted the presence of empty-dir markers; the fix
        removes the eager dirs entirely (created by the step that fills them).
        """
        brain = scaffolded_project

        lazy_dirs = [
            "audit",
            "audit/resolved",
            "raw/assets",
            "outputs/queries",
            "memory",
            "graph",
            "runbooks",
        ]
        for rel_path in lazy_dirs:
            assert not (brain / rel_path).exists(), f"lifecycle dir created eagerly: {rel_path}"

    def test_init_writes_plugin_root_state_file(self, scaffolded_project: Path):
        """KD-22: init persists the plugin root so later shells read it
        instead of re-deriving it (live iter-5: the model never persisted it
        itself and kept reverting to bare commands until the harness's
        consecutive-failure breaker aborted the session)."""
        state_file = scaffolded_project / "state" / "plugin-root.txt"
        assert state_file.exists(), "init must write .brain/state/plugin-root.txt"
        recorded = state_file.read_text(encoding="utf-8").strip()
        assert recorded == str(PLUGIN_ROOT), (
            f"recorded plugin root {recorded!r} != actual {PLUGIN_ROOT}"
        )
        assert (Path(recorded) / "bin").is_dir(), "recorded root must contain bin/"

    def test_scaffold_templates_do_not_teach_slash_graphify(self, scaffolded_project: Path):
        """KD-20 residual, found during KD-22 review: the next-actions
        template still taught the slash form `/graphify .` (the exact iter-3
        failure vector) although lint/doctor/skill text were fixed."""
        next_actions = scaffolded_project / "tasks" / "next-actions.md"
        assert next_actions.exists()
        text = next_actions.read_text(encoding="utf-8")
        assert "/graphify" not in text, (
            "scaffold output must teach the CLI form `graphify .`, never the slash form"
        )

    def test_scaffold_creates_index_md_with_project_name(self, scaffolded_project: Path):
        """index.md contains the project title."""
        brain = scaffolded_project
        index_path = brain / "wiki" / "index.md"
        
        assert index_path.exists()
        content = index_path.read_text(encoding="utf-8")
        assert "Test Project" in content or "Project Brain Index - Test Project" in content

    def test_scaffold_creates_session_brief(self, scaffolded_project: Path):
        """session-brief.md is non-empty."""
        brain = scaffolded_project
        brief_path = brain / "state" / "session-brief.md"
        
        assert brief_path.exists()
        content = brief_path.read_text(encoding="utf-8")
        assert len(content.strip()) > 0

    def test_scaffold_idempotent_does_not_overwrite(self, run_script, tmp_project: Path):
        """Second run preserves sentinel line added after first run."""
        project_dir = tmp_project / "test-project"
        project_dir.mkdir(parents=True, exist_ok=True)
        
        # First run
        result1 = run_script("scaffold_brain.py", [str(project_dir), "Test Project"])
        assert result1.returncode == 0
        
        # Add sentinel line to a file
        brain_dir = project_dir / ".brain"
        claude_md = brain_dir / "CLAUDE.md"
        original_content = claude_md.read_text(encoding="utf-8")
        sentinel_line = "\n# SENTINEL_TEST_LINE_DO_NOT_REMOVE\n"
        claude_md.write_text(original_content + sentinel_line, encoding="utf-8")
        
        # Second run (without --force)
        result2 = run_script("scaffold_brain.py", [str(project_dir), "Test Project"])
        assert result2.returncode == 0
        
        # Verify sentinel is preserved
        new_content = claude_md.read_text(encoding="utf-8")
        assert "# SENTINEL_TEST_LINE_DO_NOT_REMOVE" in new_content

    def test_scaffold_no_args_exits_nonzero(self, run_script, tmp_project: Path):
        """Running without arguments exits with non-zero code."""
        project_dir = tmp_project / "test-project"
        project_dir.mkdir(parents=True, exist_ok=True)
        
        result = run_script("scaffold_brain.py", [])
        
        assert result.returncode != 0

    def test_scaffold_project_name_with_spaces(self, run_script, tmp_project: Path):
        """Project names with spaces work correctly."""
        project_dir = tmp_project / "test-project"
        project_dir.mkdir(parents=True, exist_ok=True)
        
        result = run_script("scaffold_brain.py", [str(project_dir), "My Cool Project Name"])
        
        assert result.returncode == 0
        brain_dir = project_dir / ".brain"
        assert brain_dir.exists()
        
        # Check project name appears in files
        index_path = brain_dir / "wiki" / "index.md"
        content = index_path.read_text(encoding="utf-8")
        assert "My Cool Project Name" in content

    def test_scaffold_force_flag(self, run_script, tmp_project: Path):
        """Force flag actually replaces files rather than only returning zero exit code."""
        project_dir = tmp_project / "test-project"
        project_dir.mkdir(parents=True, exist_ok=True)
        
        # First run
        result1 = run_script("scaffold_brain.py", [str(project_dir), "Test Project"])
        assert result1.returncode == 0
        
        # Identify a generated file and capture its content
        brain_dir = project_dir / ".brain"
        claude_md = brain_dir / "CLAUDE.md"
        assert claude_md.exists()
        original_content = claude_md.read_text(encoding="utf-8")
        
        # Mutate the file to a different value
        mutated_line = "\n# MUTATED_BY_TEST_BEFORE_FORCE\n"
        claude_md.write_text(original_content + mutated_line, encoding="utf-8")
        
        # Second run with --force
        result2 = run_script("scaffold_brain.py", [str(project_dir), "Test Project", "--force"])
        assert result2.returncode == 0
        
        # Verify the file was overwritten (mutated line should be gone or content changed back)
        new_content = claude_md.read_text(encoding="utf-8")
        # With --force, the file should be restored to scaffold's expected content
        # The mutated line should NOT be present after force overwrite
        assert "# MUTATED_BY_TEST_BEFORE_FORCE" not in new_content

    def test_scaffold_creates_claude_md(self, scaffolded_project: Path):
        """CLAUDE.md exists and contains 'Project Brain'."""
        brain = scaffolded_project
        claude_path = brain / "CLAUDE.md"
        
        assert claude_path.exists()
        content = claude_path.read_text(encoding="utf-8")
        assert "Project Brain" in content

    def test_scaffold_creates_tasks_next_actions(self, scaffolded_project: Path):
        """tasks/next-actions.md exists."""
        brain = scaffolded_project
        tasks_path = brain / "tasks" / "next-actions.md"
        
        assert tasks_path.exists()

    def test_scaffold_creates_wiki_pages(self, scaffolded_project: Path):
        """KD-11: only project-facing seed pages exist after scaffold.

        The old expected list asserted the plugin-explaining seed pages; those
        are removed (operating instructions live in .brain/CLAUDE.md).
        """
        brain = scaffolded_project

        expected_pages = [
            "wiki/index.md",
            "wiki/architecture/System Overview.md",
            "wiki/open-questions.md",
        ]

        for rel_path in expected_pages:
            page_path = brain / rel_path
            assert page_path.exists(), f"Missing wiki page: {rel_path}"

        forbidden = [
            "wiki/architecture/AI Brain Architecture.md",
            "wiki/decisions/Use Layered Brain Architecture.md",
            "wiki/concepts/LLM Wiki.md",
            "wiki/concepts/Post-Wiki Synchronization.md",
            "wiki/entities/MemPalace.md",
            "wiki/entities/graphify.md",
            "wiki/entities/Obsidian.md",
        ]
        for rel_path in forbidden:
            assert not (brain / rel_path).exists(), f"plugin-explaining seed page present: {rel_path}"


    def test_scaffold_unicode_project_name(self, run_script, tmp_project: Path):
        """Use a name with emoji or accent and verify no error."""
        project_dir = tmp_project / "test-project"
        project_dir.mkdir(parents=True, exist_ok=True)
        
        unicode_name = "Projet Émoji 🚀"
        result = run_script("scaffold_brain.py", [str(project_dir), unicode_name])
        
        assert result.returncode == 0
        brain_dir = project_dir / ".brain"
        assert brain_dir.exists()
        
        # Check unicode name appears in files
        index_path = brain_dir / "wiki" / "index.md"
        content = index_path.read_text(encoding="utf-8")
        assert unicode_name in content
# --- diary agent preservation across refresh ----------------------------------


def test_scaffold_configured_agent_vs_stale_sentence(tmp_path: Path):
    """Configured agent in frontmatter not overridden by stale sentence."""
    root = tmp_path / "project"
    root.mkdir()
    (root / ".git").mkdir()

    # Initial scaffold
    scaffold(root, "New Title")
    claude_md = root / ".brain" / "CLAUDE.md"

    # Manually set frontmatter to brain-new-title and insert old sentence
    content = claude_md.read_text(encoding="utf-8")
    # Add stale sentence after frontmatter
    lines = content.split("\n")
    insert_pos = next(i for i, line in enumerate(lines) if line.startswith("# New Title"))
    lines.insert(insert_pos + 2, "The session diary uses `mempalace_diary_write` with agent `brain-old-title`.")
    claude_md.write_text("\n".join(lines), encoding="utf-8")

    # Refresh with --force
    scaffold(root, "New Title", force=True)

    new_content = claude_md.read_text(encoding="utf-8")
    assert "mempalace_diary_agent: brain_new_title" in new_content
    assert "agent `brain_new_title`" in new_content


def test_scaffold_custom_agent_without_prefix_survives(tmp_path: Path):
    """Custom agent name without 'brain-' prefix preserved exactly."""
    root = tmp_path / "project"
    root.mkdir()
    (root / ".git").mkdir()

    # Initial scaffold
    scaffold(root, "Test")
    claude_md = root / ".brain" / "CLAUDE.md"

    # Set custom agent without prefix
    content = claude_md.read_text(encoding="utf-8")
    content = content.replace(
        "mempalace_diary_agent: brain_test",
        "mempalace_diary_agent: my-custom-agent"
    )
    claude_md.write_text(content, encoding="utf-8")

    # Refresh with --force
    scaffold(root, "Different Title", force=True)

    new_content = claude_md.read_text(encoding="utf-8")
    assert "mempalace_diary_agent: my-custom-agent" in new_content
    assert "brain-my-custom-agent" not in new_content
    # Check diary wing text uses the custom agent
    assert "agent `my-custom-agent`" in new_content
    assert "wing_my-custom-agent" in new_content


def test_scaffold_new_brain_gets_diary_agent(tmp_path: Path):
    """A new brain gets mempalace_diary_agent frontmatter."""
    root = tmp_path / "project"
    root.mkdir()
    (root / ".git").mkdir()
    scaffold(root, "Test Project")
    claude_md = root / ".brain" / "CLAUDE.md"
    content = claude_md.read_text(encoding="utf-8")
    assert "mempalace_diary_agent: brain_test_project" in content, \
        "New brain must have mempalace_diary_agent frontmatter"


def test_scaffold_refresh_keeps_original_agent(tmp_path: Path):
    """Refresh with --force and different title keeps original diary agent."""
    root = tmp_path / "project"
    root.mkdir()
    (root / ".git").mkdir()

    scaffold(root, "Original Title")
    claude_md = root / ".brain" / "CLAUDE.md"
    first_content = claude_md.read_text(encoding="utf-8")
    assert "mempalace_diary_agent: brain_original_title" in first_content

    scaffold(root, "New Title", force=True)
    second_content = claude_md.read_text(encoding="utf-8")
    assert "mempalace_diary_agent: brain_original_title" in second_content, \
        "Refresh must keep original diary agent"
    assert "brain_new_title" not in second_content


def test_scaffold_old_brain_recovers_slug_from_sentence(tmp_path: Path):
    """Refresh of older brain without frontmatter recovers slug from sentence."""
    root = tmp_path / "project"
    root.mkdir()
    (root / ".git").mkdir()
    brain = root / ".brain"
    brain.mkdir()

    old_claude = brain / "CLAUDE.md"
    old_content = """---
mempalace_wing: wiki-legacy
---

# Legacy Brain

The session diary uses `mempalace_diary_write` with agent `brain-legacy-slug`.
"""
    old_claude.write_text(old_content, encoding="utf-8")

    scaffold(root, "New Title", force=True)
    new_content = old_claude.read_text(encoding="utf-8")
    assert "mempalace_diary_agent: brain-legacy-slug" in new_content, \
        "Must recover slug from old diary sentence"


def test_scaffold_empty_diary_agent_falls_back(tmp_path: Path):
    """Empty mempalace_diary_agent value falls back to title-derived slug."""
    root = tmp_path / "project"
    root.mkdir()
    (root / ".git").mkdir()
    brain = root / ".brain"
    brain.mkdir()

    broken_claude = brain / "CLAUDE.md"
    broken_content = """---
mempalace_wing: wiki-test
mempalace_diary_agent:
---

# Test
"""
    broken_claude.write_text(broken_content, encoding="utf-8")

    scaffold(root, "Fallback Title", force=True)
    new_content = broken_claude.read_text(encoding="utf-8")
    assert "mempalace_diary_agent: brain_fallback_title" in new_content, \
        "Empty diary agent must fall back to title-derived slug"
