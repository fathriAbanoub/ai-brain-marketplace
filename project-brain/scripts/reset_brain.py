#!/usr/bin/env python3
"""Safely preview and reset a project-brain memory store.

The reset operation intentionally targets only the project-brain storage layers:
MemPalace drawers for the resolved project wing, the local .brain/ directory, and
local graphify-out/ output. It never deletes or modifies project source files.

MemPalace MCP tools are normally available to the agent runtime, not to arbitrary
subprocesses. This script therefore supports an explicit bridge command through
PROJECT_BRAIN_MEMPALACE_BRIDGE. The bridge is called as:

    <bridge> <tool-name> <json-arguments>

and must print a JSON result to stdout. Supported tool names are
mempalace_list_rooms, mempalace_list_drawers, and mempalace_delete_drawer.
If no bridge is configured or the bridge fails, the script reports MemPalace as
unavailable and fails closed for MemPalace deletion.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
WING_KEYS = (
    "mempalace_wing",
    "mempalace-wing",
    "mempalace wing",
    "wing",
    "project_wing",
    "project-wing",
    "project",
    "project_name",
    "project-name",
    "name",
)


class ResetError(Exception):
    """Base class for reset errors that should be shown without a traceback."""


class MempalaceUnavailable(ResetError):
    """Raised when MemPalace cannot be reached from this process."""


@dataclass(frozen=True)
class Drawer:
    drawer_id: str
    wing: str
    room: str
    preview: str = ""


def eprint(message: str) -> None:
    print(message, file=sys.stderr)


def sanitize_wing_name(raw: str) -> str:
    normalized = raw.strip().lower()
    normalized = re.sub(r"[^a-z0-9._-]+", "-", normalized)
    normalized = re.sub(r"-+", "-", normalized).strip("-._")
    return normalized or "project-brain"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def parse_scalar(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if value[0:1] in {'"', "'"} and value[-1:] == value[0]:
        return value[1:-1]
    return value


def parse_frontmatter(text: str) -> dict[str, str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}
    data: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith(" ") or line.startswith("-"):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        data[key.strip().lower()] = parse_scalar(value)
    return data


def resolve_wing_name(root: Path) -> tuple[str, str]:
    candidates = [root / ".brain" / "CLAUDE.md", root / ".brain" / "state" / "session-brief.md"]
    for path in candidates:
        if not path.exists():
            continue
        try:
            fm = parse_frontmatter(read_text(path))
        except OSError:
            continue
        for key in WING_KEYS:
            value = fm.get(key)
            if value:
                return sanitize_wing_name(value), f"frontmatter `{key}` in {path.relative_to(root)}"
    return sanitize_wing_name(root.name), "project directory name fallback"


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


def first_string(value: Any, keys: Iterable[str]) -> str:
    if isinstance(value, dict):
        for key in keys:
            found = value.get(key)
            if found is not None:
                return str(found)
    return ""


def preview_text(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, dict):
        raw = first_string(raw, ("preview", "content_preview", "content", "text", "body", "value"))
    text = re.sub(r"\s+", " ", str(raw)).strip()
    return text[:80]


class MempalaceBridge:
    """Call MemPalace MCP tools through an explicit command bridge."""

    def __init__(self, command: str | None = None) -> None:
        self.command = command or os.environ.get("PROJECT_BRAIN_MEMPALACE_BRIDGE", "").strip()

    @property
    def configured(self) -> bool:
        return bool(self.command)

    def _call(self, tool: str, args: dict[str, Any]) -> Any:
        if not self.command:
            raise MempalaceUnavailable(
                "no PROJECT_BRAIN_MEMPALACE_BRIDGE command is configured; "
                "this shell process cannot call in-session MCP tools directly"
            )
        cmd = shlex.split(self.command) + [tool, json.dumps(args, ensure_ascii=False)]
        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
        except FileNotFoundError as exc:
            raise MempalaceUnavailable(f"MemPalace bridge command not found: {cmd[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            raise MempalaceUnavailable(f"MemPalace bridge timed out while calling {tool}") from exc
        except Exception as exc:
            raise MempalaceUnavailable(f"MemPalace bridge failed while calling {tool}: {exc}") from exc
        if proc.returncode != 0:
            detail = proc.stderr.strip() or proc.stdout.strip() or f"exit code {proc.returncode}"
            raise MempalaceUnavailable(f"MemPalace bridge call {tool} failed: {detail}")
        output = proc.stdout.strip()
        if not output:
            return None
        try:
            return json.loads(output)
        except json.JSONDecodeError as exc:
            raise MempalaceUnavailable(f"MemPalace bridge returned non-JSON output for {tool}: {output[:200]}") from exc

    def list_rooms(self, wing: str) -> list[str]:
        result = self._call("mempalace_list_rooms", {"wing": wing})
        if isinstance(result, dict):
            result = result.get("rooms", result.get("result", result.get("data", [])))
        rooms: list[str] = []
        if isinstance(result, list):
            for item in result:
                if isinstance(item, str):
                    rooms.append(item)
                elif isinstance(item, dict):
                    name = first_string(item, ("room", "name", "room_name", "title", "id"))
                    if name:
                        rooms.append(name)
        return rooms

    def list_drawers(self, wing: str, room: str) -> list[Drawer]:
        result = self._call("mempalace_list_drawers", {"wing": wing, "room": room})
        if isinstance(result, dict):
            result = result.get("drawers", result.get("result", result.get("data", [])))
        drawers: list[Drawer] = []
        if not isinstance(result, list):
            return drawers
        for item in result:
            if isinstance(item, str):
                drawers.append(Drawer(drawer_id=item, wing=wing, room=room, preview=""))
                continue
            if not isinstance(item, dict):
                continue
            drawer_id = first_string(item, ("drawer_id", "id", "drawerId", "uuid"))
            if not drawer_id:
                continue
            item_wing = first_string(item, ("wing", "wing_name")) or wing
            item_room = first_string(item, ("room", "room_name")) or room
            drawers.append(Drawer(drawer_id=drawer_id, wing=item_wing, room=item_room, preview=preview_text(item)))
        return drawers

    def delete_drawer(self, drawer_id: str) -> None:
        self._call("mempalace_delete_drawer", {"drawer_id": drawer_id})


def collect_mempalace_drawers(client: MempalaceBridge, wing: str) -> tuple[list[str], list[Drawer]]:
    rooms = client.list_rooms(wing)
    drawers: list[Drawer] = []
    for room in rooms:
        drawers.extend(client.list_drawers(wing, room))
    return rooms, drawers


def print_mempalace_plan(drawers: list[Drawer], rooms: list[str]) -> None:
    print(f"MemPalace wing rooms: {len(rooms)}")
    if not drawers:
        print("MemPalace drawers: 0")
        return
    print(f"MemPalace drawers that would be deleted: {len(drawers)}")
    for drawer in drawers:
        preview = drawer.preview or "(no preview returned)"
        print(f"  - id={drawer.drawer_id} wing={drawer.wing} room={drawer.room} preview={preview}")


def maybe_prompt_local_only() -> bool:
    print("MemPalace is unavailable. Local-only deletion can still remove .brain/ and graphify-out/.")
    if not sys.stdin.isatty():
        print("Non-interactive shell detected. Re-run with --local-only --confirm to delete only local brain files.")
        return False
    try:
        answer = input("Proceed with local-only deletion instead? Type 'local-only' to continue: ").strip()
    except EOFError:
        return False
    return answer == "local-only"


@dataclass
class DryRunResult:
    wing: str
    wing_source: str
    mempalace_available: bool
    mempalace_error: str | None
    rooms: list[str]
    drawers: list[Drawer]
    brain_files: int
    brain_size: int
    graph_files: int
    graph_size: int


def dry_run(root: Path, *, mempalace_only: bool, local_only: bool) -> DryRunResult:
    wing, wing_source = resolve_wing_name(root)
    brain = root / ".brain"
    graph = root / "graphify-out"

    print("Project Brain reset preview")
    print(f"Project root: {root}")
    print(f"Resolved MemPalace wing: {wing} ({wing_source})")
    print()

    rooms: list[str] = []
    drawers: list[Drawer] = []
    mempalace_error: str | None = None
    mempalace_available = False

    if local_only:
        print("MemPalace: skipped (--local-only)")
    else:
        try:
            client = MempalaceBridge()
            rooms, drawers = collect_mempalace_drawers(client, wing)
            mempalace_available = True
            print_mempalace_plan(drawers, rooms)
        except MempalaceUnavailable as exc:
            mempalace_error = str(exc)
            print(f"⚠ MemPalace unavailable: {mempalace_error}")
            print("  No MemPalace drawers were enumerated or deleted.")
        except Exception as exc:
            mempalace_error = f"unexpected MemPalace error: {exc}"
            print(f"⚠ {mempalace_error}")
            print("  No MemPalace drawers were enumerated or deleted.")
    print()

    brain_files = brain_size = graph_files = graph_size = 0
    if mempalace_only:
        print("Local files: skipped (--mempalace-only)")
    else:
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
    print()

    drawer_summary = str(len(drawers)) if mempalace_available or local_only else "unknown"
    print(f"Summary: {drawer_summary} drawers, {brain_files} wiki files, {graph_files} graph files would be deleted")
    print("Run with --confirm to execute deletion. This is irreversible.")

    return DryRunResult(
        wing=wing,
        wing_source=wing_source,
        mempalace_available=mempalace_available,
        mempalace_error=mempalace_error,
        rooms=rooms,
        drawers=drawers,
        brain_files=brain_files,
        brain_size=brain_size,
        graph_files=graph_files,
        graph_size=graph_size,
    )


def remove_directory(path: Path, label: str) -> bool:
    if not path.exists():
        print(f"- {label} not found; skipped")
        return False
    try:
        shutil.rmtree(path)
    except Exception as exc:
        print(f"✗ Failed to remove {label}: {exc}")
        return False
    print(f"✓ {label} removed")
    return True


def confirmed_reset(root: Path, *, mempalace_only: bool, local_only: bool) -> int:
    result = dry_run(root, mempalace_only=mempalace_only, local_only=local_only)
    print()

    effective_local_only = local_only
    if not local_only and not result.mempalace_available:
        if mempalace_only:
            print("Cannot continue: --mempalace-only was requested but MemPalace is unavailable.")
            return 2
        if maybe_prompt_local_only():
            effective_local_only = True
        else:
            print("Reset aborted before deleting anything.")
            return 2

    wait_seconds = 5
    raw_wait = os.environ.get("PROJECT_BRAIN_RESET_WAIT_SECONDS")
    if raw_wait is not None:
        try:
            wait_seconds = max(0, int(raw_wait))
        except ValueError:
            wait_seconds = 5
    print("Proceeding with deletion in 5 seconds. Press Ctrl+C to abort.")
    try:
        time.sleep(wait_seconds)
    except KeyboardInterrupt:
        print("\nReset aborted. Nothing else was deleted.")
        return 130

    deleted_drawers = 0
    failed_drawers: list[str] = []
    if effective_local_only:
        print("- MemPalace skipped (--local-only)")
    else:
        client = MempalaceBridge()
        for drawer in result.drawers:
            try:
                client.delete_drawer(drawer.drawer_id)
                deleted_drawers += 1
            except Exception as exc:
                failed_drawers.append(drawer.drawer_id)
                print(f"✗ Failed to delete drawer {drawer.drawer_id}: {exc}")
        print(f"✓ MemPalace wing cleared ({deleted_drawers} drawers deleted)")
        if failed_drawers:
            print(f"⚠ {len(failed_drawers)} drawer deletion(s) failed: {', '.join(failed_drawers)}")

    if mempalace_only:
        print("- .brain/ skipped (--mempalace-only)")
        print("- graphify-out/ skipped (--mempalace-only)")
    else:
        remove_directory(root / ".brain", ".brain/")
        remove_directory(root / "graphify-out", "graphify-out/")

    if effective_local_only:
        print("Local brain reset complete. MemPalace was left intact. Run project-brain-init to start fresh.")
    elif failed_drawers:
        print("Brain reset finished with MemPalace deletion failures. The wing may still exist until failed drawers are removed.")
    else:
        print("Brain reset complete. The project wing no longer exists in MemPalace. Run project-brain-init to start fresh.")
    if failed_drawers:
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="project-brain-reset",
        description="Safely delete a project brain.",
        add_help=True,
    )
    parser.add_argument("path", nargs="?", default=".", help="Project root directory (default: current directory)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--mempalace-only", action="store_true", help="Delete only the MemPalace wing, keep local files")
    mode.add_argument("--local-only", action="store_true", help="Delete only .brain/ and graphify-out/, keep MemPalace")
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
            return confirmed_reset(root, mempalace_only=args.mempalace_only, local_only=args.local_only)
        dry_run(root, mempalace_only=args.mempalace_only, local_only=args.local_only)
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
