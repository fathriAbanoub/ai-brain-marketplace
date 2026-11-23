"""Tests for lint_brain.py script."""

import json
import sys
import pytest
from pathlib import Path
from unittest.mock import patch

PLUGIN_ROOT = Path(__file__).parent.parent
SCRIPTS_PATH_INDEX = 0
sys.path.insert(SCRIPTS_PATH_INDEX, str(PLUGIN_ROOT / "scripts"))

from scaffold_brain import SESSION_BRIEF_PATH  # noqa: E402
import lint_brain as lb  # noqa: E402

LINT_SCRIPT = "lint_brain.py"
CLI_FAILURE = 1
TRACEBACK_MARKER = "Traceback"
UNREADABLE_BRIEF_CATEGORY = lb.UNREADABLE_BRIEF_CATEGORY
READ_HELPER_NAME = "read"
BRIEF_PERMISSION_ERROR = "brief access denied"
BRIEF_READ_DENIALS = ((True, True, True), (False, True, True), (False, False, True))
HASH_HELPER_NAME = "sha256_file"
CITED_PAGE_NAME = "concepts/Unreadable.md"
CITED_PAGE_STATE = "wiki/concepts/Unreadable.md"
CITED_SOURCE_PATH = Path("cited-source.txt")
CITED_RAW_SOURCE_PATH = Path("raw") / CITED_SOURCE_PATH
CONFLICT_DATE_HELPER = "page_updated_date"
RESOLVED_CONFLICT_BODY = (
    '# Open Questions\n\n## Conflict\nstatus: resolved\ndate: 2026-11-22\n'
    'target: [[concepts/Unreadable]]\n'
)
OPEN_QUESTIONS_PATH = Path("wiki/open-questions.md")
CITED_SOURCE_ANCHOR = "# Session Brief"
CITED_SOURCE_LINE = 1
CITED_PAGE_FRONTMATTER = {"title": "Cited source", "type": "concept", "status": "active", "sources": []}
CITED_PAGE_BODY = '# Cited source\n\n{{{{src {path}:{line} "{anchor}"}}}}\n'
CITATION_DRIFT_CATEGORY = lb.CITATION_DRIFT_CATEGORY
UNREADABLE_CITATION_MESSAGE = lb.UNREADABLE_CITATION_MESSAGE
CITATION_PERMISSION_ERROR = "cited source access denied"
EXPECTED_BRIEF_ISSUE_COUNT = 1
CITATION_STATE_DRIFT = lb.CITATION_DRIFT_KEY
CITATION_STATE_FILES = lb.CITATION_FILES_KEY
VERIFICATION_PAGES_KEY = "pages"
REPORT_ISSUES_KEY = "issues"
ISSUE_CATEGORY_KEY = lb.ISSUE_CATEGORY_KEY
ISSUE_MESSAGE_KEY = "message"


