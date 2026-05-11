"""Tests for lint_brain.py script."""

import json
import pytest
from pathlib import Path


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
        
        # Should mention orphan or missing from index
        output_lower = result.stdout.lower()
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
        
        # Should detect broken link
        assert result.returncode != 0
        output_lower = result.stdout.lower()
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
        
        # Should report missing source
        assert result.returncode != 0
        output_lower = result.stdout.lower()
        assert "source" in output_lower or "not found" in output_lower or "missing" in output_lower

    def test_lint_stale_session_brief(self, run_script, scaffolded_project: Path):
        """Stale session brief is detected."""
        brain = scaffolded_project
        project_dir = brain.parent
        
        # Modify session-brief to have old date
        brief_path = brain / "state" / "session-brief.md"
        content = brief_path.read_text(encoding="utf-8")
        # Replace updated date with old date
        old_content = content.replace("Updated:", "Updated: 2020-01-01")
        brief_path.write_text(old_content, encoding="utf-8")
        
        result = run_script("lint_brain.py", [str(project_dir)])
        
        # Should warn about stale brief (but may still exit 0 since it's a warning)
        output_lower = result.stdout.lower()
        assert "stale" in output_lower or "days" in output_lower or "session" in output_lower

    def test_lint_missing_required_paths(self, run_script, scaffolded_project: Path):
        """Exit non-zero, output 'missing' when required paths are missing."""
        brain = scaffolded_project
        project_dir = brain.parent
        
        # Remove a required file
        required_file = brain / "tasks" / "next-actions.md"
        required_file.unlink()
        
        result = run_script("lint_brain.py", [str(project_dir)])
        
        # Should fail due to missing required path
        assert result.returncode != 0
        output_lower = result.stdout.lower()
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
        
        # Should warn about deprecated field
        output_lower = result.stdout.lower()
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
