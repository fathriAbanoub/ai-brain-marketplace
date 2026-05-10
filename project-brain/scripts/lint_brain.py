#!/usr/bin/env python3
"""Health-check a project brain.

Usage:
    lint_brain.py <project-root> [--json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, date, timezone
from pathlib import Path

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
SEVERITIES = ("error", "warn", "suggest", "info")


def rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def add(issues: list[dict], severity: str, category: str, file: Path | None, root: Path, message: str, line: int | None = None) -> None:
    item = {
        "severity": severity,
        "category": category,
        "file": rel(file, root) if file else None,
        "line": line,
        "message": message,
    }
    issues.append(item)


def extract_frontmatter(text: str) -> dict[str, object]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    body = m.group(1)
    result: dict[str, object] = {}
    current_key: str | None = None
    for raw in body.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if current_key and stripped.startswith("-"):
            val = stripped[1:].strip().strip('"\'')
            result.setdefault(current_key, [])
            if isinstance(result[current_key], list):
                result[current_key].append(val)
            continue
        if re.match(r"^[A-Za-z0-9_-]+:\s*", line):
            key, _, rest = line.partition(":")
            key = key.strip()
            rest = rest.strip()
            current_key = None
            if rest == "":
                result[key] = []
                current_key = key
            elif rest.startswith("[") and rest.endswith("]"):
                inner = rest[1:-1].strip()
                result[key] = [p.strip().strip('"\'') for p in inner.split(",") if p.strip()]
            else:
                result[key] = rest.strip('"\'')
    return result


def collect_wiki_keys(wiki: Path) -> tuple[set[str], list[Path]]:
    keys: set[str] = set()
    pages = list(wiki.rglob("*.md")) if wiki.exists() else []
    for p in pages:
        rel_no_ext = str(p.relative_to(wiki).with_suffix(""))
        keys.add(rel_no_ext.lower())
        keys.add(p.stem.lower())
    return keys, pages


def normalize_link(target: str) -> str:
    t = target.strip().replace("\\", "/")
    if t.lower().endswith(".md"):
        t = t[:-3]
    return t.lower().strip("/")


def resolve_wikilink(target: str, keys: set[str]) -> bool:
    needle = normalize_link(target)
    if not needle or needle.startswith("#"):
        return True
    return any(key == needle or key.endswith(needle) for key in keys)


def line_for(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def check_required(root: Path, brain: Path, issues: list[dict]) -> None:
    required = [
        brain / "CLAUDE.md",
        brain / "wiki" / "index.md",
        brain / "state" / "session-brief.md",
        brain / "tasks" / "next-actions.md",
    ]
    for p in required:
        if not p.exists():
            add(issues, "error", "missing_required_path", p, root, f"missing required path: {rel(p, root)}")


def check_wikilinks(root: Path, brain: Path, issues: list[dict]) -> None:
    wiki = brain / "wiki"
    keys, pages = collect_wiki_keys(wiki)
    for p in pages:
        text = read(p)
        for m in WIKILINK_RE.finditer(text):
            target = m.group(1).strip()
            if not resolve_wikilink(target, keys):
                add(
                    issues,
                    "error",
                    "broken_wikilink",
                    p,
                    root,
                    f"[[{target}]] — target not found in wiki",
                    line_for(text, m.start()),
                )


def source_path_exists(src: str, root: Path, file: Path) -> bool:
    src = src.strip().strip('"\'')
    if not src:
        return True
    candidate = Path(src).expanduser()
    candidates = [candidate] if candidate.is_absolute() else [root / candidate, file.parent / candidate]
    return any(c.exists() for c in candidates)


def check_sources(root: Path, brain: Path, issues: list[dict]) -> None:
    wiki = brain / "wiki"
    for p in wiki.rglob("*.md") if wiki.exists() else []:
        fm = extract_frontmatter(read(p))
        sources = fm.get("sources", [])
        if isinstance(sources, str):
            sources = [sources]
        if not isinstance(sources, list):
            continue
        for src in sources:
            if not src or str(src).strip() in ("[]", ""):
                continue
            if not source_path_exists(str(src), root, p):
                add(
                    issues,
                    "error",
                    "missing_source_path",
                    p,
                    root,
                    f"source path not found: {src}",
                    None,
                )


def check_index(root: Path, brain: Path, issues: list[dict]) -> None:
    wiki = brain / "wiki"
    index = wiki / "index.md"
    if not index.exists():
        return
    text = read(index).lower()
    for p in wiki.rglob("*.md") if wiki.exists() else []:
        if p == index:
            continue
        no_ext = str(p.relative_to(wiki).with_suffix(""))
        if f"[[{p.stem.lower()}]]" not in text and f"[[{no_ext.lower()}]]" not in text and no_ext.lower() not in text:
            add(issues, "warn", "missing_index_entry", p, root, f"page missing from index: {rel(p, root)}")


def parse_updated_line(path: Path) -> datetime | None:
    if not path.exists():
        return None
    for line in read(path).splitlines():
        if line.lower().startswith("updated:"):
            raw = line.split(":", 1)[1].strip()
            for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    return datetime.strptime(raw[:16] if fmt.endswith("%M") else raw[:10], fmt)
                except ValueError:
                    pass
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                return None
    return None


def check_session_brief_staleness(root: Path, brain: Path, issues: list[dict]) -> None:
    brief = brain / "state" / "session-brief.md"
    updated = parse_updated_line(brief)
    if updated is None:
        add(issues, "warn", "stale_session_brief", brief, root, "session-brief.md has no parseable Updated line")
        return
    days = (datetime.now() - updated).days
    if days > 7:
        add(issues, "warn", "stale_session_brief", brief, root, f"session-brief.md has not been updated in {days} days")


def check_audit(root: Path, brain: Path, issues: list[dict]) -> None:
    audit = brain / "audit"
    if not audit.exists():
        return
    for p in audit.glob("*.md"):
        if p.name == ".gitkeep":
            continue
        text = read(p)
        if "status: open" not in text:
            add(issues, "warn", "audit_shape", p, root, f"open audit may be malformed or missing status: {rel(p, root)}")


def check_evidence_aging(root: Path, brain: Path, issues: list[dict]) -> None:
    raw = brain / "raw"
    wiki = brain / "wiki"
    if not raw.exists():
        return
    wiki_text = "\n".join(read(p) for p in wiki.rglob("*.md")) if wiki.exists() else ""
    cutoff_days = 90
    now = datetime.now().timestamp()
    for p in raw.rglob("*"):
        if not p.is_file() or p.name == ".gitkeep":
            continue
        age_days = int((now - p.stat().st_mtime) / 86400)
        if age_days <= cutoff_days:
            continue
        relpath = rel(p, root)
        if relpath not in wiki_text and p.name not in wiki_text and p.stem not in wiki_text:
            add(
                issues,
                "suggest",
                "stale_unreferenced_evidence",
                p,
                root,
                f"raw source is {age_days} days old and has no obvious wiki reference; consider archival review",
            )


def check_graph_report(root: Path, issues: list[dict]) -> None:
    report = root / "graphify-out" / "GRAPH_REPORT.md"
    if not report.exists():
        add(issues, "info", "missing_graph_report", report, root, "graphify-out/GRAPH_REPORT.md not found; run `/graphify .` when a relationship map is needed")


def page_updated_date(path: Path) -> datetime | None:
    if not path.exists():
        return None
    text = read(path)
    fm = extract_frontmatter(text)
    raw = fm.get("updated") or fm.get("date")
    if raw:
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(str(raw)[:16] if fmt.endswith("%M") else str(raw)[:10], fmt)
            except ValueError:
                pass
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            pass
    return parse_updated_line(path)


def wiki_lookup(wiki: Path) -> dict[str, Path]:
    lookup: dict[str, Path] = {}
    if not wiki.exists():
        return lookup
    for p in wiki.rglob("*.md"):
        rel_no_ext = str(p.relative_to(wiki).with_suffix(""))
        lookup[rel_no_ext.lower()] = p
        lookup[p.stem.lower()] = p
    return lookup


def resolve_wikilink_path(target: str, lookup: dict[str, Path]) -> Path | None:
    needle = normalize_link(target)
    if not needle:
        return None
    if needle in lookup:
        return lookup[needle]
    matches = [path for key, path in lookup.items() if key.endswith(needle)]
    return matches[0] if matches else None


def index_lines_for_page(index_text: str, page: Path, wiki: Path) -> list[str]:
    rel_no_ext = str(page.relative_to(wiki).with_suffix(""))
    candidates = {page.stem.lower(), rel_no_ext.lower()}
    lines: list[str] = []
    for line in index_text.splitlines():
        low = line.lower()
        if any(f"[[{c}]]" in low or c in low for c in candidates):
            lines.append(line)
    return lines


def first_date_in_text(text: str) -> datetime | None:
    m = re.search(r"(20\d{2}-\d{2}-\d{2})", text)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d")
    except ValueError:
        return None


def target_from_conflict_block(block: str, lookup: dict[str, Path]) -> Path | None:
    for line in block.splitlines():
        if line.lower().startswith(("target:", "page:", "wiki page:")):
            target = line.split(":", 1)[1].strip().strip("'\"")
            if target.startswith("[[") and target.endswith("]]" ):
                target = target[2:-2]
            resolved = resolve_wikilink_path(target, lookup)
            if resolved:
                return resolved
    for m in WIKILINK_RE.finditer(block):
        resolved = resolve_wikilink_path(m.group(1), lookup)
        if resolved:
            return resolved
    return None


REQUIRED_FRONTMATTER_FIELDS = {"title", "type", "created", "updated", "status", "sources", "tags"}
DEPRECATED_FIELDS = {"name", "author", "score"}


def check_frontmatter_schema(root: Path, brain: Path, issues: list[dict]) -> None:
    """Check that all wiki pages use standardized frontmatter fields.

    - Every page must have a `title:` field (not `name:`).
    - Deprecated fields (`name:`, `author:`, `score:`) are flagged.
    - Source summary pages should use `reliability:` instead of `score:`.
    """
    wiki = brain / "wiki"
    if not wiki.exists():
        return
    for p in wiki.rglob("*.md"):
        if p.name == "index.md":
            continue
        fm = extract_frontmatter(read(p))
        if not fm:
            add(issues, "warn", "missing_frontmatter", p, root, f"no frontmatter found in wiki page")
            continue
        # Check for deprecated `name:` instead of `title:`
        if "name" in fm and "title" not in fm:
            add(issues, "error", "deprecated_frontmatter_field", p, root,
                f"uses `name:` instead of `title:` — rename to `title:` per wiki-schema standard")
        # Check for other deprecated fields
        for dep_field in DEPRECATED_FIELDS:
            if dep_field in fm and dep_field != "name":
                replacement = "reliability" if dep_field == "score" else None
                msg = f"deprecated frontmatter field `{dep_field}:` found"
                if replacement:
                    msg += f" — use `{replacement}:` instead per wiki-schema standard"
                else:
                    msg += " — remove non-standard field per wiki-schema standard"
                add(issues, "warn", "deprecated_frontmatter_field", p, root, msg)
        # Check for missing required fields
        missing = REQUIRED_FRONTMATTER_FIELDS - set(fm.keys())
        if missing:
            add(issues, "warn", "missing_frontmatter_field", p, root,
                f"missing required frontmatter field(s): {', '.join(sorted(missing))}")


def check_contradictions(root: Path, brain: Path, issues: list[dict]) -> None:
    wiki = brain / "wiki"
    if not wiki.exists():
        return
    lookup = wiki_lookup(wiki)
    index = wiki / "index.md"
    index_text_value = read(index) if index.exists() else ""

    superseded_pages: set[Path] = set()
    for page in wiki.rglob("*.md"):
        if page == index:
            continue
        fm = extract_frontmatter(read(page))
        if str(fm.get("status", "")).strip().lower() == "superseded":
            superseded_pages.add(page)
            lines = index_lines_for_page(index_text_value, page, wiki)
            if any("superseded" not in line.lower() for line in lines):
                add(issues, "warn", "contradiction_superseded_active", index, root, f"superseded page still listed as active in index: {rel(page, root)}")

    decisions = wiki / "decisions"
    superseded_decisions = {p for p in superseded_pages if decisions in p.parents}
    if superseded_decisions and decisions.exists():
        for page in decisions.rglob("*.md"):
            if page in superseded_decisions:
                continue
            text = read(page)
            for m in WIKILINK_RE.finditer(text):
                target = resolve_wikilink_path(m.group(1), lookup)
                if target in superseded_decisions:
                    line_no = line_for(text, m.start())
                    line_text = text.splitlines()[line_no - 1] if line_no - 1 < len(text.splitlines()) else ""
                    if "superseded" not in line_text.lower():
                        add(issues, "suggest", "decision_links_superseded", page, root, f"decision wikilink may point to superseded page: {rel(page, root)} → [[{m.group(1)}]]", line_no)

    open_questions = wiki / "open-questions.md"
    if not open_questions.exists():
        return
    oq_text = read(open_questions)
    blocks = re.split(r"(?=^##+\s+)", oq_text, flags=re.MULTILINE)
    for block in blocks:
        low = block.lower()
        if "conflict" not in low or not re.search(r"status:\s*resolved", low):
            continue
        resolved_dt = first_date_in_text(block)
        target = target_from_conflict_block(block, lookup)
        if not resolved_dt or not target:
            continue
        target_dt = page_updated_date(target)
        if target_dt and target_dt.date() < resolved_dt.date():
            add(issues, "suggest", "resolved_conflict_not_reflected", open_questions, root, f"resolved conflict in open-questions.md but target page may not reflect resolution: {rel(target, root)}")


def build_report(root: Path) -> tuple[int, dict]:
    root = root.expanduser().resolve()
    brain = root / ".brain"
    issues: list[dict] = []
    if not brain.exists():
        add(issues, "error", "missing_brain", brain, root, f"no .brain directory at {brain}")
    else:
        check_required(root, brain, issues)
        check_wikilinks(root, brain, issues)
        check_sources(root, brain, issues)
        check_index(root, brain, issues)
        check_session_brief_staleness(root, brain, issues)
        check_audit(root, brain, issues)
        check_evidence_aging(root, brain, issues)
        check_graph_report(root, issues)
        check_frontmatter_schema(root, brain, issues)
        check_contradictions(root, brain, issues)

    summary = {sev: 0 for sev in SEVERITIES}
    for issue in issues:
        summary[issue["severity"]] += 1
    report = {
        "timestamp": now_iso(),
        "project_root": str(root),
        "issues": issues,
        "summary": summary,
    }
    code = 1 if summary["error"] else 0
    return code, report


def print_human(report: dict) -> None:
    print(f"Project root: {report['project_root']}")
    print("Summary: " + ", ".join(f"{k}={v}" for k, v in report["summary"].items()))
    issues = report["issues"]
    if not issues:
        print("No issues found.")
        return
    for sev in SEVERITIES:
        bucket = [i for i in issues if i["severity"] == sev]
        if not bucket:
            continue
        print(f"\n{sev.upper()}:")
        for i in bucket:
            loc = i["file"] or "(project)"
            if i.get("line"):
                loc += f":{i['line']}"
            print(f"  - [{i['category']}] {loc} — {i['message']}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lint a project brain.")
    parser.add_argument("project_root")
    parser.add_argument("--json", action="store_true", dest="as_json", help="print machine-readable JSON")
    return parser.parse_args(argv[1:])


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    code, report = build_report(Path(args.project_root))
    if args.as_json:
        print(json.dumps(report, indent=2))
    else:
        print_human(report)
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
