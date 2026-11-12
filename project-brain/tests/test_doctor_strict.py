"""WP2 regression tests: doctor --strict gate, receipts, coverage fix (KD-12,13).

Regression-first: --strict, receipts, and inventory-based coverage did not
exist when these were written — watched failing before implementation.
"""

import json
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))


def green_project(run_script, tmp_path: Path) -> Path:
    """A project that passes both strict gates (lint clean + inventory complete)."""
    proj = tmp_path / "strict-project"
    (proj / "src").mkdir(parents=True)
    (proj / "src" / "app.ts").write_text("export const a = 1;\n" * 10, encoding="utf-8")
    (proj / "package.json").write_text('{"name": "strict-project"}\n', encoding="utf-8")
    result = run_script("scaffold_brain.py", [str(proj), "Strict"])
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
            + '{{src package.json:1 "strict-project"}}\n'
            + '{{src .brain/raw/git/history-digest.md:1-2 "Branch"}}\n')
    page.write_text(fm + body, encoding="utf-8")
    return proj


def doctor_json(run_script, proj: Path, *extra: str) -> tuple[int, dict]:
    r = run_script("doctor.py", [str(proj), "--json", *extra])
    return r.returncode, json.loads(r.stdout)


class TestCoverageFix:
    def test_coverage_zero_without_inventory_never_100(self, run_script, tmp_project: Path):
        proj = tmp_project / "cov-project"
        proj.mkdir(parents=True)
        result = run_script("scaffold_brain.py", [str(proj), "Cov"])
        assert result.returncode == 0, result.stderr
        code, data = doctor_json(run_script, proj)
        assert code == 0
        assert data["health"]["Coverage"]["score"] == 0
        assert "inventory" in data["health"]["Coverage"]["note"]

    def test_coverage_from_inventory(self, run_script, tmp_project: Path):
        proj = green_project(run_script, tmp_project)
        run_script("brain_inventory.py", [str(proj), "inventory"])
        code, data = doctor_json(run_script, proj)
        assert code == 0
        assert data["health"]["Coverage"]["score"] == 100
        assert data["inventory"]["completion"]["complete"] is True


class TestStrictGate:
    def test_strict_fails_without_inventory_and_writes_receipt(self, run_script, tmp_project: Path):
        proj = tmp_project / "strict-project"
        proj.mkdir(parents=True)
        result = run_script("scaffold_brain.py", [str(proj), "Strict"])
        assert result.returncode == 0, result.stderr
        code, data = doctor_json(run_script, proj, "--strict")
        assert code == 1
        assert data["gates"]["coverage"]["status"] == "could-not-run"
        runs = sorted((proj / ".brain/audit/runs").iterdir())
        assert len(runs) == 1
        receipt = json.loads((runs[0] / "run.json").read_text(encoding="utf-8"))
        assert receipt["gates"]["coverage"]["status"] == "could-not-run"
        assert receipt["status"] == "partial"
        assert receipt["strict"] is True

    def test_strict_fails_on_lint_errors(self, run_script, tmp_project: Path):
        proj = green_project(run_script, tmp_project)
        run_script("brain_inventory.py", [str(proj), "inventory"])
        page = proj / ".brain/wiki/decisions/D.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            "---\ntitle: D\ntype: decision\ncreated: 2026-01-01\nupdated: 2026-01-01\n"
            "status: accepted\nsources: []\ntags: [d]\nrationale_source: bogus\n---\n\n# D\n\nBecause.\n",
            encoding="utf-8")
        code, data = doctor_json(run_script, proj, "--strict")
        assert code == 1
        assert data["gates"]["lint_errors"]["status"] == "failed"
        assert "invalid_rationale_source" in data["gates"]["lint_errors"]["error_categories"]

    def test_strict_green_project_passes(self, run_script, tmp_project: Path):
        proj = green_project(run_script, tmp_project)
        run_script("brain_inventory.py", [str(proj), "inventory"])
        code, data = doctor_json(run_script, proj, "--strict")
        assert code == 0, json.dumps(data)
        assert data["status"] == "passed-for-scope"
        assert all(g["status"] == "passed" for g in data["gates"].values())
        # one receipt per run: a second run creates a second receipt dir
        run_script("doctor.py", [str(proj), "--strict", "--json"])
        runs = sorted((proj / ".brain/audit/runs").iterdir())
        assert len(runs) == 2

    def test_strict_fails_when_inventory_incomplete(self, run_script, tmp_project: Path):
        proj = tmp_project / "strict-project"
        proj.mkdir(parents=True)
        (proj / "src").mkdir(parents=True)
        (proj / "src" / "app.ts").write_text("export const a = 1;\n" * 10, encoding="utf-8")
        result = run_script("scaffold_brain.py", [str(proj), "Strict"])
        assert result.returncode == 0, result.stderr
        run_script("brain_inventory.py", [str(proj), "inventory"])  # nothing covered
        code, data = doctor_json(run_script, proj, "--strict")
        assert code == 1
        assert data["gates"]["coverage"]["status"] == "failed"

    def test_bin_wrapper_strict(self, run_script, tmp_project: Path):
        proj = green_project(run_script, tmp_project)
        run_script("brain_inventory.py", [str(proj), "inventory"])
        wrapper = PLUGIN_ROOT / "bin" / "project-brain-doctor"
        result = subprocess.run(["bash", str(wrapper), str(proj), "--strict"],
                                capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