class TestLintBrain:
    """Test suite for lint_brain.py."""

    def test_lint_exits_zero_on_fresh_scaffold(self, run_script, scaffolded_project: Path):
        """Fresh scaffold should pass lint with exit 0."""
        brain = scaffolded_project
        project_dir = brain.parent
        
        result = run_script("lint_brain.py", [str(project_dir)])
        
        assert result.returncode == 0

    def test_lint_no_frontmatter_reports_warning(self, run_script, scaffolded_project: Path, make_wiki_page):
        """Create a page without frontmatter. Assert stdout contains 'missing frontmatter' or 'no frontmatter'.
        
        Do NOT assert non-zero exit because missing frontmatter is only a warning in the source.
        """
        brain = scaffolded_project
        project_dir = brain.parent
        
        # Create a page without frontmatter
        test_page = brain / "wiki" / "concepts" / "NoFrontmatter.md"
        test_page.parent.mkdir(parents=True, exist_ok=True)
        test_page.write_text("# No Frontmatter Page\n\nThis page has no frontmatter.\n", encoding="utf-8")
        
        result = run_script("lint_brain.py", [str(project_dir)])
        
        # Should mention missing frontmatter (case insensitive)
        output_lower = result.stdout.lower() + result.stderr.lower()
        assert "frontmatter" in output_lower and ("missing" in output_lower or "no" in output_lower)

    def test_lint_orphan_page_detected(self, run_script, scaffolded_project: Path, make_wiki_page):
        """Page not linked from index; check stdout mentions 'orphan' or 'missing from index'."""
        brain = scaffolded_project
        project_dir = brain.parent
        
        # Create an orphan page not linked from index
        orphan_page = brain / "wiki" / "concepts" / "OrphanPage.md"
        orphan_page.parent.mkdir(parents=True, exist_ok=True)
        orphan_page.write_text(
            "---\ntitle: Orphan Page\ntype: concept\ncreated: 2024-01-01\nupdated: 2024-01-01\nstatus: draft\nsources: []\ntags: [test]\n---\n\n# Orphan Page\n\nThis page is not linked from index.\n",
            encoding="utf-8"
        )
        
        result = run_script("lint_brain.py", [str(project_dir)])
        
        # Should mention orphan or missing from index - check stdout+stderr combined
        output_lower = (result.stdout + result.stderr).lower()
        assert "orphan" in output_lower or "missing" in output_lower or "index" in output_lower

    def test_lint_broken_wikilink_detected(self, run_script, scaffolded_project: Path):
        """Page with [[NonExistentPage]] → exit code != 0, output 'broken' or 'not found'."""
        brain = scaffolded_project
        project_dir = brain.parent
        
        # Create a page with broken wikilink
        broken_page = brain / "wiki" / "concepts" / "BrokenLink.md"
        broken_page.parent.mkdir(parents=True, exist_ok=True)
        broken_page.write_text(
            "---\ntitle: Broken Link Page\ntype: concept\ncreated: 2024-01-01\nupdated: 2024-01-01\nstatus: draft\nsources: []\ntags: [test]\n---\n\n# Broken Link Page\n\nSee [[NonExistentPage]] for more info.\n",
            encoding="utf-8"
        )
        
        result = run_script("lint_brain.py", [str(project_dir)])
        
        # Should detect broken link - check stdout+stderr combined
        assert result.returncode != 0
        output_lower = (result.stdout + result.stderr).lower()
        assert "broken" in output_lower or "not found" in output_lower

    def test_lint_output_contains_summary(self, run_script, scaffolded_project: Path):
        """Output contains summary information."""
        brain = scaffolded_project
        project_dir = brain.parent
        
        result = run_script("lint_brain.py", [str(project_dir)])
        
        assert result.returncode == 0
        # Should have some kind of summary
        assert "summary" in result.stdout.lower() or "issue" in result.stdout.lower() or "error" in result.stdout.lower() or "warn" in result.stdout.lower()

    def test_lint_json_flag_produces_parseable_json(self, run_script, scaffolded_project: Path):
        """--json yields valid JSON with keys issues, summary, timestamp, project_root."""
        brain = scaffolded_project
        project_dir = brain.parent
        
        result = run_script("lint_brain.py", [str(project_dir), "--json"])
        
        assert result.returncode == 0
        
        # Parse JSON
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            pytest.fail("Output is not valid JSON")
        
        # Check required keys
        assert "issues" in data
        assert "summary" in data
        assert "timestamp" in data
        assert "project_root" in data

    def test_lint_missing_source_path(self, run_script, scaffolded_project: Path):
        """A source path that doesn't exist → error/exit non-zero."""
        brain = scaffolded_project
        project_dir = brain.parent
        
        # Create a page with non-existent source path
        bad_source_page = brain / "wiki" / "sources" / "BadSource.md"
        bad_source_page.parent.mkdir(parents=True, exist_ok=True)
        bad_source_page.write_text(
            "---\ntitle: Bad Source\ntype: source\ncreated: 2024-01-01\nupdated: 2024-01-01\nstatus: draft\nsources: ['/nonexistent/path/file.txt']\ntags: [test]\n---\n\n# Bad Source\n\nThis references a non-existent file.\n",
            encoding="utf-8"
        )
        
        result = run_script("lint_brain.py", [str(project_dir)])
        
        # Should report missing source - check stdout+stderr combined
        assert result.returncode != 0
        output_lower = (result.stdout + result.stderr).lower()
        assert "source" in output_lower or "not found" in output_lower or "missing" in output_lower

    def test_lint_directory_brief_reports_issue_without_traceback(self, run_script, scaffolded_project):
        brief = scaffolded_project / SESSION_BRIEF_PATH
        brief.unlink()
        brief.mkdir()
        result = run_script(LINT_SCRIPT, [str(scaffolded_project.parent)])
        assert TRACEBACK_MARKER not in result.stderr
        assert result.returncode == CLI_FAILURE
        assert UNREADABLE_BRIEF_CATEGORY in result.stdout
        assert str(SESSION_BRIEF_PATH) in result.stdout

    def test_brief_permission_error_is_reported_by_all_readers(self, scaffolded_project):
        brief = scaffolded_project / SESSION_BRIEF_PATH
        original_read = lb.read

        for failures in BRIEF_READ_DENIALS:
            denied_reads = iter(failures)

            def denied_brief(path):
                if path == brief and next(denied_reads):
                    raise PermissionError(BRIEF_PERMISSION_ERROR)
                return original_read(path)

            with patch.object(lb, READ_HELPER_NAME, side_effect=denied_brief):
                code, report = lb.build_report(scaffolded_project.parent)
            assert code == CLI_FAILURE
            assert any(issue["category"] == UNREADABLE_BRIEF_CATEGORY for issue in report["issues"])

    def test_lint_stale_session_brief(self, run_script, scaffolded_project: Path):
        """Stale session brief is detected."""
        brain = scaffolded_project
        project_dir = brain.parent
        
        # Modify session-brief to have old date
        brief_path = brain / SESSION_BRIEF_PATH
        content = brief_path.read_text(encoding="utf-8")
        # Replace the entire Updated: metadata line with an old date using regex
        import re
        old_content = re.sub(r'^updated:.*$', 'updated: 2020-01-01', content, flags=re.MULTILINE | re.IGNORECASE)
        brief_path.write_text(old_content, encoding="utf-8")
        
        result = run_script("lint_brain.py", [str(project_dir)])
        
        # Should warn about stale brief (but may still exit 0 since it's a warning) - check stdout+stderr combined
        output_lower = (result.stdout + result.stderr).lower()
        assert "stale" in output_lower or "days" in output_lower or "session" in output_lower

    def test_lint_missing_required_paths(self, run_script, scaffolded_project: Path):
        """Exit non-zero, output 'missing' when required paths are missing."""
        brain = scaffolded_project
        project_dir = brain.parent
        
        # Remove a required file
        required_file = brain / "tasks" / "next-actions.md"
        required_file.unlink()
        
        result = run_script("lint_brain.py", [str(project_dir)])
        
        # Should fail due to missing required path - check stdout+stderr combined
        assert result.returncode != 0
        output_lower = (result.stdout + result.stderr).lower()
        assert "missing" in output_lower

    def test_lint_missing_brain_directory(self, run_script, tmp_project: Path):
        """Exit non-zero, output 'brain' when .brain directory is missing."""
        project_dir = tmp_project / "no-brain"
        project_dir.mkdir(parents=True, exist_ok=True)
        
        result = run_script("lint_brain.py", [str(project_dir)])
        
        # Should fail - no brain directory
        assert result.returncode != 0
        output_lower = result.stdout.lower() + result.stderr.lower()
        assert "brain" in output_lower

    def test_lint_deprecated_frontmatter_fields(self, run_script, scaffolded_project: Path):
        """Use name: instead of title: and check for deprecation warning."""
        brain = scaffolded_project
        project_dir = brain.parent
        
        # Create a page with deprecated 'name:' field
        deprecated_page = brain / "wiki" / "concepts" / "DeprecatedField.md"
        deprecated_page.parent.mkdir(parents=True, exist_ok=True)
        deprecated_page.write_text(
            "---\nname: Deprecated Field Page\ntype: concept\ncreated: 2024-01-01\nupdated: 2024-01-01\nstatus: draft\nsources: []\ntags: [test]\n---\n\n# Deprecated Field Page\n\nThis page uses deprecated name: field.\n",
            encoding="utf-8"
        )
        
        result = run_script("lint_brain.py", [str(project_dir)])
        
        # Should warn about deprecated field - check stdout+stderr combined
        output_lower = (result.stdout + result.stderr).lower()
        assert "deprecated" in output_lower or "name:" in output_lower or "title:" in output_lower

    def test_lint_valid_page_no_errors(self, run_script, scaffolded_project: Path):
        """Create a fully correct page, ensure exit 0."""
        brain = scaffolded_project
        project_dir = brain.parent
        
        # Create a valid page with proper frontmatter and links
        valid_page = brain / "wiki" / "concepts" / "ValidPage.md"
        valid_page.parent.mkdir(parents=True, exist_ok=True)
        valid_page.write_text(
            "---\ntitle: Valid Page\ntype: concept\ncreated: 2024-01-01\nupdated: 2024-01-01\nstatus: active\nsources: []\ntags: [test]\n---\n\n# Valid Page\n\nThis is a properly formatted page.\n\nSee [[index]] for navigation.\n",
            encoding="utf-8"
        )
        
        # Also add it to index to avoid orphan warning
        index_path = brain / "wiki" / "index.md"
        index_content = index_path.read_text(encoding="utf-8")
        if "[[concepts/ValidPage]]" not in index_content:
            index_content += "\n- [[concepts/ValidPage]] - test page\n"
            index_path.write_text(index_content, encoding="utf-8")
        
        result = run_script("lint_brain.py", [str(project_dir)])
        
        # Should pass without errors (warnings may exist but exit 0)
        assert result.returncode == 0


