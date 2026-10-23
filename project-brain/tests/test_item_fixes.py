"""Tests for ITEM 1, ITEM 2, and ITEM 3 fixes."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from datetime import datetime

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from doctor import graphify_freshness  # noqa: E402


# ITEM 1 tests: recall instructions must have guard and wing scope

def test_guard_key_phrase_in_all_files():
    """Each doc file must contain the guard phrase OR a pointer to the recall rule."""
    guard_phrase = "does not define a non-empty"
    recall_rule_pointer = "recall rule in"
    required_files = [
        "skills/brain/SKILL.md",
        "skills/brain/references/brain-lifecycle.md",
        "skills/brain/references/post-wiki-checklist.md",
        "skills/brain/references/install-and-integration.md",
        "skills/brain/references/mempalace-tools.md",
    ]
    for rel in required_files:
        path = PLUGIN_ROOT / rel
        content = path.read_text(encoding="utf-8")
        has_guard = guard_phrase in content
        has_pointer = recall_rule_pointer in content
        assert has_guard or has_pointer, \
            f"{rel} must contain guard phrase '{guard_phrase}' OR pointer '{recall_rule_pointer}'"


def test_no_unscoped_mempalace_search():
    """No doc line with '(search|query) mempalace' lacks wing/diary/recall-rule."""
    import re
    doc_files = list((PLUGIN_ROOT / "skills").rglob("*.md"))
    doc_files.extend((PLUGIN_ROOT / "scripts").rglob("*.py"))
    doc_files.extend((PLUGIN_ROOT / "hooks").rglob("*.py"))

    search_re = re.compile(r"(search|query|check)\s+mempalace", re.IGNORECASE)
    scope_indicators = ["wing", "mempalace_diary_read", "recall rule"]
    # Skip table rows (lines starting with |)
    table_row_re = re.compile(r"^\s*\|")

    violations = []
    for path in doc_files:
        if path.name == "test_item_fixes.py":
            continue
        content = path.read_text(encoding="utf-8")
        for i, line in enumerate(content.splitlines(), 1):
            # Skip table rows
            if table_row_re.match(line):
                continue
            if search_re.search(line):
                line_lower = line.lower()
                if not any(ind in line_lower for ind in scope_indicators):
                    violations.append(f"{path.relative_to(PLUGIN_ROOT)}:{i}")

    assert not violations, \
        f"Lines with '(search|query) mempalace' lack wing/diary/recall-rule:\n" + "\n".join(violations)


# ITEM 2 tests: diary agent preserved on refresh

def test_scaffold_new_brain_gets_diary_agent():
    """A new brain gets mempalace_diary_agent frontmatter."""
    import sys
    sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))
    from scaffold_brain import scaffold

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".git").mkdir()
        scaffold(root, "Test Project")
        claude_md = root / ".brain" / "CLAUDE.md"
        content = claude_md.read_text(encoding="utf-8")
        assert "mempalace_diary_agent: brain-test-project" in content, \
            "New brain must have mempalace_diary_agent frontmatter"


def test_scaffold_refresh_keeps_original_agent():
    """Refresh with --force and different title keeps original diary agent."""
    import sys
    sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))
    from scaffold_brain import scaffold

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".git").mkdir()

        scaffold(root, "Original Title")
        claude_md = root / ".brain" / "CLAUDE.md"
        first_content = claude_md.read_text(encoding="utf-8")
        assert "mempalace_diary_agent: brain-original-title" in first_content

        scaffold(root, "New Title", force=True)
        second_content = claude_md.read_text(encoding="utf-8")
        assert "mempalace_diary_agent: brain-original-title" in second_content, \
            "Refresh must keep original diary agent"
        assert "brain-new-title" not in second_content


def test_scaffold_old_brain_recovers_slug_from_sentence():
    """Refresh of older brain without frontmatter recovers slug from sentence."""
    import sys
    sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))
    from scaffold_brain import scaffold

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".git").mkdir()
        brain = root / ".brain"
        brain.mkdir()

        old_claude = brain / "CLAUDE.md"
        old_content = """---
mempalace_wing: wiki-legacy
---

# Legacy Brain

The session diary uses `mempalace_diary_write` with agent `brain-legacy-slug`.
"""
        old_claude.write_text(old_content, encoding="utf-8")

        scaffold(root, "New Title", force=True)
        new_content = old_claude.read_text(encoding="utf-8")
        assert "mempalace_diary_agent: brain-legacy-slug" in new_content, \
            "Must recover slug from old diary sentence"


def test_scaffold_empty_diary_agent_falls_back():
    """Empty mempalace_diary_agent value falls back to title-derived slug."""
    import sys
    sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))
    from scaffold_brain import scaffold

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".git").mkdir()
        brain = root / ".brain"
        brain.mkdir()

        broken_claude = brain / "CLAUDE.md"
        broken_content = """---
mempalace_wing: wiki-test
mempalace_diary_agent:
---

