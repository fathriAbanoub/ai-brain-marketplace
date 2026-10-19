"""Test fixtures for project-brain test suite."""

import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

import pytest


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Return a temporary directory path for testing."""
    return tmp_path


@pytest.fixture
def run_script():
    """Create a subprocess runner for project-brain scripts.
    
    The plugin root is found by Path(__file__).parent.parent since this file
    is in project-brain/tests/. Scripts dir is plugin_root / "scripts".
    """
    def _run(script_name: str, args: list[str], timeout: int = 30, cwd: Path | None = None) -> subprocess.CompletedProcess:
        plugin_root = Path(__file__).parent.parent
        scripts_dir = plugin_root / "scripts"
        script_path = scripts_dir / script_name
        
        cmd = [sys.executable, str(script_path)] + args
        
        # Use scripts_dir as default cwd so script_path is resolved relative to it
        if cwd is None:
            cwd = scripts_dir
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd
        )
        return result
    
    return _run


@pytest.fixture
def scaffolded_project(run_script, tmp_project: Path) -> Path:
    """Run scaffold_brain.py on a fresh directory with a test name.
    
    Fails fixture if scaffolding fails.
    """
    brain_dir = tmp_project / "test-project"
    brain_dir.mkdir(parents=True, exist_ok=True)
    
    result = run_script("scaffold_brain.py", [str(brain_dir), "Test Project"])
    
    if result.returncode != 0:
        pytest.fail(f"Scaffolding failed: {result.stderr}")
    
    return brain_dir / ".brain"


@pytest.fixture
def make_wiki_page():
    """Write a frontmatter+body page into a brain's wiki/ directory.
    
    Args:
        brain_dir: Path to the .brain directory
        filename: Relative filename within wiki/ (e.g., "concepts/Test.md")
        frontmatter: Dict of frontmatter key-value pairs
        body: String body content after frontmatter
    """
    def _write(brain_dir: Path, filename: str, frontmatter: Dict[str, Any], body: str) -> Path:
        wiki_dir = brain_dir / "wiki"
        page_path = wiki_dir / filename
        page_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Build frontmatter block
        fm_lines = []
        for key, value in frontmatter.items():
            if isinstance(value, list):
                fm_lines.append(f"{key}: [{', '.join(str(v) for v in value)}]")
            else:
                fm_lines.append(f"{key}: {value}")
        
        fm_block = "---\n" + "\n".join(fm_lines) + "\n---\n"
        
        content = fm_block + "\n" + body
        page_path.write_text(content, encoding="utf-8")
        
        return page_path
    
    return _write
