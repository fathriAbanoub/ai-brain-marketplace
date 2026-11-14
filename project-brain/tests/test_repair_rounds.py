"""Fix-up round: the repair-limit counter.

The old skill rule counted `doctor --strict` receipts only, but the observed
failure loop was `lint --verify` (lint writes no receipt), and an in-memory
count dies at compaction. The counter lives on disk at
.brain/state/repair-rounds, is shared by lint_brain.py and doctor.py (one
named constant, MAX_REPAIR_ROUNDS), and prints the STOP message at the limit.

0.10.0 fix: the counter is keyed PER GATE (`lint=`, `doctor-strict=`). The
previous single shared counter was reset by ANY passing run, so a loop that
alternated a passing lint with a failing `doctor --strict` repaired forever
without ever reaching the limit. A passing run now resets only its own gate;
legacy single-integer files are tolerated (the count applies to both gates).

These tests drive the scripts as subprocesses, so "survives a second process
run" is exercised for real.
"""

import json
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
COUNTER_REL = Path(".brain") / "state" / "repair-rounds"
STOP_MESSAGE = "repair round 3/3 — STOP and write the honest report"
OVER_LIMIT_MESSAGE = "repair limit exceeded (4 > 3) — STOP and write the honest report"


def failing_page(brain: Path) -> Path:
    """A wiki page with an invalid rationale_source — a guaranteed lint error."""
    page = brain / "wiki" / "decisions" / "Broken.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        "---\ntitle: Broken\ntype: decision\ncreated: 2026-01-01\nupdated: 2026-01-01\n"
        "status: accepted\nsources: []\ntags: [d]\nrationale_source: bogus\n---\n\n# Broken\n\nBecause.\n",
        encoding="utf-8",
    )
    return page


@pytest.fixture
def proj(run_script, tmp_project: Path) -> Path:
    project = tmp_project / "repair-project"
    project.mkdir(parents=True)
    result = run_script("scaffold_brain.py", [str(project), "Repair"])
    assert result.returncode == 0, result.stderr
    return project


class TestLintCounter:
    def test_counter_increments_on_failing_run(self, run_script, proj: Path):
        failing_page(proj / ".brain")
        result = run_script("lint_brain.py", [str(proj)])
        assert result.returncode != 0
        assert "repair round 1/3" in result.stderr
        assert "lint=1" in (proj / COUNTER_REL).read_text(encoding="utf-8")

    def test_counter_resets_on_passing_run(self, run_script, proj: Path):
        failing_page(proj / ".brain")
        assert run_script("lint_brain.py", [str(proj)]).returncode != 0
        failing_page(proj / ".brain").unlink()
        result = run_script("lint_brain.py", [str(proj)])
        assert result.returncode == 0, result.stderr
        assert "repair round" not in result.stderr
        assert "lint=0" in (proj / COUNTER_REL).read_text(encoding="utf-8")

    def test_message_at_the_limit(self, run_script, proj: Path):
        failing_page(proj / ".brain")
        for expected in (1, 2):
            result = run_script("lint_brain.py", [str(proj)])
            assert f"repair round {expected}/3" in result.stderr
            assert "STOP" not in result.stderr
        result = run_script("lint_brain.py", [str(proj)])
        assert STOP_MESSAGE in result.stderr, result.stderr

    def test_over_limit_prints_over_limit_message(self, run_script, proj: Path):
        """Past the limit the message must not read `repair round 4/3`; an
        explicit over-limit message prints instead."""
        failing_page(proj / ".brain")
        (proj / COUNTER_REL).write_text("lint=3\ndoctor-strict=0\n", encoding="utf-8")
        result = run_script("lint_brain.py", [str(proj)])
        assert result.returncode != 0
        assert OVER_LIMIT_MESSAGE in result.stderr, result.stderr
        assert "repair round " not in result.stderr

    def test_legacy_single_integer_file_is_tolerated(self, run_script, proj: Path):
        """A counter file written before the per-gate fix: the legacy count
        applies to the gate being run (an over-limit legacy count still stops)."""
        failing_page(proj / ".brain")
        (proj / COUNTER_REL).write_text("2\n", encoding="utf-8")
        result = run_script("lint_brain.py", [str(proj)])
        assert result.returncode != 0
        assert STOP_MESSAGE in result.stderr, result.stderr
        # The file is migrated to the per-gate format on the next write.
        content = (proj / COUNTER_REL).read_text(encoding="utf-8")
        assert "lint=3" in content and "doctor-strict=" in content