class TestUnreadableCitations:
    def test_live_citations_report_read_and_hash_failures(self, scaffolded_project, make_wiki_page):
        root = scaffolded_project.parent
        source = root / CITED_SOURCE_PATH
        source.write_text(CITED_SOURCE_ANCHOR, encoding="utf-8")
        raw_source = scaffolded_project / CITED_RAW_SOURCE_PATH
        raw_source.parent.mkdir(parents=True, exist_ok=True)
        raw_source.write_text(CITED_SOURCE_ANCHOR, encoding="utf-8")
        for target in (scaffolded_project / SESSION_BRIEF_PATH, source, raw_source):
            path_s = str(target.relative_to(root))
            make_wiki_page(scaffolded_project, CITED_PAGE_NAME, CITED_PAGE_FRONTMATTER,
                           CITED_PAGE_BODY.format(path=path_s, line=CITED_SOURCE_LINE,
                                                  anchor=CITED_SOURCE_ANCHOR))
            for helper_name in (READ_HELPER_NAME, HASH_HELPER_NAME):
                original = getattr(lb, helper_name)

                def denied_target(path):
                    if path == target:
                        raise PermissionError(CITATION_PERMISSION_ERROR)
                    return original(path)

                state = {}
                with patch.object(lb, helper_name, side_effect=denied_target):
                    code, report = lb.build_report(root, citation_state=state)
                assert code == CLI_FAILURE
                assert state[CITED_PAGE_STATE][CITATION_STATE_DRIFT]
                assert path_s not in state[CITED_PAGE_STATE][CITATION_STATE_FILES]
                issues = report[REPORT_ISSUES_KEY]
                if target == scaffolded_project / SESSION_BRIEF_PATH:
                    assert sum(issue[ISSUE_CATEGORY_KEY] == UNREADABLE_BRIEF_CATEGORY
                               for issue in issues) == EXPECTED_BRIEF_ISSUE_COUNT
                else:
                    assert any(issue[ISSUE_CATEGORY_KEY] == CITATION_DRIFT_CATEGORY
                               and UNREADABLE_CITATION_MESSAGE in issue[ISSUE_MESSAGE_KEY]
                               for issue in issues)

    def test_conflict_target_read_failure_is_reported(self, scaffolded_project, make_wiki_page):
        page = make_wiki_page(scaffolded_project, CITED_PAGE_NAME, CITED_PAGE_FRONTMATTER,
                              CITED_SOURCE_ANCHOR)
        (scaffolded_project / OPEN_QUESTIONS_PATH).write_text(RESOLVED_CONFLICT_BODY, encoding="utf-8")
        original_read = lb.read
        original_date = lb.page_updated_date

        def denied_target(path):
            if path == page:
                raise PermissionError(CITATION_PERMISSION_ERROR)
            return original_read(path)

        def check_target_date(path):
            with patch.object(lb, READ_HELPER_NAME, side_effect=denied_target):
                return original_date(path)

        with patch.object(lb, CONFLICT_DATE_HELPER, side_effect=check_target_date):
            code, report = lb.build_report(scaffolded_project.parent)
        assert code == CLI_FAILURE
        assert any(issue[ISSUE_CATEGORY_KEY] == CITATION_DRIFT_CATEGORY
                   and UNREADABLE_CITATION_MESSAGE in issue[ISSUE_MESSAGE_KEY]
                   for issue in report[REPORT_ISSUES_KEY])

    def test_stored_citations_report_hash_failures(self, scaffolded_project, make_wiki_page):
        root = scaffolded_project.parent
        source = root / CITED_SOURCE_PATH
        source.write_text(CITED_SOURCE_ANCHOR, encoding="utf-8")
        make_wiki_page(scaffolded_project, CITED_PAGE_NAME, CITED_PAGE_FRONTMATTER, CITED_SOURCE_ANCHOR)
        for target in (scaffolded_project / SESSION_BRIEF_PATH, source):
            path_s = str(target.relative_to(root))
            verification = {VERIFICATION_PAGES_KEY: {
                CITED_PAGE_STATE: {CITATION_STATE_FILES: {path_s: lb.sha256_file(target)}},
            }}
            (scaffolded_project / lb.VERIFICATION_FILE).write_text(json.dumps(verification), encoding="utf-8")
            original_hash = lb.sha256_file

            def denied_target(path):
                if path == target:
                    raise PermissionError(CITATION_PERMISSION_ERROR)
                return original_hash(path)

            state = {}
            with patch.object(lb, HASH_HELPER_NAME, side_effect=denied_target):
                code, report = lb.build_report(root, citation_state=state)
            assert code == CLI_FAILURE
            assert state[CITED_PAGE_STATE][CITATION_STATE_DRIFT]
            issues = report[REPORT_ISSUES_KEY]
            if target == scaffolded_project / SESSION_BRIEF_PATH:
                assert sum(issue[ISSUE_CATEGORY_KEY] == UNREADABLE_BRIEF_CATEGORY
                           for issue in issues) == EXPECTED_BRIEF_ISSUE_COUNT
            else:
                assert any(issue[ISSUE_CATEGORY_KEY] == CITATION_DRIFT_CATEGORY
                           and UNREADABLE_CITATION_MESSAGE in issue[ISSUE_MESSAGE_KEY]
                           for issue in issues)


