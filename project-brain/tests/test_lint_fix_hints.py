"""0.10.0 lint-message tests (finding 4): every rule with a mechanical fix
must name the fix, and the fix must be the SAME for every instance of the
rule — script-shaped commands, not per-file hand edits (the agent that
hand-edited the script-generated index.md ~5 times created new duplicates).
"""

import json
from pathlib import Path

import pytest


class TestIndexFixHints:
    def test_duplicate_index_entry_suggests_reindex(self, run_script, scaffolded_project: Path):
        project = scaffolded_project.parent
        index = scaffolded_project / "wiki" / "index.md"
        text = index.read_text(encoding="utf-8")
        text = text.replace(
            "## Architecture\n",
            "## Architecture\n- [[architecture/System Overview]] - duplicated entry\n",
            1,
        )
        index.write_text(text, encoding="utf-8")
        result = run_script("lint_brain.py", [str(project), "--json"])
        issues = json.loads(result.stdout)["issues"]
        dupes = [i for i in issues if i["category"] == "duplicate_index_entry"]
        assert dupes
        assert all("--reindex" in i["message"] for i in dupes)
        assert all("never hand-edit index.md" in i["message"] for i in dupes)

    def test_index_entry_target_missing_suggests_reindex(self, run_script, scaffolded_project: Path):
        project = scaffolded_project.parent
        index = scaffolded_project / "wiki" / "index.md"
        index.write_text(
            index.read_text(encoding="utf-8") + "\n- [[architecture/Ghost Page]] - gone\n",
            encoding="utf-8",
        )
        result = run_script("lint_brain.py", [str(project), "--json"])
        issues = json.loads(result.stdout)["issues"]
        ghosts = [i for i in issues if i["category"] == "index_entry_target_missing"]
        assert ghosts
        assert all("--reindex" in i["message"] for i in ghosts)


class TestWikilinkFixHints:
    def test_non_wiki_file_target_suggests_code_span(self, run_script, scaffolded_project: Path):
        """[[<existing non-wiki file>]] → the fix is a code-span path, not a
        wikilink and not a hand edit (observed live: [[graphify-out/...]])."""
        project = scaffolded_project.parent
        brief = scaffolded_project / "state" / "session-brief.md"
        assert brief.is_file()
        page = scaffolded_project / "wiki" / "concepts" / "LinksFile.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            "---\ntitle: Links File\ntype: concept\ncreated: 2026-01-01\nupdated: 2026-01-01\n"
            "status: draft\nsources: []\ntags: [t]\n---\n\n# Links File\n\nSee [[.brain/state/session-brief.md]].\n",
            encoding="utf-8",
        )
        result = run_script("lint_brain.py", [str(project), "--json"])
        issues = json.loads(result.stdout)["issues"]
        broken = [i for i in issues if i["category"] == "broken_wikilink"]
        assert broken
        assert all("code-span path" in i["message"] for i in broken)

    def test_missing_page_target_suggests_creating_page(self, run_script, scaffolded_project: Path):
        project = scaffolded_project.parent
        page = scaffolded_project / "wiki" / "concepts" / "BrokenLink.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            "---\ntitle: Broken Link\ntype: concept\ncreated: 2026-01-01\nupdated: 2026-01-01\n"
            "status: draft\nsources: []\ntags: [t]\n---\n\n# Broken Link\n\nSee [[No Such Page]].\n",
            encoding="utf-8",
        )
        result = run_script("lint_brain.py", [str(project), "--json"])
        issues = json.loads(result.stdout)["issues"]
        broken = [i for i in issues if i["category"] == "broken_wikilink"]
        assert broken
        assert all("create the target page" in i["message"] for i in broken)


