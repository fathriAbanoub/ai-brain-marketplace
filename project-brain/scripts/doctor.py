#!/usr/bin/env python3
"""Print project-brain status, availability checks, and health metrics."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def extract_frontmatter(text: str) -> dict[str, object]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    result: dict[str, object] = {}
    current_key: str | None = None
    for raw in m.group(1).splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if current_key and stripped.startswith("-"):
            result.setdefault(current_key, [])
            if isinstance(result[current_key], list):
                result[current_key].append(stripped[1:].strip().strip('"\''))
            continue
        if ":" in raw and not raw.startswith(" "):
            key, _, rest = raw.partition(":")
            key = key.strip()
            rest = rest.strip()
            current_key = None
            if not rest:
                result[key] = []
                current_key = key
            elif rest.startswith("[") and rest.endswith("]"):
                inner = rest[1:-1].strip()
                result[key] = [p.strip().strip('"\'') for p in inner.split(",") if p.strip()]
            else:
                result[key] = rest.strip('"\'')
    return result


def parse_date(raw: object) -> datetime | None:
    if not raw:
        return None
    s = str(raw).strip().replace("Z", "+00:00")
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:16] if fmt.endswith("%M") else s[:10], fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(s).replace(tzinfo=None)
    except ValueError:
        return None


# ponytail: Claude Code's settings path is UNVERIFIED from material; we check
# both known locations defensively instead of guessing one.
SETTINGS_PATHS = (
    Path.home() / ".openclaude" / "settings.json",
    Path.home() / ".claude" / "settings.json",
)


def read_enabled_plugins() -> set[str]:
    enabled: set[str] = set()
    for settings in SETTINGS_PATHS:
        try:
            data = json.loads(settings.read_text(encoding="utf-8"))
            raw = data.get("enabledPlugins", {})
            if isinstance(raw, dict):
                enabled.update(str(k) for k in raw.keys())
            elif isinstance(raw, list):
                enabled.update(str(item) for item in raw)
        except Exception:
            continue
    return enabled


GRAPH_REPORT_REL = Path("graphify-out") / "GRAPH_REPORT.md"
GRAPH_MANIFEST_REL = Path("graphify-out") / "manifest.json"
# graphify writes short hashes; 7 is git's own minimum abbreviation length.
MIN_COMMIT_HASH_LEN = 7
COMMIT_LINE_RE = re.compile(r"Built from commit:\s*`([0-9a-fA-F]+)`")
# Paths that never affect the graph: brain metadata and graphify's own output.
# .graphifyignore is deliberately NOT excluded: editing it changes which files
# graphify indexes, so a dirty .graphifyignore is real graph staleness. The
# report-mtime check below already treats "all dirty files older than the
# report" as fresh, which covers the scaffold-then-graph case.
# git pathspec exclude syntax: ":(exclude)<path>".
_DIRTY_EXCLUDES = [":(exclude).brain/", ":(exclude)graphify-out/"]
MAX_DIRTY_LINES = 3  # How many porcelain lines to include in stale reason
DIRTY_OMITTED_MARKER = "... (more paths omitted; run `git status` for the full list)"


def graphify_freshness(root: Path) -> tuple[str, str]:
    """Return ("fresh"|"stale", reason) for the graphify graph in `root`.

    After graphify runs, treats the graph as fresh until a source file changes again.
    """
    report = root / GRAPH_REPORT_REL
    if not report.exists():
        return "stale", f"{GRAPH_REPORT_REL} missing"
    match = COMMIT_LINE_RE.search(read(report))
    if not match:
        return "stale", "no 'Built from commit:' line in report"
    recorded = match.group(1)
    if len(recorded) < MIN_COMMIT_HASH_LEN:
        return "stale", f"recorded commit hash too short: {recorded!r}"

    manifest_path = root / GRAPH_MANIFEST_REL
    manifest_keys: set[str] = set()
    try:
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(manifest_data, dict):
            manifest_keys = set(manifest_data.keys())
    except Exception:
        pass

    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=5
        ).stdout.strip()
        # Dirty check: include untracked source files (they are indexed by the
        # graph), but exclude .brain/ and graphify-out/ which never affect it.
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--", *_DIRTY_EXCLUDES], cwd=root, capture_output=True, text=True, timeout=5
        ).stdout.rstrip()
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        return "stale", f"git unavailable: {exc}"
    if not head:
        return "stale", "not a git repository"
    if not head.startswith(recorded):
        return "stale", f"graph built at {recorded}, HEAD is {head[:len(recorded)]}"
    if dirty:
        dirty_lines = dirty.splitlines()
        visible_lines = dirty_lines[:MAX_DIRTY_LINES]
        omitted_count = len(dirty_lines) - len(visible_lines)

        # ponytail: compares mtime for existing files; for deletions consults
        # manifest. Remaining limit: missing manifest. Upgrade path: Graphify's
        # own change detection.
        report_mtime = report.stat().st_mtime
        any_newer_than_report = False
        for line in dirty_lines:
            # Parse git status --porcelain format: XY path [-> newpath]
            # Handle renames (->), spaces in paths, and missing files
            parts = line[3:].split(" -> ")
            path_str = parts[-1].strip()  # Use new path for renames
            path = root / path_str
            if path.exists():
                if path.stat().st_mtime > report_mtime:
                    any_newer_than_report = True
                    break
            else:
                # Deleted file: check manifest
                if manifest_keys:
                    path_posix = path.relative_to(root).as_posix()
                    path_abs = str(path.resolve())
                    if path_posix in manifest_keys or path_abs in manifest_keys:
                        any_newer_than_report = True
                        break

        if not any_newer_than_report:
            # All dirty files predate the report - graph was rebuilt after edits
            return "fresh", f"graph matches {recorded}"

        lines_str = "; ".join(visible_lines)
        if omitted_count > 0:
            lines_str += f"; {DIRTY_OMITTED_MARKER}"
        return "stale", f"uncommitted changes to source files: {lines_str}"
    return "fresh", f"graph matches {recorded}"


def graphify_version() -> tuple[bool, str]:
    try:
        proc = subprocess.run(["graphify", "--version"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=5)
    except FileNotFoundError:
        return False, "not on PATH"
    except Exception as exc:
        return False, f"version check failed: {exc}"
    line = proc.stdout.strip().splitlines()[0] if proc.stdout.strip() else "available"
    return proc.returncode == 0, line


def wiki_pages(root: Path) -> list[Path]:
    wiki = root / ".brain" / "wiki"
    if not wiki.exists():
        return []
    return [p for p in wiki.rglob("*.md") if p.name != "index.md"]


def index_text(root: Path) -> str:
    p = root / ".brain" / "wiki" / "index.md"
    return read(p).lower() if p.exists() else ""


def page_in_index(page: Path, root: Path, idx: str) -> bool:
    wiki = root / ".brain" / "wiki"
    no_ext = str(page.relative_to(wiki).with_suffix("")).lower()
    return f"[[{page.stem.lower()}]]" in idx or f"[[{no_ext}]]" in idx or no_ext in idx


def completeness(root: Path) -> tuple[int, str]:
    pages = wiki_pages(root)
    if not pages:
        return 0, "0/0 pages fully formed"
    idx = index_text(root)
    total_points = 0
    max_points = 0
    # Weights: title/heading=2, type=1, wikilink=1, indexed=2, status=1 (sources optional — new pages start empty)
    weights = [2, 1, 1, 2, 1]
    for p in pages:
        text = read(p)
        fm = extract_frontmatter(text)
        checks = [
            bool(fm.get("title") or re.search(r"^#\s+", text, re.M)),
            bool(fm.get("type")),
            bool(WIKILINK_RE.search(text)),
            page_in_index(p, root, idx),
            bool(fm.get("status")),
        ]
        page_points = sum(w for w, c in zip(weights, checks) if c)
        total_points += page_points
        max_points += sum(weights)
    score = round(total_points / max_points * 100) if max_points else 0
    full = sum(
        1 for p in pages
        if (lambda t, fm: all([
            bool(fm.get("title") or re.search(r"^#\s+", t, re.M)),
            bool(fm.get("type")),
            bool(WIKILINK_RE.search(t)),
            page_in_index(p, root, idx),
            bool(fm.get("status")),
        ]))(read(p), extract_frontmatter(read(p)))
    )
    return score, f"{full}/{len(pages)} pages fully formed (weighted score)"


def freshness(root: Path) -> tuple[int, str]:
    pages = wiki_pages(root)
    now = datetime.now()
    if not pages:
        base = 0
        fresh_pages = 0
    else:
        fresh_pages = 0
        for p in pages:
            fm = extract_frontmatter(read(p))
            dt = parse_date(fm.get("updated")) or datetime.fromtimestamp(p.stat().st_mtime)
            if (now - dt).days <= 30:
                fresh_pages += 1
        base = round(fresh_pages / len(pages) * 100)

    notes: list[str] = [f"{fresh_pages}/{len(pages)} wiki pages updated in 30 days"]
    score = base

    brief = root / ".brain" / "state" / "session-brief.md"
    brief_dt = None
    if brief.exists():
        for line in read(brief).splitlines():
            if line.lower().startswith("updated:"):
                brief_dt = parse_date(line.split(":", 1)[1].strip())
                break
    if brief_dt:
        days = (now - brief_dt).days
        if days > 7:
            score -= 15
            notes.append(f"session brief {days} days old")
    else:
        score -= 15
        notes.append("session brief date unknown")

    report = root / "graphify-out" / "GRAPH_REPORT.md"
    if report.exists():
        graph_days = (now - datetime.fromtimestamp(report.stat().st_mtime)).days
        if graph_days > 14:
            score -= 15
            notes.append(f"graphify {graph_days} days old")
    else:
        score -= 10
        notes.append("no graphify report")
    return max(0, min(100, score)), ", ".join(notes)


def coverage(root: Path) -> tuple[int, str]:
    raw = root / ".brain" / "raw"
    summaries = root / ".brain" / "wiki" / "sources"
    if not raw.exists():
        return 100, "no raw source directory"
    raw_files = [p for p in raw.rglob("*") if p.is_file() and p.name != ".gitkeep"]
    if not raw_files:
        return 100, "0/0 raw sources require summaries"
    summary_text = "\n".join(read(p) for p in summaries.rglob("*.md")) if summaries.exists() else ""
    covered = 0
    for p in raw_files:
        if rel(p, root) in summary_text or p.name in summary_text or p.stem in summary_text:
            covered += 1
    return round(covered / len(raw_files) * 100), f"{covered}/{len(raw_files)} raw sources have wiki summaries"


def memory_sync(root: Path) -> tuple[int, str]:
    log = root / ".brain" / "log"
    if not log.exists():
        return 0, "no brain logs found"
    files = sorted([p for p in log.glob("*.md") if p.is_file()], key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return 0, "no brain logs found"
    for idx, p in enumerate(files[:3], start=1):
        text = read(p).lower()
        if "mempalace" in text and any(word in text for word in ("diary", "preference", "preferences", "memory sync")):
            score = {1: 100, 2: 75, 3: 50}.get(idx, 25)
            return score, f"MemPalace last written {idx} session(s) ago"
    older = any("mempalace" in read(p).lower() for p in files[3:])
    if older:
        return 25, "MemPalace evidence exists but is older than 3 sessions"
    return 0, "no evidence of recent MemPalace diary/preference write"


def mempalace_wing_check(root: Path) -> tuple[str, str]:
    """Check the MemPalace wing name stored in .brain/CLAUDE.md.

    Does not require MCP — reads the recorded wing name and validates that it
    follows the canonical wiki-<slug> convention introduced in 0.8.0.
    """
    # ponytail: file-based only; MCP drawer count requires the agent session
    try:
        from scaffold_brain import (  # type: ignore
            WIKI_WING_PREFIX,
            resolve_wing_name,
        )
    except Exception as exc:
        return "warning", f"unable to load scaffold_brain: {exc}"

    wing, source = resolve_wing_name(root)
    if source == "derived":
        return "warning", f"wing={wing} (derived — .brain/CLAUDE.md missing mempalace_wing)"

    # Check if both files declare mempalace_wing
    root_claude = root / "CLAUDE.md"
    brain_claude = root / ".brain" / "CLAUDE.md"
    other_source = ".brain/CLAUDE.md" if source == "CLAUDE.md" else "CLAUDE.md"
    other_file = brain_claude if source == "CLAUDE.md" else root_claude
    other_declares = False
    if other_file.exists():
        text = other_file.read_text(encoding="utf-8")
        if re.search(r"mempalace_wing:\s*\S+", text):
            other_declares = True

    if not wing.startswith(WIKI_WING_PREFIX):
        msg = (
            f"wing={wing} ({source}) does not start with '{WIKI_WING_PREFIX}'; "
            f"to migrate: use mempalace_update_drawer to move drawers to the new wing name, "
            f"then update mempalace_wing in {source}"
        )
        if other_declares:
            msg += f" and change {other_source} to match"
        msg += " — re-scaffolding alone preserves the old wing name"
        return "warning", msg
    return "ok", f"wing={wing} ({source})"


def print_health(root: Path) -> None:
    c, c_note = completeness(root)
    f, f_note = freshness(root)
    cov, cov_note = coverage(root)
    mem, mem_note = memory_sync(root)
    total = round((c + f + cov + mem) / 4)
    print()
    print(f"Project Brain Health: {total}/100")
    print(f"  Completeness: {c:4}/100  ({c_note})")
    print(f"  Freshness:    {f:4}/100  ({f_note})")
    print(f"  Coverage:     {cov:4}/100  ({cov_note})")
    print(f"  Memory sync:  {mem:4}/100  ({mem_note}) [estimated from logs]")


def main(argv: list[str]) -> int:
    root = Path(argv[1]).expanduser().resolve() if len(argv) > 1 else Path.cwd()
    brain = root / ".brain"
    plugins = read_enabled_plugins()

    print(f"Project root: {root}")
    print(f"Brain directory: {brain}")
    print()

    if brain.exists():
        print("✓ .brain exists")
    else:
        print("✗ .brain does not exist")
        print('  Run: project-brain-init . "My Project"')

    for p in [brain / "wiki" / "index.md", brain / "state" / "session-brief.md"]:
        if p.exists():
            print(f"✓ {rel(p, root)} exists")
        else:
            print(f"✗ {rel(p, root)} missing")

    if any("mempalace" in p.lower() for p in plugins):
        print("✓ MemPalace plugin enabled in settings.json")
    else:
        print("⚠ mempalace not found in enabledPlugins — check ~/.openclaude/settings.json (or ~/.claude/settings.json)")

    ok, ver = graphify_version()
    if ok:
        print(f"✓ graphify CLI available ({ver})")
    else:
        print("✗ graphify not on PATH — run: uv tool install graphify && graphify install")

    if any("obsidian" in p.lower() for p in plugins):
        print("✓ Obsidian plugin enabled in settings.json")
    else:
        print("⚠ Obsidian not found in enabledPlugins (optional — needed for vault sync)")
    print("  (MCP tool availability during sessions depends on OpenClaude runtime — "
          "settings.json reflects install state only)")

    report = root / GRAPH_REPORT_REL
    if report.exists():
        print(f"✓ graphify report exists: {rel(report, root)}")
    else:
        print(f"⚠ {GRAPH_REPORT_REL} missing")
    freshness, freshness_note = graphify_freshness(root)
    if freshness == "fresh":
        print(f"✓ graphify freshness: {freshness_note}")
    else:
        print(f"⚠ graphify stale: {freshness_note} — run `/graphify .`")

    if brain.exists():
        print_health(root)
        severity, wing_note = mempalace_wing_check(root)
        glyph = {"ok": "✓", "warning": "⚠", "info": "ℹ"}.get(severity, "-")
        print(f"{glyph} MemPalace wing: {wing_note}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