class TestSourcePathResolution:
    """CodeRabbit #23B: `sources:` entries resolve root-relative (raw
    evidence), page-relative, or wiki-relative (source-summary pages).
    Missing paths stay errors — never silently converted to wikilinks."""

    def _page_with_sources(self, brain: Path, rel: str, sources: str) -> Path:
        page = brain / rel
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            "---\ntitle: S\ntype: architecture\ncreated: 2024-01-01\nupdated: 2024-01-01\n"
            f"status: active\nsources: [{sources}]\ntags: [t]\n---\n\n# S\n\nBody.\n",
            encoding="utf-8",
        )
        return page

    def test_wiki_relative_source_summary_resolves(self, run_script, scaffolded_project: Path):
        """sources/package-json-primary-source.md resolves against .brain/wiki/."""
        brain = scaffolded_project
        summary = brain / "wiki" / "sources" / "package-json-primary-source.md"
        summary.parent.mkdir(parents=True, exist_ok=True)
        summary.write_text(
            "---\ntitle: package.json primary\ntype: source\ncreated: 2024-01-01\n"
            "updated: 2024-01-01\nstatus: active\nsources: []\nreliability: primary\ntags: []\n---\n\n# package.json primary\n",
            encoding="utf-8",
        )
        page = self._page_with_sources(
            brain, "wiki/architecture/System Overview.md", "sources/package-json-primary-source.md"
        )
        result = run_script("lint_brain.py", [str(brain.parent)])
        issues = (result.stdout + result.stderr).lower()
        assert "sources/package-json-primary-source.md" not in issues or result.returncode == 0

    def test_missing_source_path_still_errors(self, run_script, scaffolded_project: Path):
        """A sources entry pointing nowhere is an error in every resolution mode."""
        brain = scaffolded_project
        self._page_with_sources(
            brain, "wiki/architecture/System Overview.md", "sources/does-not-exist.md"
        )
        result = run_script("lint_brain.py", [str(brain.parent)])
        assert result.returncode != 0
        assert "source path not found" in (result.stdout + result.stderr)

    def test_root_relative_raw_evidence_resolves(self, run_script, scaffolded_project: Path):
        brain = scaffolded_project
        raw = brain / "raw" / "notes" / "evidence.md"
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_text("evidence\n", encoding="utf-8")
        self._page_with_sources(brain, "wiki/concepts/Evidence.md", ".brain/raw/notes/evidence.md")
        result = run_script("lint_brain.py", [str(brain.parent)])
        assert result.returncode == 0

    def test_page_relative_source_resolves(self, run_script, scaffolded_project: Path):
        brain = scaffolded_project
        sibling = brain / "wiki" / "architecture" / "sibling-src.md"
        sibling.write_text("sibling\n", encoding="utf-8")
        self._page_with_sources(brain, "wiki/architecture/System Overview.md", "sibling-src.md")
        result = run_script("lint_brain.py", [str(brain.parent)])
        assert result.returncode == 0


