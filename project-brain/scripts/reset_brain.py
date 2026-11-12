#!/usr/bin/env python3
"""Reset the local layers of a project brain.

This script deletes only local artifacts: the .brain/ directory, graphify-out/,
the "# Project Brain" block injected into root CLAUDE.md, and
CLAUDE.project-brain.snippet.md. It never touches project source files.

MemPalace drawers are NOT handled here. MemPalace is only reachable through
MCP tools, which live in the agent session, not in this subprocess. The
/project-brain:reset skill deletes those drawers itself via
mempalace_list_drawers (paginated enumeration) -> mempalace_delete_drawers
(bulk batches of at most 500 IDs) -> per-wing verification, then cleans up
in-scope tunnels and hallways, before calling this script. The single-drawer
mempalace_delete_drawer tool is prohibited in that workflow. The canonical
algorithm lives in scripts/mempalace_reset.py.

This script also carries --classify-wings, a read-only helper that runs the
wing classifier (scripts/mempalace_reset.py::classify_wings) on a recorded
mempalace_list_wings result and prints the table plus the A/B/C outcome as
evidence for the user; every reset target still needs the user's confirmation.
"""

from __future__ import annotations

import argparse
import json
import os
import re
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


RESET_TRANSCRIPT_REL = ".brain/audit/reset-transcript.jsonl"
ALLOWED_TRANSCRIPT_TOOLS = {
    "mempalace_list_wings", "mempalace_get_taxonomy", "mempalace_list_rooms",
    "mempalace_list_drawers", "mempalace_delete_drawers",
}
PROHIBITED_TRANSCRIPT_TOOLS = {"mempalace_delete_drawer"}


