"""Tests for reset_brain.py script.

All tests use --dry-run only – never test actual deletion.
"""

import pytest
from pathlib import Path


class TestResetBrain:
    """Test suite for reset_brain.py."""

    def test_dry_run_exits_zero(self, run_script, scaffolded_project: Path):
        """--dry-run exits with code 0."""
        brain = scaffolded_project
        project_dir = brain.parent
        
        result = run_script("reset_brain.py", [str(project_dir), "--dry-run"])
        
        assert result.returncode == 0

    def test_dry_run_prints_preview(self, run_script, scaffolded_project: Path):
        """--dry-run prints a preview of what would be deleted."""
        brain = scaffolded_project
        project_dir = brain.parent
        
        result = run_script("reset_brain.py", [str(project_dir), "--dry-run"])
        
        assert result.returncode == 0
        # Should mention deletion preview
        assert "would be deleted" in result.stdout or "Summary:" in result.stdout

    def test_dry_run_does_not_delete_files(self, run_script, scaffolded_project: Path):
        """Assert file still exists after dry run."""
        brain = scaffolded_project
        project_dir = brain.parent
        
        # Get a file that should exist
        index_path = brain / "wiki" / "index.md"
        assert index_path.exists()
        
        result = run_script("reset_brain.py", [str(project_dir), "--dry-run"])
        
        assert result.returncode == 0
        # File should still exist after dry run
        assert index_path.exists()

    def test_dry_run_mempalace_unavailable_no_crash(self, run_script, scaffolded_project: Path):
        """Dry run handles MemPalace unavailability gracefully."""
        brain = scaffolded_project
        project_dir = brain.parent
        
        # Run without MemPalace bridge configured
        result = run_script("reset_brain.py", [str(project_dir), "--dry-run"])
        
        # Should not crash - just report MemPalace unavailable
        assert "MemPalace" in result.stdout or "MemPalace" in result.stderr or result.returncode == 0

    def test_dry_run_shows_wing_info(self, run_script, scaffolded_project: Path):
        """Output contains 'Wing:' or similar stable label."""
        brain = scaffolded_project
        project_dir = brain.parent
        
        result = run_script("reset_brain.py", [str(project_dir), "--dry-run"])
        
        assert result.returncode == 0
        # Should show wing information
        assert "wing" in result.stdout.lower() or "MemPalace wing" in result.stdout

    def test_no_brain_directory_error(self, run_script, tmp_project: Path):
        """Gracefully reports missing .brain, no traceback."""
        project_dir = tmp_project / "no-brain-project"
        project_dir.mkdir(parents=True, exist_ok=True)
        
        result = run_script("reset_brain.py", [str(project_dir), "--dry-run"])
        
        # Should report error gracefully without Python traceback
        assert "Traceback" not in result.stderr
        # Should mention brain directory issue
        assert result.returncode != 0 or ".brain" in result.stdout or "not found" in result.stdout.lower()

    def test_dry_run_local_only_flag(self, run_script, scaffolded_project: Path):
        """--local-only flag works with --dry-run."""
        brain = scaffolded_project
        project_dir = brain.parent
        
        result = run_script("reset_brain.py", [str(project_dir), "--dry-run", "--local-only"])
        
        assert result.returncode == 0
        assert "local-only" in result.stdout.lower() or "skipped" in result.stdout.lower()

    def test_dry_run_mempalace_only_flag(self, run_script, scaffolded_project: Path):
        """--mempalace-only flag works with --dry-run."""
        brain = scaffolded_project
        project_dir = brain.parent
        
        result = run_script("reset_brain.py", [str(project_dir), "--dry-run", "--mempalace-only"])
        
        assert result.returncode == 0

    def test_dry_run_shows_file_counts(self, run_script, scaffolded_project: Path):
        """Output shows file counts for directories."""
        brain = scaffolded_project
        project_dir = brain.parent
        
        result = run_script("reset_brain.py", [str(project_dir), "--dry-run"])
        
        assert result.returncode == 0
        # Should show file counts (e.g., "files" or numeric counts)
        assert "files" in result.stdout.lower() or "Summary:" in result.stdout

    def test_dry_run_default_behavior(self, run_script, scaffolded_project: Path):
        """Even without --dry-run flag, it doesn't delete (dry-run is default)."""
        brain = scaffolded_project
        project_dir = brain.parent
        
        # Get a file that should exist
        index_path = brain / "wiki" / "index.md"
        assert index_path.exists()
        
        # Run without explicit --dry-run (should default to dry-run)
        result = run_script("reset_brain.py", [str(project_dir)])
        
        # Verify script ran successfully - check exit code and output contains dry-run confirmation
        assert result.returncode == 0
        assert "dry" in result.stdout.lower() or "would be deleted" in result.stdout or "Summary:" in result.stdout
        
        # File should still exist (default is dry-run)
        assert index_path.exists()

    def test_dry_run_nonexistent_project(self, run_script, tmp_project: Path):
        """Non-existent project path returns non-zero exit, no traceback."""
        nonexistent = tmp_project / "does-not-exist"
        
        result = run_script("reset_brain.py", [str(nonexistent), "--dry-run"])
        
        # Should fail gracefully
        assert "Traceback" not in result.stderr
        assert result.returncode != 0

    def test_dry_run_summary_output(self, run_script, scaffolded_project: Path):
        """Output includes a summary section."""
        brain = scaffolded_project
        project_dir = brain.parent
        
        result = run_script("reset_brain.py", [str(project_dir), "--dry-run"])
        
        assert result.returncode == 0
        assert "Summary:" in result.stdout

    def test_dry_run_preserves_source_files(self, run_script, tmp_project: Path):
        """Create a source file outside .brain/, ensure it's not mentioned as deletion target."""
        project_dir = tmp_project / "test-project"
        project_dir.mkdir(parents=True, exist_ok=True)
        
        # Create a source file outside .brain/
        source_file = project_dir / "src" / "main.py"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_text("# Source file\nprint('hello')\n", encoding="utf-8")
        
        # Scaffold the brain
        result_scaffold = run_script("scaffold_brain.py", [str(project_dir), "Test Project"])
        assert result_scaffold.returncode == 0
        
        # Run dry-run
        result = run_script("reset_brain.py", [str(project_dir), "--dry-run"])
        
        assert result.returncode == 0
        # Source file should not be mentioned as deletion target
        assert "src/main.py" not in result.stdout
        # Verify source file still exists
        assert source_file.exists()

    def test_dry_run_graphify_out_reported(self, run_script, scaffolded_project: Path):
        """Output mentions graphify-out directory."""
        brain = scaffolded_project
        project_dir = brain.parent
        
        result = run_script("reset_brain.py", [str(project_dir), "--dry-run"])
        
        assert result.returncode == 0
        # Should mention graphify-out
        assert "graphify-out" in result.stdout or "graphify" in result.stdout.lower()