# Test
"""
        broken_claude.write_text(broken_content, encoding="utf-8")

        scaffold(root, "Fallback Title", force=True)
        new_content = broken_claude.read_text(encoding="utf-8")
        assert "mempalace_diary_agent: brain-fallback-title" in new_content, \
            "Empty diary agent must fall back to title-derived slug"


# ITEM 3 tests: detect deletions using manifest

def test_graphify_deletion_in_manifest_reports_stale():
    """Deleted file present in manifest reports stale."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True, capture_output=True)

        src = root / "src.py"
        src.write_text("print('hello')")
        subprocess.run(["git", "add", "src.py"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)

        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()

        graphify_out = root / "graphify-out"
        graphify_out.mkdir()
        report = graphify_out / "GRAPH_REPORT.md"
        report.write_text(f"Built from commit: `{head[:12]}`\n")

        manifest = graphify_out / "manifest.json"
        manifest.write_text(json.dumps({"src.py": {"mtime": 1000, "seen": 1}}))

        src.unlink()

        status, reason = graphify_freshness(root)
        assert status == "stale", "Deleted file in manifest must report stale"
        assert "uncommitted changes" in reason


def test_graphify_deletion_not_in_manifest_reports_fresh():
    """Deleted file not in manifest reports fresh."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True, capture_output=True)

        src = root / "src.py"
        src.write_text("print('hello')")
        subprocess.run(["git", "add", "src.py"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)

        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()

        graphify_out = root / "graphify-out"
        graphify_out.mkdir()
        report = graphify_out / "GRAPH_REPORT.md"
        report.write_text(f"Built from commit: `{head[:12]}`\n")

        manifest = graphify_out / "manifest.json"
        manifest.write_text(json.dumps({"other.py": {"mtime": 1000, "seen": 1}}))

        src.unlink()

        status, reason = graphify_freshness(root)
        assert status == "fresh", "Deleted file not in manifest must report fresh"


def test_graphify_deletion_absolute_key_reports_stale():
    """Deleted file with absolute path key in manifest reports stale."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True, capture_output=True)

        src = root / "src.py"
        src.write_text("print('hello')")
        subprocess.run(["git", "add", "src.py"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)

        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()

        graphify_out = root / "graphify-out"
        graphify_out.mkdir()
        report = graphify_out / "GRAPH_REPORT.md"
        report.write_text(f"Built from commit: `{head[:12]}`\n")

        manifest = graphify_out / "manifest.json"
        manifest.write_text(json.dumps({str(src.resolve()): {"mtime": 1000, "seen": 1}}))

        src.unlink()

        status, reason = graphify_freshness(root)
        assert status == "stale", "Deleted file with absolute key must report stale"


def test_graphify_missing_manifest_no_exception():
    """Missing manifest does not raise exception."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True, capture_output=True)

        src = root / "src.py"
        src.write_text("print('hello')")
        subprocess.run(["git", "add", "src.py"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)

        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()

        graphify_out = root / "graphify-out"
        graphify_out.mkdir()
        report = graphify_out / "GRAPH_REPORT.md"
        report.write_text(f"Built from commit: `{head[:12]}`\n")

        src.unlink()

        status, reason = graphify_freshness(root)
        assert status == "fresh", "Missing manifest must not crash and keep old behavior"


def test_graphify_corrupt_manifest_no_exception():
    """Corrupt manifest does not raise exception."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True, capture_output=True)

        src = root / "src.py"
        src.write_text("print('hello')")
        subprocess.run(["git", "add", "src.py"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)

        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()

        graphify_out = root / "graphify-out"
        graphify_out.mkdir()
        report = graphify_out / "GRAPH_REPORT.md"
        report.write_text(f"Built from commit: `{head[:12]}`\n")

        manifest = graphify_out / "manifest.json"
        manifest.write_text("not json at all")

        src.unlink()

        status, reason = graphify_freshness(root)
        assert status == "fresh", "Corrupt manifest must not crash"


def test_graphify_list_manifest_no_exception():
    """Manifest that is a JSON list does not raise exception."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True, capture_output=True)

        src = root / "src.py"
        src.write_text("print('hello')")
        subprocess.run(["git", "add", "src.py"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)

        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()

        graphify_out = root / "graphify-out"
        graphify_out.mkdir()
        report = graphify_out / "GRAPH_REPORT.md"
        report.write_text(f"Built from commit: `{head[:12]}`\n")

        manifest = graphify_out / "manifest.json"
        manifest.write_text(json.dumps(["src.py"]))

        src.unlink()

        status, reason = graphify_freshness(root)
        assert status == "fresh", "List manifest must not crash"


def test_graphify_renamed_file_old_path_in_manifest_reports_stale():
    """Renamed file whose old path is in manifest reports stale."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True, capture_output=True)

        old = root / "old.py"
        old.write_text("print('hello')")
        subprocess.run(["git", "add", "old.py"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)

        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()

        graphify_out = root / "graphify-out"
        graphify_out.mkdir()
        report = graphify_out / "GRAPH_REPORT.md"
        report.write_text(f"Built from commit: `{head[:12]}`\n")

        manifest = graphify_out / "manifest.json"
        manifest.write_text(json.dumps({"old.py": {"mtime": 1000, "seen": 1}}))

        old.rename(root / "new.py")

        status, reason = graphify_freshness(root)
        assert status == "stale", "Renamed file with old path in manifest must report stale"