def verify_reset_transcript(root: Path, wing: str) -> int:
    """S-a (D-3): validate a recorded MCP reset transcript against the hard
    contracts of mempalace_reset — the canonical, tested algorithm.

    Contracts checked: no single-drawer deletes; batch size 1..MAX_BATCH;
    page limit <= PAGE_LIMIT; every enumerated drawer id recorded as deleted;
    wing-cleared evidence (list_wings absence or taxonomy drawer_count 0)
    after the last delete; a mempalace_get_taxonomy count cross-check before
    the first delete whose count matches the pre-delete enumeration
    (reset skill Step 3a.4). The transcript is shared across confirmed wings,
    so records naming a different wing (exact-name comparison) are skipped,
    not violations. Exit 0 only when the transcript satisfies every contract.
    """
    import mempalace_reset as mr

    path = root / RESET_TRANSCRIPT_REL
    if not path.is_file():
        eprint(f"error: no reset transcript at {RESET_TRANSCRIPT_REL} — the reset skill "
               "must record every MemPalace call there before verification")
        return 2
    records: list[dict] = []
    for ln, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError as exc:
            eprint(f"error: corrupt reset transcript at line {ln}: {exc}")
            return 2
        if not isinstance(rec, dict):
            eprint(f"error: corrupt reset transcript at line {ln}: not a JSON object")
            return 2
        records.append(rec)

    target = mr.normalize_wing_for_compare(wing)
    violations: list[str] = []
    enumerated: set[str] = set()
    deleted: set[str] = set()
    wing_absent: bool | None = None
    drawer_count: int | None = None
    cleared_evidence_after_delete = False
    # Step 3a.4 cross-check state: the enumeration must be compared against a
    # pre-deletion mempalace_get_taxonomy count before anything is deleted.
    delete_started = False
    enumerated_pre_delete: set[str] = set()
    saw_taxonomy_pre_delete = False
    taxonomy_count_pre_delete: int | None = None
    for i, rec in enumerate(records, start=1):
        tool = str(rec.get("tool", ""))
        if tool in PROHIBITED_TRANSCRIPT_TOOLS:
            violations.append(f"line {i}: single-drawer delete ({tool}) is prohibited — "
                              "bulk mempalace_delete_drawers only")
            continue
        if tool not in ALLOWED_TRANSCRIPT_TOOLS:
            violations.append(f"line {i}: unknown or unrecorded tool {tool!r}")
            continue
        rec_wing = rec.get("wing")
        if rec_wing is not None and str(rec_wing) != wing:
            # Another confirmed wing's record in the shared transcript. Exact
            # name comparison: a normalized twin is a distinct wing and its
            # records must never count for (or against) this one.
            continue
        if tool == "mempalace_delete_drawers":
            if not delete_started:
                delete_started = True
                if not saw_taxonomy_pre_delete:
                    violations.append(
                        f"line {i}: no mempalace_get_taxonomy record before the first delete — "
                        "cross-check the enumeration against the taxonomy drawer_count "
                        "before any deletion (reset skill Step 3a.4)")
                elif taxonomy_count_pre_delete != len(enumerated_pre_delete):
                    violations.append(
                        f"line {i}: enumerated {len(enumerated_pre_delete)} drawer(s) before the "
                        f"first delete but the pre-deletion taxonomy reported "
                        f"{taxonomy_count_pre_delete} — counts disagree; the skill requires "
                        "STOP, delete nothing, re-run the enumeration")
            ids = rec.get("ids")
            size = len(ids) if isinstance(ids, list) else -1
            if not (1 <= size <= mr.MAX_BATCH):
                violations.append(f"line {i}: batch size {size} outside 1..{mr.MAX_BATCH}")
            del_ids = rec.get("deleted_ids")
            if isinstance(del_ids, list):
                deleted.update(str(x) for x in del_ids)
            else:
                violations.append(f"line {i}: delete record missing deleted_ids")
            wing_absent, drawer_count = None, None  # deletion invalidates old evidence
            cleared_evidence_after_delete = False
        elif tool == "mempalace_list_drawers":
            limit = rec.get("limit")
            if isinstance(limit, int) and limit > mr.PAGE_LIMIT:
                violations.append(f"line {i}: page limit {limit} exceeds {mr.PAGE_LIMIT}")
            ret = rec.get("returned_ids")
            if isinstance(ret, list):
                page_ids = {str(x) for x in ret}
                enumerated.update(page_ids)
                if not delete_started:
                    enumerated_pre_delete.update(page_ids)
        elif tool == "mempalace_list_wings":
            wings = rec.get("wings")
            if isinstance(wings, list):
                names = [str(w.get("wing") or w.get("name") or w) if isinstance(w, dict) else str(w)
                         for w in wings]
                wing_absent = all(mr.normalize_wing_for_compare(n) != target for n in names)
                cleared_evidence_after_delete = True
        elif tool == "mempalace_get_taxonomy":
            count = rec.get("drawer_count")
            if isinstance(count, int):
                drawer_count = count
                cleared_evidence_after_delete = True
                if not delete_started:
                    saw_taxonomy_pre_delete = True
                    taxonomy_count_pre_delete = count

    not_deleted = enumerated - deleted
    if not_deleted:
        violations.append(f"{len(not_deleted)} enumerated drawer id(s) not recorded as deleted: "
                          f"{sorted(not_deleted)[:5]}")
    if not cleared_evidence_after_delete:
        violations.append("no wing-cleared evidence after the last delete — need a final "
                          "mempalace_list_wings or mempalace_get_taxonomy record")
    elif not ((wing_absent is True) or (drawer_count == 0)):
        violations.append(f"wing not cleared at end (absent={wing_absent}, "
                          f"drawer_count={drawer_count})")

    if violations:
        for v in violations:
            eprint(f"transcript violation: {v}")
        eprint(f"reset transcript: {len(violations)} contract violation(s) — reset NOT verified")
        return 1
    print(f"reset transcript verified: {len(records)} call(s), {len(deleted)} drawer(s) "
          f"deleted, wing {wing!r} cleared")
    return 0


# --- wing classification (--classify-wings: read-only evidence) --------------

# Frontmatter keys in .brain/CLAUDE.md that record the brain's identity.
IDENTITY_KEY_RE = re.compile(r"^(mempalace_wing|mempalace_diary_agent):\s*(.+?)\s*$")


def read_brain_identity(root: Path) -> tuple[str | None, str | None]:
    """Read mempalace_wing / mempalace_diary_agent from <root>/.brain/CLAUDE.md.

    An absent or unreadable file, or a missing key, means "not recorded"
    (None) — the classifier then derives the orphan-scan slug from the
    project directory name instead.
    """
    path = root / ".brain" / "CLAUDE.md"
    if not path.is_file():
        return None, None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None, None
    wing: str | None = None
    agent: str | None = None
    for line in text.splitlines():
        match = IDENTITY_KEY_RE.match(line.strip())
        if not match:
            continue
        value = match.group(2).strip("'\"") or None
        if match.group(1) == "mempalace_wing":
            wing = wing or value
        else:
            agent = agent or value
    return wing, agent


