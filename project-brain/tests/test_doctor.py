"""Tests for doctor.py script."""

import re
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from doctor import (  # noqa: E402
    SESSION_BRIEF_REL,
    WING_WARNING,
    graphify_freshness,
    mempalace_wing_check,
    memory_sync,
    print_health,
)
from scaffold_brain import BLOCKED_WING_MARKER, BRIEF_LINE_SEPARATOR, resolve_wing_name  # noqa: E402

FULL_MEMORY_SYNC_SCORE = 100
NO_MEMORY_SYNC_SCORE = 0
DIARY_LOG_FILENAME = "20261121.md"
BRAIN_SKILL = PLUGIN_ROOT / "skills" / "brain" / "SKILL.md"
BLOCKED_WING_NOTE = " — do not mine; resolve via /project-brain:reset"
UNVERIFIED_WING_NOTE = " — collision or unverified check; do not mine; resolve via /project-brain:reset"
DIFFERENT_WING_SUFFIX = "_other"
BLOCKED_MINING_MESSAGE = "mining is blocked"
RESET_COMMAND = "/project-brain:reset"
UNREADABLE_BRIEF_MESSAGE = "cannot read"
DO_NOT_MINE_MESSAGE = "do not mine"
DOCTOR_SCRIPT = "doctor.py"
STRICT_FLAG = "--strict"
CLI_SUCCESS = 0
CLI_FAILURE = 1
TRACEBACK_MARKER = "Traceback"
UNKNOWN_BRIEF_DATE_MESSAGE = "session brief date unknown"
TEXT_ENCODING = "utf-8"


class TestMemorySync:
    def test_documented_diary_log_returns_full_score(self, tmp_path):
        text = BRAIN_SKILL.read_text(encoding=TEXT_ENCODING)
        init = text[text.index("## Initialize"):text.index("## Other modes")]
        heading = re.search(r"^\s*## \[HH:MM\] diary \| <title>$", init, re.M)
        bullet = re.search(r"^\s*- MemPalace diary written \(agent <diary agent>\)$", init, re.M)
        assert heading, "Initialize must document a diary log heading"
        assert bullet, "Initialize must document the MemPalace diary-write bullet"
        log = tmp_path / ".brain" / "log" / DIARY_LOG_FILENAME
        log.parent.mkdir(parents=True)
        log.write_text(
            heading.group().strip() + "\n" + bullet.group().strip() + "\n",
            encoding=TEXT_ENCODING,
        )
        score, _ = memory_sync(tmp_path)
        assert score == FULL_MEMORY_SYNC_SCORE

    def test_zero_score_note_explains_log_repair(self, tmp_path):
        log = tmp_path / ".brain" / "log"
        for state in ("missing", "empty", "without diary"):
            if state == "empty":
                log.mkdir(parents=True)
            elif state == "without diary":
                (log / DIARY_LOG_FILENAME).write_text("Initialized brain.\n", encoding=TEXT_ENCODING)
            score, note = memory_sync(tmp_path)
            assert score == NO_MEMORY_SYNC_SCORE
            assert "append" in note.lower()
            assert ".brain/log/<YYYYMMDD>.md" in note
            assert "MemPalace diary write" in note


class TestBlockedWing:
    def test_recorded_wing_marker_blocks_mining(self, scaffolded_project):
        root = scaffolded_project.parent
        wing, _ = resolve_wing_name(root)
        brief = root / SESSION_BRIEF_REL
        brief.write_text(f"{BLOCKED_WING_MARKER} {wing}{BLOCKED_WING_NOTE}\n", encoding=TEXT_ENCODING)
        severity, note = mempalace_wing_check(root)
        assert severity == WING_WARNING
        assert wing in note
        assert BLOCKED_MINING_MESSAGE in note.lower()
        assert RESET_COMMAND in note

    def test_unverified_check_marker_blocks_recorded_wing(self, scaffolded_project):
        root = scaffolded_project.parent
        wing, _ = resolve_wing_name(root)
        brief = root / SESSION_BRIEF_REL
        content = brief.read_text(encoding=TEXT_ENCODING)
        brief.write_text(
            f"{BLOCKED_WING_MARKER} {wing}{UNVERIFIED_WING_NOTE}{BRIEF_LINE_SEPARATOR}{content}",
            encoding=TEXT_ENCODING,
        )
        severity, note = mempalace_wing_check(root)
        assert severity == WING_WARNING
        assert wing in note
        assert BLOCKED_MINING_MESSAGE in note.lower()
        assert RESET_COMMAND in note

    def test_different_wing_marker_leaves_result_unchanged(self, scaffolded_project):
        root = scaffolded_project.parent
        original = mempalace_wing_check(root)
        wing, _ = resolve_wing_name(root)
        (root / SESSION_BRIEF_REL).write_text(
            f"{BLOCKED_WING_MARKER} {wing}{DIFFERENT_WING_SUFFIX}{BLOCKED_WING_NOTE}\n",
            encoding=TEXT_ENCODING,
        )
        assert mempalace_wing_check(root) == original

    def test_no_brief_leaves_result_unchanged(self, scaffolded_project):
        root = scaffolded_project.parent
        original = mempalace_wing_check(root)
        (root / SESSION_BRIEF_REL).unlink()
        assert mempalace_wing_check(root) == original

    def test_unreadable_brief_warns_not_to_mine(self, scaffolded_project):
        root = scaffolded_project.parent
        brief = root / SESSION_BRIEF_REL
        brief.unlink()
        brief.mkdir()
        severity, note = mempalace_wing_check(root)
        assert severity == WING_WARNING
        assert UNREADABLE_BRIEF_MESSAGE in note.lower()
        assert str(SESSION_BRIEF_REL) in note
        assert DO_NOT_MINE_MESSAGE in note.lower()

    def test_directory_brief_warns_through_plain_and_strict_cli(self, run_script, scaffolded_project):
        root = scaffolded_project.parent
        brief = root / SESSION_BRIEF_REL
        brief.unlink()
        brief.mkdir()
        for flags, expected_exit in (([], CLI_SUCCESS), ([STRICT_FLAG], CLI_FAILURE)):
            result = run_script(DOCTOR_SCRIPT, [str(root), *flags])
            assert TRACEBACK_MARKER not in result.stderr
            assert result.returncode == expected_exit
            assert UNREADABLE_BRIEF_MESSAGE in result.stdout.lower()
            assert str(SESSION_BRIEF_REL) in result.stdout
            assert DO_NOT_MINE_MESSAGE in result.stdout.lower()
            assert UNKNOWN_BRIEF_DATE_MESSAGE in result.stdout


