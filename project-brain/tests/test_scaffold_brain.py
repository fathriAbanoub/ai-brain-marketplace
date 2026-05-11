"""Tests for scaffold_brain.py script."""

import pytest
from pathlib import Path


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
            "raw",
            "log",
            "wiki/architecture",
            "wiki/concepts",
            "wiki/decisions",
            "wiki/entities",
            "wiki/syntheses",
            "outputs/queries",
            "memory",
            "graph",
            "tasks",
            "runbooks",
            "audit",
            "audit/resolved",
        ]
        
        for rel_dir in expected_dirs:
            dir_path = brain / rel_dir
            assert dir_path.exists(), f"Missing directory: {rel_dir}"
            assert dir_path.is_dir(), f"Not a directory: {rel_dir}"

    def test_scaffold_creates_gitkeep_files(self, scaffolded_project: Path):
        """Verify .gitkeep in audit, audit/resolved, raw/assets, outputs/queries."""
        brain = scaffolded_project
        
        gitkeep_paths = [
            "audit/.gitkeep",
            "audit/resolved/.gitkeep",
            "raw/assets/.gitkeep",
            "outputs/queries/.gitkeep",
        ]
        
        for rel_path in gitkeep_paths:
            keep_path = brain / rel_path
            assert keep_path.exists(), f"Missing .gitkeep: {rel_path}"

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
        """Force flag doesn't break idempotency."""
        project_dir = tmp_project / "test-project"
        project_dir.mkdir(parents=True, exist_ok=True)
        
        # First run
        result1 = run_script("scaffold_brain.py", [str(project_dir), "Test Project"])
        assert result1.returncode == 0
        
        # Second run with --force
        result2 = run_script("scaffold_brain.py", [str(project_dir), "Test Project", "--force"])
        
        assert result2.returncode == 0

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
        """Verify wiki pages that scaffold_brain.py actually writes."""
        brain = scaffolded_project
        
        # These are the pages created by scaffold_brain.py based on source inspection
        expected_pages = [
            "wiki/index.md",
            "wiki/architecture/AI Brain Architecture.md",
            "wiki/architecture/System Overview.md",
            "wiki/decisions/Use Layered Brain Architecture.md",
            "wiki/concepts/LLM Wiki.md",
            "wiki/entities/MemPalace.md",
            "wiki/entities/graphify.md",
            "wiki/entities/Obsidian.md",
            "wiki/open-questions.md",
        ]
        
        for rel_path in expected_pages:
            page_path = brain / rel_path
            assert page_path.exists(), f"Missing wiki page: {rel_path}"

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
