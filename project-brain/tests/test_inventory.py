"""WP3 regression+unit tests: inventory, tiers, statuses, completion, crossrefs.

Regression-first: every test here failed before scripts/brain_inventory.py
existed (collection error) — watched failing 2026-10-29 before implementation.
"""

import json
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))
import brain_inventory as bi  # noqa: E402


def write_page(brain: Path, rel: str, body: str, status: str = "active") -> Path:
    page = brain / "wiki" / rel
    page.parent.mkdir(parents=True, exist_ok=True)
    fm = (f"---\ntitle: T\ntype: concept\ncreated: 2026-01-01\nupdated: 2026-01-01\n"
          f"status: {status}\nsources: []\ntags: [t]\n---\n")
    page.write_text(fm + body, encoding="utf-8")
    return page


def substantive() -> str:
    return "This page carries a real, checkable summary of the project. " * 4


def make_source_project(run_script, tmp_path: Path) -> Path:
    proj = tmp_path / "inv-project"
    (proj / "src").mkdir(parents=True)
    (proj / "src" / "engine.ts").write_text(
        "\n".join(f"line {i} of engine" for i in range(1, 30)) + "\n", encoding="utf-8")
    (proj / "src" / "util.ts").write_text("export const u = 1;\n" * 5, encoding="utf-8")
    (proj / "src" / "index.ts").write_text("export const entry = true;\n", encoding="utf-8")
    (proj / "tests").mkdir()
    (proj / "tests" / "engine.test.ts").write_text("test('engine', () => {});\n", encoding="utf-8")
    (proj / "docs").mkdir()
    (proj / "docs" / "design.md").write_text(
        "# Design\n\nUses `src/engine.ts` and `src/missing.ts`.\n", encoding="utf-8")
    (proj / "package.json").write_text('{"name": "inv-project"}\n', encoding="utf-8")
    result = run_script("scaffold_brain.py", [str(proj), "Inv Project"])
    assert result.returncode == 0, result.stderr
    # Deterministic unit set for the completion-gate math: drop the
    # scaffold's root-level extras (they would be extra reference units).
    for extra in ("CLAUDE.md", "CLAUDE.project-brain.snippet.md", ".graphifyignore"):
        p = proj / extra
        if p.exists():
            p.unlink()
    return proj


def run_inventory(run_script, proj: Path, subcommand: str = "inventory"):
    return run_script("brain_inventory.py", [str(proj), subcommand])


def load_inventory(proj: Path) -> dict:
    return json.loads((proj / ".brain" / "inventory.json").read_text(encoding="utf-8"))


def units_by_path(inv: dict) -> dict:
    return {u["path"]: u for u in inv["units"]}


