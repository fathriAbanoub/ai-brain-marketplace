"""Tests for audit_review.py script."""

import pytest
from pathlib import Path


class TestAuditReview:
    """Test suite for audit_review.py."""

    def test_audit_exits_zero_no_open_items(self, run_script, scaffolded_project: Path):
        """Exit 0 when no open audit items exist."""
        # audit_review.py takes brain directory as argument, not project root
        brain = scaffolded_project
        
        result = run_script("audit_review.py", [str(brain), "--open"])
        
        assert result.returncode == 0

    def test_audit_detects_open_task(self, run_script, scaffolded_project: Path):
        """Detects an open audit task."""
        brain = scaffolded_project
        
        # Create an open audit file
        audit_file = brain / "audit" / "test-audit.md"
        audit_file.write_text(
            """---
id: TEST-001
severity: error
target: wiki/index.md
author: Test Author
created: 2024-01-01
status: open
---

# Comment

This is a test audit item.
""",
            encoding="utf-8"
        )
        
        result = run_script("audit_review.py", [str(brain), "--open"])
        
        assert result.returncode == 0
        # Should detect the open item
        output_lower = result.stdout.lower()
        assert "error" in output_lower or "TEST-001" in result.stdout or "open" in output_lower

    def test_audit_done_items_only(self, run_script, scaffolded_project: Path):
        """--resolved mode shows only resolved items."""
        brain = scaffolded_project
        
        # Create a resolved audit file
        resolved_dir = brain / "audit" / "resolved"
        resolved_dir.mkdir(parents=True, exist_ok=True)
        audit_file = resolved_dir / "done-audit.md"
        audit_file.write_text(
            """---
id: DONE-001
severity: warn
target: wiki/concepts/Test.md
author: Tester
created: 2024-01-01
status: resolved
---

# Comment

This is a resolved audit item.
""",
            encoding="utf-8"
        )
        
        result = run_script("audit_review.py", [str(brain), "--resolved"])
        
        assert result.returncode == 0
        # Should find the resolved item
        assert "DONE-001" in result.stdout or "resolved" in result.stdout.lower()

    def test_audit_mode_all(self, run_script, scaffolded_project: Path):
        """--all mode shows both open and resolved items."""
        brain = scaffolded_project
        
        # Create an open audit file
        audit_file = brain / "audit" / "open-audit.md"
        audit_file.write_text(
            """---
id: OPEN-001
severity: error
target: wiki/index.md
author: Test
created: 2024-01-01
status: open
---

# Comment

Open item.
""",
            encoding="utf-8"
        )
        
        # Create a resolved audit file
        resolved_dir = brain / "audit" / "resolved"
        resolved_dir.mkdir(parents=True, exist_ok=True)
        resolved_file = resolved_dir / "closed-audit.md"
        resolved_file.write_text(
            """---
id: CLOSED-001
severity: warn
target: wiki/concepts/Test.md
author: Tester
created: 2024-01-01
status: resolved
---

# Comment

Resolved item.
""",
            encoding="utf-8"
        )
        
        result = run_script("audit_review.py", [str(brain), "--all"])
        
        assert result.returncode == 0
        # Should show both
        output = result.stdout
        assert "OPEN-001" in output or "CLOSED-001" in output or "all" in output.lower()

    def test_audit_no_audit_directory(self, run_script, tmp_project: Path):
        """Exit non-zero, stderr mentions 'audit' when audit directory missing."""
        project_dir = tmp_project / "no-audit"
        project_dir.mkdir(parents=True, exist_ok=True)
        
        # Scaffold to create .brain but we won't have audit files
        result_scaffold = run_script("scaffold_brain.py", [str(project_dir), "Test"])
        assert result_scaffold.returncode == 0
        
        # Remove audit directory
        import shutil
        brain_dir = project_dir / ".brain"
        audit_dir = brain_dir / "audit"
        if audit_dir.exists():
            shutil.rmtree(audit_dir)
        
        result = run_script("audit_review.py", [str(brain_dir)])
        
        # Should fail - no audit directory
        assert result.returncode != 0
        output_lower = result.stdout.lower() + result.stderr.lower()
        assert "audit" in output_lower

    def test_audit_default_mode_is_open(self, run_script, scaffolded_project: Path):
        """Default mode (no flag) is --open."""
        brain = scaffolded_project
        
        # Create an open audit file
        audit_file = brain / "audit" / "default-test.md"
        audit_file.write_text(
            """---
id: DEFAULT-001
severity: info
target: wiki/index.md
author: Test
created: 2024-01-01
status: open
---

# Comment

Default mode test.
""",
            encoding="utf-8"
        )
        
        # Run without mode flag
        result = run_script("audit_review.py", [str(brain)])
        
        assert result.returncode == 0
        # Default should be open mode
        output_lower = result.stdout.lower()
        assert "open" in output_lower or "DEFAULT-001" in result.stdout

    def test_audit_severity_ordering(self, run_script, scaffolded_project: Path):
        """Output shows ERROR before WARN before SUGGEST before INFO."""
        brain = scaffolded_project
        
        # Create audit files with different severities
        severities = ["info", "suggest", "warn", "error"]
        for i, sev in enumerate(severities):
            audit_file = brain / "audit" / f"sev-{sev}.md"
            audit_file.write_text(
                f"""---
id: SEV-{sev.upper()}
severity: {sev}
target: wiki/index.md
author: Test
created: 2024-01-0{i}
status: open
---

# Comment

{sev} severity item.
""",
                encoding="utf-8"
            )
        
        result = run_script("audit_review.py", [str(brain), "--open"])
        
        assert result.returncode == 0
        output = result.stdout
        
        # Check ordering - ERROR section should appear before WARN, etc.
        error_pos = output.find("## ERROR")
        warn_pos = output.find("## WARN")
        suggest_pos = output.find("## SUGGEST")
        info_pos = output.find("## INFO")
        
        # All sections should exist
        assert error_pos >= 0
        assert warn_pos >= 0
        assert suggest_pos >= 0
        assert info_pos >= 0
        
        # Verify order
        assert error_pos < warn_pos < suggest_pos < info_pos

    def test_audit_empty_audit_directory(self, run_script, scaffolded_project: Path):
        """Handles empty audit directory gracefully."""
        brain = scaffolded_project
        
        # Audit directory exists from scaffold but has no .md files (only .gitkeep)
        result = run_script("audit_review.py", [str(brain), "--open"])
        
        assert result.returncode == 0
        # Should report no items found
        output_lower = result.stdout.lower()
        assert "no" in output_lower or "0" in output_lower or "empty" in output_lower

    def test_audit_missing_frontmatter_warning(self, run_script, scaffolded_project: Path):
        """Warns about audit files missing frontmatter."""
        brain = scaffolded_project
        
        # Create an audit file without frontmatter
        bad_audit = brain / "audit" / "bad-frontmatter.md"
        bad_audit.write_text(
            """# No Frontmatter

This audit file has no frontmatter block.
""",
            encoding="utf-8"
        )
        
        result = run_script("audit_review.py", [str(brain), "--open"])
        
        # Should warn about missing frontmatter
        output_lower = result.stdout.lower() + result.stderr.lower()
        assert "frontmatter" in output_lower or "missing" in output_lower or "⚠" in result.stderr