class TestDoctorBoundary:
    """A sub-score of exactly 70 must pass (the doctor flags
    strictly-below-70 only, and skill text says 'at or above 70' is done)."""

    def test_score_70_is_not_flagged(self, capsys, tmp_path):
        # completeness: 7/10 pages fully formed -> exactly 70. Active pages
        # need a source (frontmatter entry or inline citation) to count.
        root = tmp_path / "boundary-70"
        brain = root / ".brain"
        (brain / "wiki").mkdir(parents=True)
        (brain / "wiki" / "index.md").write_text("# index\n", encoding=TEXT_ENCODING)
        for i in range(10):
            good = i < 7
            page = brain / "wiki" / f"p{i}.md"
            if good:
                page.write_text(
                    "---\ntitle: t\ntype: concept\nstatus: active\nsources: [src.md]\n---\n"
                    f"# p{i}\n[[p0]] link\n",
                    encoding=TEXT_ENCODING,
                )
                (brain / "wiki" / "index.md").open("a", encoding=TEXT_ENCODING).write(f"[[p{i}]]\n")
            else:
                page.write_text("", encoding=TEXT_ENCODING)  # 0 points: no heading/frontmatter
        # Verify the score really is exactly 70 before asserting the boundary.
        from doctor import completeness
        score, _ = completeness(root)
        assert score == 70, f"fixture drift: completeness={score}"
        print_health(root)
        out = capsys.readouterr().out
        completeness_line = next(l for l in out.splitlines() if "Completeness" in l)
        assert "BELOW REPAIR THRESHOLD" not in completeness_line

    def test_score_below_70_is_flagged(self, capsys, tmp_path):
        root = tmp_path / "boundary-69"
        brain = root / ".brain"
        (brain / "wiki").mkdir(parents=True)
        (brain / "wiki" / "index.md").write_text("# index\n", encoding=TEXT_ENCODING)
        for i in range(10):
            good = i < 6
            page = brain / "wiki" / f"p{i}.md"
            if good:
                page.write_text(
                    "---\ntitle: t\ntype: concept\nstatus: active\nsources: [src.md]\n---\n"
                    f"# p{i}\n[[p0]] link\n",
                    encoding=TEXT_ENCODING,
                )
                (brain / "wiki" / "index.md").open("a", encoding=TEXT_ENCODING).write(f"[[p{i}]]\n")
            else:
                page.write_text("", encoding=TEXT_ENCODING)
        from doctor import completeness
        score, _ = completeness(root)
        assert score < 70
        print_health(root)
        out = capsys.readouterr().out
        completeness_line = next(l for l in out.splitlines() if "Completeness" in l)
        assert "BELOW REPAIR THRESHOLD" in completeness_line

    def test_lifecycle_doc_says_at_or_above(self):
        """Skill text and doctor must agree on the boundary semantics."""
        text = (PLUGIN_ROOT / "skills" / "brain" / "references" / "brain-lifecycle.md").read_text(encoding=TEXT_ENCODING)
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
        brief_path = project_dir / SESSION_BRIEF_REL
        brief_path.unlink()
        
        result = run_script("doctor.py", [str(project_dir)])
        
        # Should report missing session-brief
        output_lower = result.stdout.lower()
        assert "session" in output_lower and ("missing" in output_lower or "brief" in output_lower)
