"""WP1 regression tests: lint structure checks (KD-05, KD-06, KD-08).
"""

import json
from pathlib import Path


def lint_json(run_script, project: Path) -> dict:
    result = run_script("lint_brain.py", [str(project), "--json"])
    return json.loads(result.stdout)


class TestIndexChecks:
    def test_duplicate_index_entries_flagged(self, run_script, scaffolded_project: Path):
        """KD-05: a page listed twice (also under different sections) is an error."""
        project = scaffolded_project.parent
        index = scaffolded_project / "wiki" / "index.md"
        text = index.read_text(encoding="utf-8")
        line = "- [[architecture/System Overview]] - duplicated entry\n"
        # Simulate the observed failure: same page under two sections.
        text = text.replace(
            "## Architecture\n",
            "## Architecture\n" + line,
            1,
        )
        index.write_text(text, encoding="utf-8")
        report = lint_json(run_script, project)
        cats = [i["category"] for i in report["issues"]]
        assert "duplicate_index_entry" in cats, cats

    def test_index_entry_to_missing_page_flagged(self, run_script, scaffolded_project: Path):
        """KD-05: an index entry pointing at a page that does not exist is an error."""
        project = scaffolded_project.parent
        index = scaffolded_project / "wiki" / "index.md"
        text = index.read_text(encoding="utf-8")
        text += "\n- [[architecture/Ghost Page]] - does not exist\n"
        index.write_text(text, encoding="utf-8")
        report = lint_json(run_script, project)
        cats = [i["category"] for i in report["issues"]]
        assert "index_entry_target_missing" in cats, cats

    def test_reindex_generates_exact_index(self, run_script, scaffolded_project: Path):
        """--reindex regenerates the index from the real page list; lint is then clean."""
        project = scaffolded_project.parent
        # Add a real page and corrupt the index.
        page = scaffolded_project / "wiki" / "concepts" / "New Concept.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            "---\ntitle: New Concept\ntype: concept\ncreated: 2026-01-01\nupdated: 2026-01-01\n"
            "status: active\nsources: []\ntags: [t]\n---\n# New Concept\n\nSome body text long enough.\n",
            encoding="utf-8",
        )
        index = scaffolded_project / "wiki" / "index.md"
        index.write_text("# Project Brain Index\n\n## Architecture\n- [[architecture/Ghost]] - nope\n", encoding="utf-8")
        result = run_script("lint_brain.py", [str(project), "--reindex"])
        assert result.returncode == 0
        text = index.read_text(encoding="utf-8")
        assert "[[concepts/New Concept]]" in text
        assert "Ghost" not in text
        report = lint_json(run_script, project)
        cats = [i["category"] for i in report["issues"]]
        assert "duplicate_index_entry" not in cats
        assert "index_entry_target_missing" not in cats
        assert "missing_index_entry" not in cats


class TestBriefTaskRule:
    def test_checklist_in_brief_flagged(self, run_script, scaffolded_project: Path):
        """KD-06: task checklists belong in tasks/next-actions.md only."""
        project = scaffolded_project.parent
        brief = scaffolded_project / "state" / "session-brief.md"
        brief.write_text(
            "# Session Brief\n\nUpdated: 2026-01-01 10:00\n\n## Next actions\n\n- [ ] Do the thing.\n",
            encoding="utf-8",
        )
        report = lint_json(run_script, project)
        cats = [i["category"] for i in report["issues"]]
        assert "task_checklist_in_brief" in cats, cats


class TestNestedGraphifyOut:
    def test_nested_graphify_out_flagged(self, run_script, scaffolded_project: Path):
        """KD-08: a nested graphify-out/graphify-out/ cache copy is detected."""
        project = scaffolded_project.parent
        nested = project / "graphify-out" / "graphify-out"
        nested.mkdir(parents=True)
        (nested / "cache").mkdir()
        report = lint_json(run_script, project)
        cats = [i["category"] for i in report["issues"]]
        assert "nested_graphify_output" in cats, cats