class TestCitationAndBriefFixHints:
    def _drift_issues(self, run_script, project: Path) -> list[dict]:
        result = run_script("lint_brain.py", [str(project), "--json"])
        issues = json.loads(result.stdout)["issues"]
        return [i for i in issues if i["category"] == "citation_drift"]

    def test_citation_drift_missing_file_suggests_verify(self, run_script, scaffolded_project: Path):
        project = scaffolded_project.parent
        page = scaffolded_project / "wiki" / "concepts" / "Drift.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            "---\ntitle: Drift\ntype: concept\ncreated: 2026-01-01\nupdated: 2026-01-01\n"
            "status: draft\nsources: []\ntags: [t]\n---\n\n# Drift\n\n{{src no/such/file.ts:1-2 \"x\"}}\n",
            encoding="utf-8",
        )
        drift = self._drift_issues(run_script, project)
        assert drift
        assert all("--verify" in i["message"] for i in drift)
        assert all('grep -n "<anchor>"' in i["message"] for i in drift), (
            "every variant must teach locating the real lines with grep -n"
        )

    def test_citation_drift_anchor_not_found_suggests_grep(self, run_script, scaffolded_project: Path):
        """The variant that actually occurred live: a real file whose cited
        lines do NOT contain the anchor. It must carry the same grep -n hint
        as the other variants (fix-up round: it was the only one without)."""
        project = scaffolded_project.parent
        src = project / "real.ts"
        src.write_text("export const a = 1;\nexport const b = 2;\n", encoding="utf-8")
        page = scaffolded_project / "wiki" / "concepts" / "AnchorDrift.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            "---\ntitle: Anchor Drift\ntype: concept\ncreated: 2026-01-01\nupdated: 2026-01-01\n"
            "status: draft\nsources: []\ntags: [t]\n---\n\n# Anchor Drift\n\n"
            '{{src real.ts:1-2 "the anchor text is not here"}}\n',
            encoding="utf-8",
        )
        drift = self._drift_issues(run_script, project)
        assert drift
        assert all("anchor text not found" in i["message"] for i in drift)
        assert all('grep -n "the anchor text is not here" real.ts' in i["message"] for i in drift)
        assert all("--verify" in i["message"] for i in drift)

    def test_citation_drift_out_of_range_suggests_grep(self, run_script, scaffolded_project: Path):
        project = scaffolded_project.parent
        src = project / "short.ts"
        src.write_text("line one\n", encoding="utf-8")
        page = scaffolded_project / "wiki" / "concepts" / "RangeDrift.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            "---\ntitle: Range Drift\ntype: concept\ncreated: 2026-01-01\nupdated: 2026-01-01\n"
            "status: draft\nsources: []\ntags: [t]\n---\n\n# Range Drift\n\n"
            '{{src short.ts:40-50 "line one"}}\n',
            encoding="utf-8",
        )
        drift = self._drift_issues(run_script, project)
        assert drift
        assert all("outside short.ts" in i["message"] for i in drift)
        assert all('grep -n "line one" short.ts' in i["message"] for i in drift)
        assert all("--verify" in i["message"] for i in drift)

    def test_stale_brief_names_the_update(self, run_script, scaffolded_project: Path):
        import re
        project = scaffolded_project.parent
        brief = scaffolded_project / "state" / "session-brief.md"
        content = brief.read_text(encoding="utf-8")
        brief.write_text(
            re.sub(r"^updated:.*$", "updated: 2020-01-01", content, flags=re.MULTILINE | re.IGNORECASE),
            encoding="utf-8",
        )
        result = run_script("lint_brain.py", [str(project), "--json"])
        issues = json.loads(result.stdout)["issues"]
        stale = [i for i in issues if i["category"] == "stale_session_brief"]
        assert stale
        assert all("update .brain/state/session-brief.md" in i["message"] for i in stale)


class TestSourcesObjectGuard:
    def test_flow_style_object_entry_reports_one_issue(self, run_script, scaffolded_project: Path):
        """`sources: [{ path: README.md, reliability: primary }]` used to be
        comma-split into two bogus half-paths with a misleading "fix the path
        or create the file" hint. Now: ONE issue per page naming the real
        rule, and no missing_source_path noise (fix-up round)."""
        project = scaffolded_project.parent
        (project / "README.md").write_text("# Real file\n", encoding="utf-8")
        page = scaffolded_project / "wiki" / "sources" / "ObjSource.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            "---\ntitle: Obj Source\ntype: source\ncreated: 2026-01-01\nupdated: 2026-01-01\n"
            "status: draft\nsources: [{ path: README.md, reliability: primary }]\ntags: [t]\n"
            "---\n\n# Obj Source\n\nA real file cited as a flow-style object.\n",
            encoding="utf-8",
        )
        result = run_script("lint_brain.py", [str(project), "--json"])
        issues = json.loads(result.stdout)["issues"]
        page_issues = [i for i in issues if i["file"].endswith("ObjSource.md")]
        bogus = [i for i in page_issues if i["category"] == "missing_source_path"]
        assert not bogus, f"flow-style entries must not produce path errors: {bogus}"
        invalid = [i for i in page_issues if i["category"] == "invalid_sources_entry"]
        assert len(invalid) == 1, f"exactly ONE issue per page, got {len(invalid)}"
        message = invalid[0]["message"]
        assert "plain root-relative path strings" in message
        assert "not {path: …} objects" in message
        assert "reliability belongs only in the frontmatter of wiki/sources/* pages" in message

    def test_plain_path_entries_still_checked(self, run_script, scaffolded_project: Path):
        """The guard must not suppress genuine missing-path errors."""
        project = scaffolded_project.parent
        page = scaffolded_project / "wiki" / "sources" / "GoneSource.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            "---\ntitle: Gone\ntype: source\ncreated: 2026-01-01\nupdated: 2026-01-01\n"
            "status: draft\nsources: [no/such/file.txt]\ntags: [t]\n---\n\n# Gone\n\nBody.\n",
            encoding="utf-8",
        )
        result = run_script("lint_brain.py", [str(project), "--json"])
        issues = json.loads(result.stdout)["issues"]
        assert any(
            i["category"] == "missing_source_path" and "no/such/file.txt" in i["message"]
            for i in issues
        )


class TestScaffoldFixHints:
    def test_missing_required_path_suggests_reinit(self, run_script, scaffolded_project: Path):
        project = scaffolded_project.parent
        (scaffolded_project / "tasks" / "next-actions.md").unlink()
        result = run_script("lint_brain.py", [str(project), "--json"])
        issues = json.loads(result.stdout)["issues"]
        missing = [i for i in issues if i["category"] == "missing_required_path"]
        assert missing
        assert all("project-brain-init" in i["message"] for i in missing)

    def test_missing_brain_suggests_init(self, run_script, tmp_project: Path):
        project = tmp_project / "no-brain"
        project.mkdir(parents=True, exist_ok=True)
        result = run_script("lint_brain.py", [str(project), "--json"])
        issues = json.loads(result.stdout)["issues"]
        assert any(
            i["category"] == "missing_brain" and "project-brain-init" in i["message"]
            for i in issues
        )
