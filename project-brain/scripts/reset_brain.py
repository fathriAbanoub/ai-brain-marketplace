#!/usr/bin/env python3
"""Reset the local layers of a project brain.

This script deletes only local artifacts: the .brain/ directory, graphify-out/,
the "# Project Brain" block injected into root CLAUDE.md, and
CLAUDE.project-brain.snippet.md. It never touches project source files.

MemPalace drawers are NOT handled here. MemPalace is only reachable through
MCP tools, which live in the agent session, not in this subprocess. The
/project-brain:reset skill deletes those drawers directly via
mempalace_list_rooms -> mempalace_list_drawers -> mempalace_delete_drawer
before calling this script.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path


class ResetError(Exception):
    """Base class for reset errors that should be shown without a traceback."""


def eprint(message: str) -> None:
    print(message, file=sys.stderr)


def directory_stats(path: Path) -> tuple[int, int]:
    if not path.exists():
        return 0, 0
    files = 0
    size = 0
    for item in path.rglob("*"):
        try:
            if item.is_file() or item.is_symlink():
                files += 1
                size += item.lstat().st_size
        except OSError:
            continue
    return files, size


def format_size(num_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(num_bytes)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{num_bytes} B"


@dataclass
class DryRunResult:
    brain_files: int
    brain_size: int
    graph_files: int
    graph_size: int
    claude_md_block: bool
    snippet: bool


def dry_run(root: Path) -> DryRunResult:
    brain = root / ".brain"
    graph = root / "graphify-out"
    claude_md = root / "CLAUDE.md"
    snippet = root / "CLAUDE.project-brain.snippet.md"

    print("Project Brain reset preview")
    print(f"Project root: {root}")
    print()

    brain_files, brain_size = directory_stats(brain)
    graph_files, graph_size = directory_stats(graph)
    if brain.exists():
        print(f".brain/: {brain_files} files, {format_size(brain_size)}")
    else:
        print(".brain/: not found (skipped)")
    if graph.exists():
        print(f"graphify-out/: {graph_files} files, {format_size(graph_size)}")
    else:
        print("graphify-out/: not found (skipped)")

    has_block = False
    if claude_md.exists():
        try:
            has_block = "<!-- project-brain:begin -->" in claude_md.read_text(encoding="utf-8")
        except OSError:
            has_block = False
    print(f"CLAUDE.md '# Project Brain' block: {'present' if has_block else 'not found'}")
    print(f"CLAUDE.project-brain.snippet.md: {'present' if snippet.exists() else 'not found'}")
    print()
    print("MemPalace: handled by the /project-brain:reset skill via MCP tools, not by this script.")
    print()
    print(
        f"Summary: {brain_files} brain files, {graph_files} graph files would be deleted; "
        f"CLAUDE.md block {'present' if has_block else 'absent'}, snippet {'present' if snippet.exists() else 'absent'}"
    )

    return DryRunResult(
        brain_files=brain_files,
        brain_size=brain_size,
        graph_files=graph_files,
        graph_size=graph_size,
        claude_md_block=has_block,
        snippet=snippet.exists(),
    )


def strip_brain_block_from_claude_md(root: Path) -> None:
    """Remove the Project Brain block injected by scaffold_brain.py from root CLAUDE.md."""
    claude_md = root / "CLAUDE.md"
    if not claude_md.exists():
        return
    text = claude_md.read_text(encoding="utf-8")
    begin = "<!-- project-brain:begin -->"
    end = "<!-- project-brain:end -->"
    if begin not in text:
        return
    lines = text.splitlines(keepends=True)
    start_idx = None
    end_idx = None
    for i, line in enumerate(lines):
        if line.strip() == begin and start_idx is None:
            start_idx = i
        elif line.strip() == end and start_idx is not None:
            end_idx = i
            break
    if start_idx is None:
        return
    if end_idx is not None:
        result = "".join(lines[:start_idx] + lines[end_idx + 1:]).rstrip("\n")
    else:
        result = "".join(lines[:start_idx]).rstrip("\n")
    if result:
        result += "\n"
    claude_md.write_text(result, encoding="utf-8")
    print("✓ Project Brain block removed from CLAUDE.md")


def remove_project_brain_snippet(root: Path) -> None:
    snippet = root / "CLAUDE.project-brain.snippet.md"
    if snippet.exists():
        snippet.unlink()
        print("✓ CLAUDE.project-brain.snippet.md removed")


def remove_directory(path: Path, label: str) -> bool:
    if not path.exists():
        print(f"- {label} not found; skipped")
        return True
    try:
        shutil.rmtree(path)
    except Exception as exc:
        print(f"✗ Failed to remove {label}: {exc}")
        return False
    print(f"✓ {label} removed")
    return True


def confirmed_reset(root: Path) -> int:
    dry_run(root)
    print()

    wait_seconds = 5
    raw_wait = os.environ.get("PROJECT_BRAIN_RESET_WAIT_SECONDS")
    if raw_wait is not None:
        try:
            wait_seconds = max(0, int(raw_wait))
        except ValueError:
            wait_seconds = 5
    if wait_seconds:
        print(f"Proceeding with deletion in {wait_seconds} seconds. Press Ctrl+C to abort.")
        try:
            time.sleep(wait_seconds)
        except KeyboardInterrupt:
            print("\nReset aborted. Nothing else was deleted.")
            return 130

    failed: list[str] = []
    if not remove_directory(root / ".brain", ".brain/"):
        failed.append(str(root / ".brain"))
    if not remove_directory(root / "graphify-out", "graphify-out/"):
        failed.append(str(root / "graphify-out"))
    strip_brain_block_from_claude_md(root)
    remove_project_brain_snippet(root)

    if failed:
        print(f"✗ Reset incomplete. The following paths could not be removed:")
        for p in failed:
            print(f"  {p}")
        return 1

    print("Local brain reset complete. Run /project-brain:brain to initialize a fresh brain.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="project-brain-reset",
        description="Delete the local layers of a project brain (.brain/, graphify-out/, CLAUDE.md block).",
        add_help=True,
    )
    parser.add_argument("path", nargs="?", default=".", help="Project root directory (default: current directory)")
    parser.add_argument("--dry-run", action="store_true", help="Preview what would be deleted (default behavior)")
    parser.add_argument("--confirm", action="store_true", help="Execute deletion (irreversible)")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        root = Path(args.path).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise ResetError(f"project root does not exist or is not a directory: {root}")
        if args.confirm:
            return confirmed_reset(root)
        dry_run(root)
        print("Run with --confirm to execute deletion. This is irreversible.")
        return 0
    except ResetError as exc:
        eprint(f"error: {exc}")
        return 2
    except KeyboardInterrupt:
        eprint("\nReset aborted.")
        return 130
    except Exception as exc:
        eprint(f"error: unexpected failure: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())