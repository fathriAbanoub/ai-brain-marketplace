"""Tests for doctor.py script."""

import pytest
import sys
import tempfile
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from doctor import graphify_freshness, print_health  # noqa: E402


class TestDoctorBoundary:
    """CodeRabbit #14: a sub-score of exactly 70 must pass (the doctor flags
    strictly-below-70 only, and skill text says 'at or above 70' is done)."""

    def test_score_70_is_not_flagged(self, capsys):
        # completeness: 7/10 pages fully formed -> exactly 70.
        import tempfile
        root = Path(tempfile.mkdtemp())
        brain = root / ".brain"
        (brain / "wiki").mkdir(parents=True)
        (brain / "wiki" / "index.md").write_text("# index\n", encoding="utf-8")
        for i in range(10):
            good = i < 7
            page = brain / "wiki" / f"p{i}.md"
            if good:
                page.write_text(
                    "---\ntitle: t\ntype: concept\nstatus: active\n---\n"
                    f"# p{i}\n[[p0]] link\n",
                    encoding="utf-8",
                )
                (brain / "wiki" / "index.md").open("a", encoding="utf-8").write(f"[[p{i}]]\n")
            else:
                page.write_text("", encoding="utf-8")  # 0 points: no heading/frontmatter
        # Verify the score really is exactly 70 before asserting the boundary.
        from doctor import completeness
        score, _ = completeness(root)
        assert score == 70, f"fixture drift: completeness={score}"
        print_health(root)
        out = capsys.readouterr().out
        completeness_line = next(l for l in out.splitlines() if "Completeness" in l)
        assert "BELOW REPAIR THRESHOLD" not in completeness_line

    def test_score_below_70_is_flagged(self, capsys):
        import tempfile
        root = Path(tempfile.mkdtemp())
        brain = root / ".brain"
        (brain / "wiki").mkdir(parents=True)
        (brain / "wiki" / "index.md").write_text("# index\n", encoding="utf-8")
        for i in range(10):
            good = i < 6
            page = brain / "wiki" / f"p{i}.md"
            if good:
                page.write_text(
                    "---\ntitle: t\ntype: concept\nstatus: active\n---\n"
                    f"# p{i}\n[[p0]] link\n",
                    encoding="utf-8",
                )
                (brain / "wiki" / "index.md").open("a", encoding="utf-8").write(f"[[p{i}]]\n")
            else:
                page.write_text("", encoding="utf-8")
        from doctor import completeness
        score, _ = completeness(root)
        assert score < 70
        print_health(root)
        out = capsys.readouterr().out
        completeness_line = next(l for l in out.splitlines() if "Completeness" in l)
        assert "BELOW REPAIR THRESHOLD" in completeness_line

    def test_lifecycle_doc_says_at_or_above(self):
        """Skill text and doctor must agree on the boundary semantics."""
        text = (PLUGIN_ROOT / "skills" / "brain" / "references" / "brain-lifecycle.md").read_text(encoding="utf-8")
        assert "at or above 70" in text
        assert "scores are above 70 or" not in text


class TestDoctor:
    """Test suite for doctor.py."""

    def test_doctor_exits_zero_on_scaffolded_project(self, run_script, scaffolded_project: Path):
        """Doctor exits 0 on a freshly scaffolded project."""
        brain = scaffolded_project
        project_dir = brain.parent
        
        result = run_script("doctor.py", [str(project_dir)])
        
        assert result.returncode == 0

    def test_doctor_stdout_mentions_brain(self, run_script, scaffolded_project: Path):
        """Output mentions 'brain' in stdout."""
        brain = scaffolded_project
        project_dir = brain.parent
        
        result = run_script("doctor.py", [str(project_dir)])
        
        assert result.returncode == 0
        output_lower = result.stdout.lower()
        assert "brain" in output_lower

    def test_doctor_contains_health_metric_labels(self, run_script, scaffolded_project: Path):
        """Output contains health metric labels like Completeness, Freshness, Coverage, Memory."""
        brain = scaffolded_project
        project_dir = brain.parent
        
        result = run_script("doctor.py", [str(project_dir)])
        
        assert result.returncode == 0
        output = result.stdout
        # Check for at least some health metrics
        assert "Completeness" in output or "Freshness" in output or "Coverage" in output or "Health" in output

    def test_doctor_graceful_degradation_no_brain(self, run_script, tmp_project: Path):
        """Doctor handles missing .brain directory gracefully."""
        project_dir = tmp_project / "no-brain"
        project_dir.mkdir(parents=True, exist_ok=True)
        
        result = run_script("doctor.py", [str(project_dir)])
        
        # Should not crash with traceback
        assert "Traceback" not in result.stderr
        # Should report missing brain
        output_lower = result.stdout.lower()
        assert "brain" in output_lower or ".brain" in output_lower

    def test_doctor_reports_project_root(self, run_script, scaffolded_project: Path):
        """Output reports the project root path."""
        brain = scaffolded_project
        project_dir = brain.parent
        
        result = run_script("doctor.py", [str(project_dir)])
        
        assert result.returncode == 0
        # Should mention project root
        assert "Project root" in result.stdout or str(project_dir) in result.stdout

    def test_doctor_health_score_format(self, run_script, scaffolded_project: Path):
        """Health score is formatted as X/100."""
        brain = scaffolded_project
        project_dir = brain.parent
        
        result = run_script("doctor.py", [str(project_dir)])
        
        assert result.returncode == 0
        # Should have health score format like "Health: XX/100"
        import re
        match = re.search(r"Health[:\s]+(\d+)/100", result.stdout, re.IGNORECASE)
        assert match is not None, f"Health score format not found in output: {result.stdout}"

    def test_doctor_wing_size_report(self, run_script, scaffolded_project: Path):
        """Output includes MemPalace wing size report."""
        brain = scaffolded_project
        project_dir = brain.parent
        
        result = run_script("doctor.py", [str(project_dir)])
        
        assert result.returncode == 0
        # Should mention wing or MemPalace
        output_lower = result.stdout.lower()
        assert "wing" in output_lower or "mempalace" in output_lower

    def test_doctor_default_cwd(self, run_script, scaffolded_project: Path):
        """Doctor works when called without explicit path (uses cwd)."""
        brain = scaffolded_project
        project_dir = brain.parent
        
        # Run from project directory with cwd set to project_dir
        result = run_script("doctor.py", [], cwd=project_dir)
        
        # Should work with default cwd behavior - no traceback and exit 0
        assert result.returncode == 0 and "Traceback" not in result.stderr

    def test_doctor_missing_session_brief(self, run_script, scaffolded_project: Path):
        """Doctor reports missing session-brief.md."""
        brain = scaffolded_project
        project_dir = brain.parent
        
        # Remove session-brief.md
        brief_path = brain / "state" / "session-brief.md"
        brief_path.unlink()
        
        result = run_script("doctor.py", [str(project_dir)])
        
        # Should report missing session-brief
        output_lower = result.stdout.lower()
        assert "session" in output_lower and ("missing" in output_lower or "brief" in output_lower)