class TestInventoryBuild:
    def test_units_kinds_tiers_stable_ids_atomic_recovery(self, run_script, tmp_project: Path):
        proj = make_source_project(run_script, tmp_project)
        result = run_inventory(run_script, proj)
        assert result.returncode == 0, result.stderr
        inv = load_inventory(proj)
        by = units_by_path(inv)
        assert by["src/engine.ts"]["tier"] == "core"
        assert by["src/engine.ts"]["kind"] == "source"
        assert by["src/index.ts"]["kind"] == "entry"
        assert by["package.json"]["kind"] == "manifest"
        assert by["tests/engine.test.ts"]["tier"] == "important"
        assert by["docs/design.md"]["tier"] == "reference"
        assert by[bi.GIT_DIGEST_REL]["kind"] == "git-history"
        # stable ids across runs
        ids1 = [u["id"] for u in inv["units"]]
        run_inventory(run_script, proj)
        ids2 = [u["id"] for u in load_inventory(proj)["units"]]
        assert ids1 == ids2
        # interrupted write (garbage inventory.json) regenerates cleanly
        (proj / ".brain" / "inventory.json").write_text("{not json", encoding="utf-8")
        result = run_inventory(run_script, proj)
        assert result.returncode == 0
        load_inventory(proj)

    def test_deny_list_excludes_sensitive_and_vendored(self, run_script, tmp_project: Path):
        proj = make_source_project(run_script, tmp_project)
        (proj / ".env").write_text("SECRET=1\n", encoding="utf-8")
        (proj / "cert.pem").write_text("-----BEGIN PRIVATE KEY-----\n", encoding="utf-8")
        (proj / "node_modules" / "pkg").mkdir(parents=True)
        (proj / "node_modules" / "pkg" / "i.js").write_text("x\n", encoding="utf-8")
        (proj / "package-lock.json").write_text("{}\n", encoding="utf-8")
        run_inventory(run_script, proj)
        paths = set(units_by_path(load_inventory(proj)))
        assert not any(p.endswith(".env") for p in paths)
        assert "cert.pem" not in paths
        assert "package-lock.json" not in paths
        assert not any(p.startswith("node_modules/") for p in paths)

    def test_git_listing_tracked_untracked_ignored(self, run_script, tmp_project: Path):
        proj = make_source_project(run_script, tmp_project)
        (proj / ".gitignore").write_text("ignored.ts\n", encoding="utf-8")
        (proj / "ignored.ts").write_text("i\n", encoding="utf-8")
        (proj / "fresh.ts").write_text("f\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(proj)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(proj), "add", "src", "package.json", ".gitignore"],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", str(proj), "-c", "user.email=t@example.com", "-c", "user.name=t",
                        "commit", "-m", "init", "-q"], check=True, capture_output=True)
        run_inventory(run_script, proj)
        inv = load_inventory(proj)
        assert inv["source"] == "git-ls-files"
        paths = set(units_by_path(inv))
        assert "fresh.ts" in paths
        assert "ignored.ts" not in paths

    def test_no_git_walk_respects_ignore_files(self, run_script, tmp_project: Path):
        proj = make_source_project(run_script, tmp_project)
        (proj / ".gitignore").write_text("ignored.ts\n", encoding="utf-8")
        (proj / ".graphifyignore").write_text("graphskip.ts\n", encoding="utf-8")
        (proj / "ignored.ts").write_text("i\n", encoding="utf-8")
        (proj / "graphskip.ts").write_text("g\n", encoding="utf-8")
        run_inventory(run_script, proj)
        inv = load_inventory(proj)
        assert inv["source"] == "directory-walk"
        paths = set(units_by_path(inv))
        assert "ignored.ts" not in paths
        assert "graphskip.ts" not in paths
        assert "src/engine.ts" in paths


class TestStatusAndCompletion:
    def test_covered_only_by_substantive_non_draft_pages(self, run_script, tmp_project: Path):
        proj = make_source_project(run_script, tmp_project)
        brain = proj / ".brain"
        write_page(brain, "concepts/Active.md",
                   substantive() + "{{src src/engine.ts:5-10 \"line 6 of engine\"}}\n")
        write_page(brain, "concepts/Draft.md",
                   substantive() + "{{src src/util.ts:1-2 \"export const u = 1;\"}}\n", status="draft")
        write_page(brain, "concepts/Stub.md",
                   "Short. {{src package.json:1 \"inv-project\"}}\n")
        result = run_inventory(run_script, proj)
        assert result.returncode == 0, result.stderr
        by = units_by_path(load_inventory(proj))
        assert by["src/engine.ts"]["status"] == "covered"
        assert by["src/engine.ts"]["cited_by"] == ["wiki/concepts/Active.md"]
        assert by["src/util.ts"]["status"] == "uncovered"
        assert by["src/util.ts"]["reason"]
        assert by["package.json"]["status"] == "uncovered"

    def test_completion_gate_math(self, run_script, tmp_project: Path):
        proj = make_source_project(run_script, tmp_project)
        brain = proj / ".brain"
        digest = proj / bi.GIT_DIGEST_REL
        digest.parent.mkdir(parents=True, exist_ok=True)
        digest.write_text("# Git History\n\nBranch: main\n", encoding="utf-8")
        # weights: core 5x5=25 (engine, util, index, package.json, git-history),
        # important 3 (test), reference 1 (docs/design.md) -> total 29.
        # phase 1: nothing covered
        run_inventory(run_script, proj)
        inv = load_inventory(proj)
        assert inv["completion"]["complete"] is False
        assert inv["completion"]["core_all_covered"] is False
        # phase 2: all core covered, weighted 25/29 = 0.8621 < 0.90 -> incomplete
        write_page(brain, "concepts/Coverage.md", substantive() + "\n".join([
            "{{src src/engine.ts:1-3 \"line 1 of engine\"}}",
            "{{src src/util.ts:1-2 \"export const u = 1;\"}}",
            "{{src src/index.ts:1 \"export const entry = true;\"}}",
            "{{src package.json:1 \"inv-project\"}}",
            "{{src " + bi.GIT_DIGEST_REL + ":1-2 \"Branch\"}}",
        ]) + "\n")
        run_inventory(run_script, proj)
        inv = load_inventory(proj)
        assert inv["completion"]["core_all_covered"] is True
        assert inv["completion"]["weighted_coverage"] < bi.WEIGHTED_COVERAGE_MIN
        assert inv["completion"]["complete"] is False
        # phase 3: also cover the important unit -> 28/29 = 0.9655 >= 0.90
        page = brain / "wiki" / "concepts" / "Coverage.md"
        page.write_text(page.read_text(encoding="utf-8")
                        + "{{src tests/engine.test.ts:1 \"engine\"}}\n", encoding="utf-8")
        run_inventory(run_script, proj)
        inv = load_inventory(proj)
        assert inv["completion"]["complete"] is True