class TestWikilinkCodeSkipping:
    """0.10.1 D4: wikilink-shaped checks skip fenced code blocks and inline
    code spans — the wiki documents code, so `` `[[ghost]]` `` is text, not a
    broken link. Applies to the plain and hybrid detectors alike."""

    FRONTMATTER = ("---\ntitle: Code Docs\ntype: concept\ncreated: 2024-01-01\n"
                   "updated: 2024-01-01\nstatus: draft\nsources: []\ntags: [test]\n---\n")

    def _lint_broken_wikilinks(self, run_script, project_dir: Path) -> list[dict]:
        result = run_script("lint_brain.py", [str(project_dir), "--json"])
        assert result.returncode in (0, 1)
        issues = json.loads(result.stdout)["issues"]
        return [i for i in issues if i["category"] == "broken_wikilink"]

    def test_ghost_links_in_code_are_not_flagged(self, run_script, scaffolded_project: Path):
        brain = scaffolded_project
        page = brain / "wiki" / "concepts" / "CodeDocs.md"
        page.write_text(self.FRONTMATTER + (
            "\nInline `[[Ghost]]` and `arr[[1](2)]` spans are documentation.\n\n"
            "```python\n# [[Ghost]] inside a fence\nx = arr[[1](2)]\n[[Ghost]]\n```\n\n"
            "~~~\n[[Ghost]] and hybrid [[Ghost](somewhere.md)] inside tildes\n~~~\n"),
            encoding="utf-8")
        assert self._lint_broken_wikilinks(run_script, brain.parent) == []

    def test_broken_link_outside_code_still_flagged_with_exact_line(self, run_script, scaffolded_project: Path):
        brain = scaffolded_project
        page = brain / "wiki" / "concepts" / "CodeDocs.md"
        body = ("\nA fence first:\n\n```\n[[Ghost]] in code\n```\n\n"
                "then a real [[Ghost]] in prose.\n")
        page.write_text(self.FRONTMATTER + body, encoding="utf-8")
        broken = self._lint_broken_wikilinks(run_script, brain.parent)
        assert len(broken) == 1, broken
        expected_line = (self.FRONTMATTER + body).count("\n", 0,
                         (self.FRONTMATTER + body).index("real [[Ghost]]")) + 1
        assert broken[0]["line"] == expected_line, broken[0]


