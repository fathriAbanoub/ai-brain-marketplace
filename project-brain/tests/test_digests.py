"""WP5+WP6 regression tests: git-history digest and graph digest.

Regression-first: both subcommands did not exist when these were written —
watched failing (argparse: invalid choice) before implementation.
"""

import json
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))
import brain_inventory as bi  # noqa: E402


def git(proj: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(proj), *args], check=True, capture_output=True)


def make_git_project(run_script, tmp_path: Path) -> Path:
    proj = tmp_path / "dig-project"
    (proj / "src").mkdir(parents=True)
    (proj / "src" / "a.ts").write_text("export const a = 1;\n", encoding="utf-8")
    (proj / "docs").mkdir()
    (proj / "docs" / "adr-001.md").write_text("# ADR 1\n", encoding="utf-8")
    result = run_script("scaffold_brain.py", [str(proj), "Dig Project"])
    assert result.returncode == 0, result.stderr
    git(proj, "init", "-q", "-b", "main")
    git(proj, "-c", "user.email=a@example.com", "-c", "user.name=alice", "add", "-A")
    git(proj, "-c", "user.email=a@example.com", "-c", "user.name=alice",
        "commit", "-q", "-m", "init: first commit")
    (proj / "src" / "b.ts").write_text("export const b = 2;\n", encoding="utf-8")
    git(proj, "-c", "user.email=b@example.com", "-c", "user.name=bob", "add", "-A")
    git(proj, "-c", "user.email=b@example.com", "-c", "user.name=bob",
        "commit", "-q", "-m", "refactor: replace legacy engine")
    git(proj, "checkout", "-q", "-b", "feature")
    (proj / "src" / "c.ts").write_text("export const c = 3;\n", encoding="utf-8")
    git(proj, "-c", "user.email=a@example.com", "-c", "user.name=alice", "add", "-A")
    git(proj, "-c", "user.email=a@example.com", "-c", "user.name=alice",
        "commit", "-q", "-m", "add c")
    git(proj, "checkout", "-q", "main")
    git(proj, "-c", "user.email=a@example.com", "-c", "user.name=alice",
        "merge", "-q", "--no-ff", "-m", "Merge branch 'feature'", "feature")
    git(proj, "tag", "v0.1.0")
    return proj


class TestGitDigest:
    def test_digest_content_deterministic(self, run_script, tmp_project: Path):
        proj = make_git_project(run_script, tmp_project)
        result = run_script("brain_inventory.py", [str(proj), "git-digest"])
        assert result.returncode == 0, result.stderr
        text = (proj / bi.GIT_DIGEST_REL).read_text(encoding="utf-8")
        assert "Branch: main" in text
        assert "Commits:" in text
        assert "replace legacy engine" in text      # decision-keyword subject
        assert "Merge branch 'feature'" in text     # merge commit listed
        assert "adr-001.md" in text                 # ADR doc list
        assert "alice" in text and "bob" in text    # authors
        assert "v0.1.0" in text                     # tag
        first = text
        run_script("brain_inventory.py", [str(proj), "git-digest"])
        assert (proj / bi.GIT_DIGEST_REL).read_text(encoding="utf-8") == first

    def test_no_git_writes_unavailable_never_fails(self, run_script, tmp_project: Path):
        proj = tmp_project / "plain-project"
        (proj / "src").mkdir(parents=True)
        result = run_script("scaffold_brain.py", [str(proj), "Plain"])
        assert result.returncode == 0, result.stderr
        result = run_script("brain_inventory.py", [str(proj), "git-digest"])
        assert result.returncode == 0
        text = (proj / bi.GIT_DIGEST_REL).read_text(encoding="utf-8")
        assert "git: unavailable" in text


def write_graph(proj: Path, nodes: list, links: list) -> None:
    gdir = proj / "graphify-out"
    gdir.mkdir(parents=True, exist_ok=True)
    (gdir / "graph.json").write_text(json.dumps({
        "directed": False, "multigraph": False,
        "graph": {"schema_version": 1, "graphify_version": "test"},
        "nodes": nodes, "links": links, "hyperedges": [],
        "built_at_commit": "0" * 40,
    }), encoding="utf-8")


class TestGraphDigest:
    def test_digest_derived_from_graph_json(self, run_script, tmp_project: Path):
        proj = tmp_project / "graph-project"
        proj.mkdir(parents=True)
        result = run_script("scaffold_brain.py", [str(proj), "Graphy"])
        assert result.returncode == 0, result.stderr
        nodes = [
            {"id": "n1", "label": "Alpha", "community": 1, "community_name": "One", "source_file": "src/a.ts", "file_type": "code"},
            {"id": "n2", "label": "Beta", "community": 1, "community_name": "One", "source_file": "src/b.ts", "file_type": "code"},
            {"id": "n3", "label": "Gamma", "community": 2, "community_name": "Two", "source_file": "src/c.ts", "file_type": "code"},
        ]
        links = [
            {"source": "n1", "target": "n2", "relation": "calls", "confidence": "EXTRACTED", "weight": 1.0},
            {"source": "n3", "target": "n1", "relation": "imports", "confidence": "INFERRED", "weight": 0.5},
            {"source": "n2", "target": "n1", "relation": "calls", "confidence": "EXTRACTED", "weight": 1.0},
        ]
        write_graph(proj, nodes, links)
        result = run_script("brain_inventory.py", [str(proj), "graph-digest"])
        assert result.returncode == 0, result.stderr
        text = (proj / bi.GRAPH_DIGEST_REL).read_text(encoding="utf-8")
        assert "One" in text and "Two" in text       # communities by name
        assert "Alpha" in text                        # god node (degree 3)
        assert "src/a.ts" in text                     # god node's file
        assert "cross-community" in text.lower()      # n3 -> n1 crosses communities
        assert "INFERRED" in text                     # confidence breakdown + limit note
        assert "counted from graph.json" in text      # provenance of numbers
        first = text
        run_script("brain_inventory.py", [str(proj), "graph-digest"])
        assert (proj / bi.GRAPH_DIGEST_REL).read_text(encoding="utf-8") == first

    def test_missing_and_malformed_fail_closed(self, run_script, tmp_project: Path):
        proj = tmp_project / "graph-project"
        proj.mkdir(parents=True)
        result = run_script("scaffold_brain.py", [str(proj), "Graphy"])
        assert result.returncode == 0, result.stderr
        result = run_script("brain_inventory.py", [str(proj), "graph-digest"])
        assert result.returncode == 2
        (proj / "graphify-out").mkdir(parents=True)
        (proj / "graphify-out" / "graph.json").write_text("{not json", encoding="utf-8")
        result = run_script("brain_inventory.py", [str(proj), "graph-digest"])
        assert result.returncode == 2

    def test_bin_wrapper_git_digest(self, run_script, tmp_project: Path):
        proj = make_git_project(run_script, tmp_project)
        wrapper = PLUGIN_ROOT / "bin" / "project-brain-inventory"
        result = subprocess.run(["bash", str(wrapper), str(proj), "git-digest"],
                                capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
        assert (proj / bi.GIT_DIGEST_REL).is_file()