class TestSkips:
    def test_skip_records_closed_reasons_and_core_protection(self, run_script, tmp_project: Path):
        proj = make_source_project(run_script, tmp_project)
        brain = proj / ".brain"
        skips = brain / "inventory-skips.json"
        skips.write_text(json.dumps([{"path": "docs/design.md", "reason": "user-directed"}]),
                         encoding="utf-8")
        result = run_inventory(run_script, proj)
        assert result.returncode == 0, result.stderr
        by = units_by_path(load_inventory(proj))
        assert by["docs/design.md"]["status"] == "skipped"
        # core units cannot be skipped
        skips.write_text(json.dumps([{"path": "src/engine.ts", "reason": "user-directed"}]),
                         encoding="utf-8")
        result = run_inventory(run_script, proj)
        assert result.returncode == 2
        assert "core" in result.stderr
        # reasons come from a closed list
        skips.write_text(json.dumps([{"path": "docs/design.md", "reason": "because"}]),
                         encoding="utf-8")
        result = run_inventory(run_script, proj)
        assert result.returncode == 2
        # unknown paths are rejected
        skips.write_text(json.dumps([{"path": "no/such/file.ts", "reason": "vendored"}]),
                         encoding="utf-8")
        result = run_inventory(run_script, proj)
        assert result.returncode == 2


class TestCrossrefs:
    def test_crossrefs_report_and_all_clear_loop(self, run_script, tmp_project: Path):
        proj = make_source_project(run_script, tmp_project)
        brain = proj / ".brain"
        run_inventory(run_script, proj)  # crossrefs needs inventory.json
        result = run_script("brain_inventory.py", [str(proj), "crossrefs"])
        assert result.returncode == 1, result.stdout + result.stderr
        report = json.loads((brain / "audit" / "crossrefs-report.json").read_text(encoding="utf-8"))
        assert {"doc": "docs/design.md", "ref": "src/missing.ts"} in report["missing"]
        # create the missing path -> clean receipt
        (proj / "src" / "missing.ts").write_text("export {};\n", encoding="utf-8")
        result = run_script("brain_inventory.py", [str(proj), "crossrefs"])
        assert result.returncode == 0, result.stdout + result.stderr
        report = json.loads((brain / "audit" / "crossrefs-report.json").read_text(encoding="utf-8"))
        assert report["missing"] == []
        # WP4 loop: all-clear allowed with a verify stamp + clean receipt
        write_page(brain, "concepts/AllClear.md",
                   substantive() + "{{src src/engine.ts:1-3 \"line 1 of engine\"}}\n"
                   "The README and code have no contradictions.\n")
        run_script("lint_brain.py", [str(proj), "--verify"])
        result = run_script("lint_brain.py", [str(proj), "--json"])
        cats = [i["category"] for i in json.loads(result.stdout)["issues"]]
        assert "forbidden_all_clear" not in cats


class TestWiring:
    def test_bin_wrapper_inventory(self, run_script, tmp_project: Path):
        proj = make_source_project(run_script, tmp_project)
        wrapper = PLUGIN_ROOT / "bin" / "project-brain-inventory"
        result = subprocess.run(["bash", str(wrapper), str(proj), "inventory"],
                                capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
        assert (proj / ".brain" / "inventory.json").is_file()