class TestPerGateCounter:
    def test_alternating_lint_pass_and_doctor_fail_reaches_the_limit(self, run_script, proj: Path):
        """The bug this fix targets: a shared counter reset by every passing
        lint let a lint-pass / doctor-fail loop repair forever. Per gate, the
        doctor count grows across lint passes and stops at the limit."""
        run_script("brain_inventory.py", [str(proj), "inventory"])
        for round_no in (1, 2):
            assert run_script("lint_brain.py", [str(proj)]).returncode == 0
            result = run_script("doctor.py", [str(proj), "--strict", "--json"])
            assert result.returncode != 0
            assert f"repair round {round_no}/3" in result.stderr, result.stderr
        assert run_script("lint_brain.py", [str(proj)]).returncode == 0
        result = run_script("doctor.py", [str(proj), "--strict", "--json"])
        assert STOP_MESSAGE in result.stderr, result.stderr

    def test_a_passing_run_resets_only_its_own_gate(self, run_script, proj: Path):
        """Two lint failures, then a passing doctor run: the lint count is
        preserved (only doctor-strict resets to 0)."""
        failing_page(proj / ".brain")
        run_script("lint_brain.py", [str(proj)])
        run_script("lint_brain.py", [str(proj)])
        run_script("brain_inventory.py", [str(proj), "inventory"])
        run_script("doctor.py", [str(proj), "--strict", "--json"])  # doctor may fail; lint stays 2
        content = (proj / COUNTER_REL).read_text(encoding="utf-8")
        assert "lint=2" in content
        assert "doctor-strict=" in content
        # The lint count continues from 2, not from 0.
        result = run_script("lint_brain.py", [str(proj)])
        assert "repair round 3/3" in result.stderr


class TestDoctorCounter:
    def test_doctor_strict_counts_in_its_own_process(self, run_script, proj: Path):
        run_script("brain_inventory.py", [str(proj), "inventory"])
        result = run_script("doctor.py", [str(proj), "--strict", "--json"])
        assert result.returncode != 0
        assert "repair round 1/3" in result.stderr
        # A second failing doctor run (fresh process) increments again.
        result = run_script("doctor.py", [str(proj), "--strict", "--json"])
        assert "repair round 2/3" in result.stderr

    def test_doctor_count_continues_across_processes_to_the_limit(self, run_script, proj: Path):
        run_script("brain_inventory.py", [str(proj), "inventory"])
        run_script("doctor.py", [str(proj), "--strict", "--json"])
        run_script("doctor.py", [str(proj), "--strict", "--json"])
        result = run_script("doctor.py", [str(proj), "--strict", "--json"])
        assert result.returncode != 0
        assert STOP_MESSAGE in result.stderr, result.stderr
        # The JSON payload on stdout stays parseable (note goes to stderr).
        json.loads(result.stdout)

    def test_passing_strict_run_resets_strict_gate(self, run_script, tmp_project: Path):
        proj = green_project(run_script, tmp_project)
        failing_page(proj / ".brain")
        # Seed doctor-strict with a FAILING strict run first: the lint runs
        # below increment lint, not doctor-strict, so the reset assertion is
        # only meaningful when the counter was actually nonzero.
        seeded = run_script("doctor.py", [str(proj), "--strict", "--json"])
        assert seeded.returncode != 0
        content = (proj / COUNTER_REL).read_text(encoding="utf-8")
        assert "doctor-strict=1" in content, content
        assert run_script("lint_brain.py", [str(proj)]).returncode != 0
        assert run_script("lint_brain.py", [str(proj)]).returncode != 0
        failing_page(proj / ".brain").unlink()
        run_script("brain_inventory.py", [str(proj), "inventory"])
        result = run_script("doctor.py", [str(proj), "--strict", "--json"])
        assert result.returncode == 0, result.stderr
        content = (proj / COUNTER_REL).read_text(encoding="utf-8")
        assert "doctor-strict=0" in content


def green_project(run_script, tmp_path: Path) -> Path:
    """A project that passes both strict gates (mirrors the recipe in
    test_doctor_strict.py: lint clean + inventory complete)."""
    proj = tmp_path / "green-repair"
    (proj / "src").mkdir(parents=True)
    (proj / "src" / "app.ts").write_text("export const a = 1;\n" * 10, encoding="utf-8")
    (proj / "package.json").write_text('{"name": "green-repair"}\n', encoding="utf-8")
    result = run_script("scaffold_brain.py", [str(proj), "GreenRepair"])
    assert result.returncode == 0, result.stderr
    for extra in ("CLAUDE.md", "CLAUDE.project-brain.snippet.md", ".graphifyignore"):
        p = proj / extra
        if p.exists():
            p.unlink()
    digest = proj / ".brain/raw/git/history-digest.md"
    digest.parent.mkdir(parents=True, exist_ok=True)
    digest.write_text("# Git History\n\nBranch: main\n", encoding="utf-8")
    page = proj / ".brain/wiki/concepts/Coverage.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    fm = ("---\ntitle: T\ntype: concept\ncreated: 2026-01-01\nupdated: 2026-01-01\n"
          "status: active\nsources: []\ntags: [t]\n---\n")
    body = ("This page carries a real, checkable summary of the project. " * 4
            + '{{src src/app.ts:1-3 "export const a = 1;"}}\n'
            + '{{src package.json:1 "green-repair"}}\n'
            + '{{src .brain/raw/git/history-digest.md:1-2 "Branch"}}\n')
    page.write_text(fm + body, encoding="utf-8")
    return proj


class TestSkillRefersToScriptOutput:
    def test_work_loop_step8_names_the_script_output(self):
        """The skill must refer to the printed round, not describe receipts."""
        text = (PLUGIN_ROOT / "skills" / "brain" / "SKILL.md").read_text(encoding="utf-8")
        assert "repair round N/3" in text
        assert ".brain/state/repair-rounds" in text
        assert "three non-passing receipts" not in text