def parse_wings_payload(text: str) -> dict[str, int]:
    """Parse a mempalace_list_wings result: {"wings": {name: count}} or a
    bare {name: count} map. Anything else is a bad input (ResetError)."""
    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise ResetError(f"--classify-wings: input is not valid JSON: {exc}")
    if not isinstance(payload, dict):
        raise ResetError(
            '--classify-wings: expected the mempalace_list_wings result (a "wings" '
            f"map of name to drawer count) or a bare such map, got {type(payload).__name__}"
        )
    wings = payload.get("wings")
    if not isinstance(wings, dict):
        wings = payload  # bare map form
    for name, count in wings.items():
        if not isinstance(name, str) or not isinstance(count, int) or isinstance(count, bool):
            raise ResetError(
                f"--classify-wings: wing counts must map name -> integer, found {name!r}: {count!r}"
            )
    return wings


def _print_classify_report(
    classification,  # mempalace_reset.WingClassification
    recorded_wing: str | None,
    recorded_agent: str | None,
    wings: dict[str, int],
) -> None:
    """Print the evidence-only report. No deletion verbs, by contract: this
    output is evidence for the user and never an instruction to act."""
    import mempalace_reset as mr

    print(f"Received {len(wings)} wing(s), {sum(wings.values())} drawer(s).")
    print(f"Recorded wiki wing: {recorded_wing or '(none recorded)'}")
    print(f"Recorded diary agent: {recorded_agent or '(none recorded)'}")
    print(f"Orphan-scan slug: {classification.orphan_slug or '(none)'}")
    print()
    rows = classification.rows
    if not rows:
        print("(no wings in the input)")
    else:
        headers = ("wing", "drawers", "normalized form", "class", "flags")
        table = [
            (r.wing, str(r.drawers), r.normalized, r.wing_class, " ".join(r.flags))
            for r in rows
        ]
        widths = [max(len(h), max(len(row[i]) for row in table)) for i, h in enumerate(headers)]
        for cells in (headers, *table):
            print("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells)).rstrip())
    collisions = sorted({r.wing for r in rows if mr.FLAG_COLLISION in r.flags})
    if collisions:
        print()
        print(
            f"Collision: {', '.join(collisions)} share a normalized form — ask which "
            "exact wing(s) belong to this brain; never collapse them."
        )
    print()
    print(f"OUTCOME: {classification.outcome} — {mr.OUTCOME_MEANINGS[classification.outcome]}")
    print(
        "Evidence only: the palace was not modified; every reset target still "
        "needs the user's confirmation."
    )


def classify_wings_command(root: Path, source: str) -> int:
    """Run the wing classifier on a mempalace_list_wings result (a JSON file
    path, or - for standard input) and print the report. Read-only."""
    import mempalace_reset as mr

    if source == "-":
        text = sys.stdin.read()
    else:
        try:
            text = Path(source).expanduser().read_text(encoding="utf-8")
        except OSError as exc:
            raise ResetError(f"--classify-wings: cannot read {source!r}: {exc}")
    wings = parse_wings_payload(text)
    recorded_wing, recorded_agent = read_brain_identity(root)
    classification = mr.classify_wings(
        wings,
        recorded_wiki_wing=recorded_wing,
        recorded_diary_agent=recorded_agent,
        project_dir_name=root.name,
    )
    _print_classify_report(classification, recorded_wing, recorded_agent, wings)
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
    parser.add_argument("--verify-reset-transcript", metavar="WING", dest="verify_transcript",
                        help="verify .brain/audit/reset-transcript.jsonl against mempalace_reset's "
                             "hard contracts for WING (exit 0 = reset verified)")
    parser.add_argument("--classify-wings", metavar="FILE", dest="classify_wings",
                        help="classify a mempalace_list_wings result (JSON file, or - for "
                             "standard input) into wing classes and an A/B/C outcome; "
                             "evidence only — every target still needs the user's confirmation")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        root = Path(args.path).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise ResetError(f"project root does not exist or is not a directory: {root}")
        if args.verify_transcript:
            return verify_reset_transcript(root, args.verify_transcript)
        if args.classify_wings is not None:
            return classify_wings_command(root, args.classify_wings)
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