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


def read_enabled_plugins() -> set[str]:
    settings = Path.home() / ".openclaude" / "settings.json"
    try:
        data = json.loads(settings.read_text(encoding="utf-8"))
        enabled = data.get("enabledPlugins", {})
        if isinstance(enabled, dict):
            return {str(k) for k in enabled.keys()}
        if isinstance(enabled, list):
            return {str(item) for item in enabled}
    except Exception:
        pass
    return set()


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
    full = 0
    for p in pages:
        text = read(p)
        fm = extract_frontmatter(text)
        sources = fm.get("sources", [])
        has_sources = isinstance(sources, list) and len([s for s in sources if str(s).strip()]) > 0
        checks = [
            bool(fm.get("title") or re.search(r"^#\s+", text, re.M)),
            bool(fm.get("type")),
            bool(fm.get("status")),
            has_sources,
            bool(WIKILINK_RE.search(text)),
            page_in_index(p, root, idx),
        ]
        if all(checks):
            full += 1
    score = round(full / len(pages) * 100)
    return score, f"{full}/{len(pages)} pages fully formed"


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
        print("⚠ mempalace not found in enabledPlugins — check ~/.openclaude/settings.json")

    ok, ver = graphify_version()
    if ok:
        print(f"✓ graphify CLI available ({ver})")
    else:
        print("✗ graphify not on PATH — run: uv tool install graphifyy && graphify install")

    if any("obsidian" in p.lower() for p in plugins):
        print("✓ Obsidian plugin enabled in settings.json")
    else:
        print("⚠ Obsidian not found in enabledPlugins (optional — needed for vault sync)")
    print("  (MCP tool availability during sessions depends on OpenClaude runtime — "
          "settings.json reflects install state only)")

    report = root / "graphify-out" / "GRAPH_REPORT.md"
    if report.exists():
        print(f"✓ graphify report exists: {rel(report, root)}")
    else:
        print("⚠ graphify-out/GRAPH_REPORT.md missing")

    if brain.exists():
        print_health(root)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
