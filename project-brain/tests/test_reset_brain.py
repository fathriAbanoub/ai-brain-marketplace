"""Tests for reset_brain.py script.

All tests use --dry-run only – never test actual deletion.
"""

import json

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
        
        # Run without any MemPalace integration available
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
        assert "MemPalace" in result.stdout

    def test_no_brain_directory_error(self, run_script, tmp_project: Path):
        """Gracefully reports missing .brain, no traceback."""
        project_dir = tmp_project / "no-brain-project"
        project_dir.mkdir(parents=True, exist_ok=True)
        
        result = run_script("reset_brain.py", [str(project_dir), "--dry-run"])
        
        # Should report error gracefully without Python traceback
        assert "Traceback" not in result.stderr
        # Should mention brain directory issue
        assert result.returncode != 0 or ".brain" in result.stdout or "not found" in result.stdout.lower()

    def test_dry_run_reports_mempalace_handled_by_skill(self, run_script, scaffolded_project: Path):
        """Dry-run says MemPalace is the skill's job, not the script's."""
        brain = scaffolded_project
        project_dir = brain.parent

        result = run_script("reset_brain.py", [str(project_dir), "--dry-run"])

        assert result.returncode == 0
        assert "mempalace" in result.stdout.lower()
        assert "skill" in result.stdout.lower()

    def test_dry_run_reports_claude_md_block(self, run_script, scaffolded_project: Path):
        """Dry-run reports whether the injected CLAUDE.md block is present."""
        brain = scaffolded_project
        project_dir = brain.parent

        result = run_script("reset_brain.py", [str(project_dir), "--dry-run"])

        assert result.returncode == 0
        assert "# Project Brain" in result.stdout
        assert "snippet" in result.stdout.lower()

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
        
        assert result.returncode == 0
        assert "Traceback" not in result.stderr
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


class TestVerifyResetTranscript:
    """--verify-reset-transcript: contract checks over a recorded JSONL
    transcript (offline — no MCP, no deletion)."""

    def _write_transcript(self, root: Path, records: list) -> None:
        audit_dir = root / ".brain" / "audit"
        audit_dir.mkdir(parents=True)
        lines = "\n".join(json.dumps(r) for r in records) + "\n"
        (audit_dir / "reset-transcript.jsonl").write_text(lines, encoding="utf-8")

    def test_deletes_without_post_delete_evidence_report_missing_evidence(
            self, run_script, tmp_path: Path):
        """A pre-delete taxonomy record is cross-check state, NOT wing-cleared
        evidence: deletions with no evidence after the last delete fail with
        the 'no wing-cleared evidence' message (every delete record resets the
        evidence flag, so a pre-delete record can never stand in for the
        post-delete verification)."""
        self._write_transcript(tmp_path, [
            {"tool": "mempalace_get_taxonomy", "wing": "w", "drawer_count": 2},
            {"tool": "mempalace_list_drawers", "wing": "w", "limit": 100,
             "returned_ids": ["d1", "d2"]},
            {"tool": "mempalace_delete_drawers", "wing": "w",
             "ids": ["d1", "d2"], "deleted_ids": ["d1", "d2"]},
        ])
        result = run_script("reset_brain.py",
                            [str(tmp_path), "--verify-reset-transcript", "w"])
        assert result.returncode == 1
        assert "no wing-cleared evidence after the last delete" in result.stderr
        assert "wing not cleared at end" not in result.stderr

    def test_post_delete_taxonomy_zero_verifies(self, run_script, tmp_path: Path):
        """The same transcript plus a final drawer_count-0 record verifies."""
        self._write_transcript(tmp_path, [
            {"tool": "mempalace_get_taxonomy", "wing": "w", "drawer_count": 2},
            {"tool": "mempalace_list_drawers", "wing": "w", "limit": 100,
             "returned_ids": ["d1", "d2"]},
            {"tool": "mempalace_delete_drawers", "wing": "w",
             "ids": ["d1", "d2"], "deleted_ids": ["d1", "d2"]},
            {"tool": "mempalace_get_taxonomy", "wing": "w", "drawer_count": 0},
        ])
        result = run_script("reset_brain.py",
                            [str(tmp_path), "--verify-reset-transcript", "w"])
        assert result.returncode == 0, result.stderr

    def test_noop_empty_wing_verifies_with_pre_delete_evidence_only(
            self, run_script, tmp_path: Path):
        """An already-empty wing (taxonomy drawer_count 0, nothing enumerated,
        nothing deleted) verifies: with zero deletes, the pre-delete evidence
        IS the clearing evidence — 'after the last delete' is vacuous."""
        self._write_transcript(tmp_path, [
            {"tool": "mempalace_list_wings", "wings": ["other"]},
            {"tool": "mempalace_get_taxonomy", "wing": "w", "drawer_count": 0},
        ])
        result = run_script("reset_brain.py",
                            [str(tmp_path), "--verify-reset-transcript", "w"])
        assert result.returncode == 0, result.stderr