class TestLedgerHistorySecrets:
    """KD-15 through Git: a secret removed from the current page is still
    reported while it survives in the wiki ledger's snapshot history."""

    def _lint_json(self, run_script, project: Path) -> dict:
        result = run_script("lint_brain.py", [str(project), "--json"])
        assert result.returncode in (0, 1), result.stderr
        return json.loads(result.stdout)

    def test_secret_removed_from_page_but_retained_in_history(self, run_script, scaffolded_project: Path):
        brain = scaffolded_project
        project = brain.parent
        page = brain / "wiki" / "concepts" / "Creds.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        fm = ("---\ntitle: Creds\ntype: concept\ncreated: 2026-01-01\nupdated: 2026-01-01\n"
              "status: active\nsources: []\ntags: [t]\n---\n")
        page.write_text(fm + "# Creds\n\naws key AKIAABCDEFGHIJKLMNOP was leaked here\n",
                        encoding="utf-8")
        # Snapshot the leak, then clean the current page and snapshot again.
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        import wiki_ledger as wl
        ledger = wl.WikiLedger(project)
        ledger.snapshot("snapshot: leak")
        page.write_text(fm + "# Creds\n\nthe credential was rotated and removed\n",
                        encoding="utf-8")
        ledger.snapshot("snapshot: cleaned")
        report = self._lint_json(run_script, project)
        history = [i for i in report["issues"]
                   if i["category"] == "brain_secret" and "ledger history" in i["message"]]
        assert history, "retained secret in ledger history was not reported"
        assert any("aws access key id" in i["message"] for i in history)
        assert any(i["file"].endswith("wiki.git") for i in history)
        # Cleanup guidance is required in the message.
        assert any("rotate" in i["message"] and "purge" in i["message"] for i in history)
        # The current page is clean: no issue points at the page file.
        assert not any(i["file"].endswith("Creds.md") for i in report["issues"]
                       if i["category"] == "brain_secret")

    def test_clean_history_produces_no_history_findings(self, run_script, scaffolded_project: Path):
        brain = scaffolded_project
        project = brain.parent
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        import wiki_ledger as wl
        wl.WikiLedger(project).snapshot("snapshot: clean")
        report = self._lint_json(run_script, project)
        assert not [i for i in report["issues"] if i["category"] == "brain_secret"]

    def test_byte_budget_bounds_content_pass_and_reports_partial(self, scaffolded_project: Path,
                                                                 monkeypatch):
        """LEDGER_HISTORY_MAX_BYTES bounds the cat-file --batch request BEFORE
        any content is captured: blobs beyond the budget are skipped (nothing
        beyond the bound is reported) and the skipped content is reported as a
        partial scan. Runs in-process so the module constant can be patched."""
        import lint_brain as lb
        brain = scaffolded_project
        project = brain.parent
        page = brain / "wiki" / "concepts" / "Creds.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        fm = ("---\ntitle: Creds\ntype: concept\ncreated: 2026-01-01\nupdated: 2026-01-01\n"
              "status: active\nsources: []\ntags: [t]\n---\n")
        page.write_text(fm + "# Creds\n\naws key AKIAIOSFODNN7EXAMPLE was leaked here\n",
                        encoding="utf-8")
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        import wiki_ledger as wl
        ledger = wl.WikiLedger(project)
        ledger.snapshot("snapshot: leak")
        page.write_text(fm + "# Creds\n\nthe credential was rotated and removed\n",
                        encoding="utf-8")
        ledger.snapshot("snapshot: cleaned")
        ledger_dir = brain / "state" / "wiki.git"

        def scan() -> list[str]:
            issues: list[dict] = []
            lb._scan_ledger_history_secrets(project, brain, ledger_dir, issues)
            return [i["category"] for i in issues]

        # Full budget: the retained secret is found (in-process control).
        assert "brain_secret" in scan()
        # One-byte budget: no blob fits, nothing is scanned, and the gap is
        # reported as a partial scan instead of being silently ignored.
        monkeypatch.setattr(lb, "LEDGER_HISTORY_MAX_BYTES", 1)
        cats = scan()
        assert "brain_secret" not in cats
        assert "brain_secret_scan_partial" in cats
