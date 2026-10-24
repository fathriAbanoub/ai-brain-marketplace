"""Tests for doctor.py script."""

import pytest
import sys
import tempfile
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from doctor import graphify_freshness  # noqa: E402


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


# --- ITEM 3: detect deletions using manifest ----------------------------------

def test_graphify_deletion_in_manifest_reports_stale():
    """Deleted file present in manifest reports stale."""
    import json
    import subprocess
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True, capture_output=True)

        src = root / "src.py"
        src.write_text("print('hello')")
        subprocess.run(["git", "add", "src.py"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)

        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()

        graphify_out = root / "graphify-out"
        graphify_out.mkdir()
        report = graphify_out / "GRAPH_REPORT.md"
        report.write_text(f"Built from commit: `{head[:12]}`\n")

        manifest = graphify_out / "manifest.json"
        manifest.write_text(json.dumps({"src.py": {"mtime": 1000, "seen": 1}}))

        src.unlink()

        status, reason = graphify_freshness(root)
        assert status == "stale", "Deleted file in manifest must report stale"
        assert "uncommitted changes" in reason


def test_graphify_deletion_not_in_manifest_reports_fresh():
    """Deleted file not in manifest reports fresh."""
    import json
    import subprocess
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True, capture_output=True)

        src = root / "src.py"
        src.write_text("print('hello')")
        subprocess.run(["git", "add", "src.py"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)

        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()

        graphify_out = root / "graphify-out"
        graphify_out.mkdir()
        report = graphify_out / "GRAPH_REPORT.md"
        report.write_text(f"Built from commit: `{head[:12]}`\n")

        manifest = graphify_out / "manifest.json"
        manifest.write_text(json.dumps({"other.py": {"mtime": 1000, "seen": 1}}))

        src.unlink()

        status, reason = graphify_freshness(root)
        assert status == "fresh", "Deleted file not in manifest must report fresh"


def test_graphify_deletion_absolute_key_reports_stale():
    """Deleted file with absolute path key in manifest reports stale."""
    import json
    import subprocess
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True, capture_output=True)

        src = root / "src.py"
        src.write_text("print('hello')")
        subprocess.run(["git", "add", "src.py"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)

        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()

        graphify_out = root / "graphify-out"
        graphify_out.mkdir()
        report = graphify_out / "GRAPH_REPORT.md"
        report.write_text(f"Built from commit: `{head[:12]}`\n")

        manifest = graphify_out / "manifest.json"
        manifest.write_text(json.dumps({str(src.resolve()): {"mtime": 1000, "seen": 1}}))

        src.unlink()

        status, reason = graphify_freshness(root)
        assert status == "stale", "Deleted file with absolute key must report stale"


def test_graphify_missing_manifest_no_exception():
    """Missing manifest does not raise exception."""
    import subprocess
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True, capture_output=True)

        src = root / "src.py"
        src.write_text("print('hello')")
        subprocess.run(["git", "add", "src.py"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)

        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()

        graphify_out = root / "graphify-out"
        graphify_out.mkdir()
        report = graphify_out / "GRAPH_REPORT.md"
        report.write_text(f"Built from commit: `{head[:12]}`\n")

        src.unlink()

        status, reason = graphify_freshness(root)
        assert status == "fresh", "Missing manifest must not crash and keep old behavior"


def test_graphify_corrupt_manifest_no_exception():
    """Corrupt manifest does not raise exception."""
    import subprocess
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True, capture_output=True)

        src = root / "src.py"
        src.write_text("print('hello')")
        subprocess.run(["git", "add", "src.py"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)

        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()

        graphify_out = root / "graphify-out"
        graphify_out.mkdir()
        report = graphify_out / "GRAPH_REPORT.md"
        report.write_text(f"Built from commit: `{head[:12]}`\n")

        manifest = graphify_out / "manifest.json"
        manifest.write_text("not json at all")

        src.unlink()

        status, reason = graphify_freshness(root)
        assert status == "fresh", "Corrupt manifest must not crash"


def test_graphify_list_manifest_no_exception():
    """Manifest that is a JSON list does not raise exception."""
    import json
    import subprocess
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True, capture_output=True)

        src = root / "src.py"
        src.write_text("print('hello')")
        subprocess.run(["git", "add", "src.py"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)

        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()

        graphify_out = root / "graphify-out"
        graphify_out.mkdir()
        report = graphify_out / "GRAPH_REPORT.md"
        report.write_text(f"Built from commit: `{head[:12]}`\n")

        manifest = graphify_out / "manifest.json"
        manifest.write_text(json.dumps(["src.py"]))

        src.unlink()

        status, reason = graphify_freshness(root)
        assert status == "fresh", "List manifest must not crash"


def test_graphify_renamed_file_old_path_in_manifest_reports_stale():
    """Renamed file whose old path is in manifest reports stale."""
    import json
    import subprocess
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True, capture_output=True)

        old = root / "old.py"
        old.write_text("print('hello')")
        subprocess.run(["git", "add", "old.py"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)

        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()

        graphify_out = root / "graphify-out"
        graphify_out.mkdir()
        report = graphify_out / "GRAPH_REPORT.md"
        report.write_text(f"Built from commit: `{head[:12]}`\n")

        manifest = graphify_out / "manifest.json"
        manifest.write_text(json.dumps({"old.py": {"mtime": 1000, "seen": 1}}))

        old.rename(root / "new.py")

        status, reason = graphify_freshness(root)
        assert status == "stale", "Renamed file with old path in manifest must report stale"
