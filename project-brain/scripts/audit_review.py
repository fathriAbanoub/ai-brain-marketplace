#!/usr/bin/env python3
"""List audit feedback in severity order.

Usage:
    audit_review.py <brain-root> [--open|--resolved|--all]
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
SEVERITY_ORDER = {"error": 0, "warn": 1, "suggest": 2, "info": 3}


def parse_frontmatter(text: str) -> dict | None:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    result: dict = {}
    for line in m.group(1).split("\n"):
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, _, rest = line.partition(":")
        key = key.strip()
        val = rest.strip()
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            result[key] = [p.strip().strip('"').strip("'") for p in inner.split(",") if p.strip()]
        elif val.startswith('"') and val.endswith('"'):
            result[key] = val[1:-1].replace("\\n", "\n").replace('\\"', '"')
        elif val.startswith("'") and val.endswith("'"):
            result[key] = val[1:-1]
        else:
            result[key] = val
    return result


def extract_comment_one_line(text: str) -> str:
    in_comment = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("# comment"):
            in_comment = True
            continue
        if not in_comment:
            continue
        if not stripped:
            continue
        if stripped.startswith("#"):
            break
        return stripped[:100]
    return "(no comment body)"


def load_files(brain_root: Path, mode: str) -> list[Path]:
    audit_dir = brain_root / "audit"
    files: list[Path] = []
    if mode in ("open", "all"):
        files.extend(p for p in audit_dir.glob("*.md") if p.name != ".gitkeep")
    if mode in ("resolved", "all"):
        resolved = audit_dir / "resolved"
        if resolved.exists():
            files.extend(p for p in resolved.glob("*.md") if p.name != ".gitkeep")
    return sorted(files)


def main(brain_root: str, mode: str) -> int:
    root_path = Path(brain_root)
    audit_dir = root_path / "audit"
    if not audit_dir.exists():
        print(f"ERROR: audit/ not found at {audit_dir}", file=sys.stderr)
        return 1

    entries: list[dict] = []
    for p in load_files(root_path, mode):
        text = p.read_text(encoding="utf-8", errors="replace")
        fm = parse_frontmatter(text)
        if fm is None:
            print(f"⚠ {p.relative_to(root_path)} — missing frontmatter", file=sys.stderr)
            continue
        fm["_path"] = str(p.relative_to(root_path))
        fm["_one_liner"] = extract_comment_one_line(text)
        entries.append(fm)

    entries.sort(key=lambda e: (SEVERITY_ORDER.get(e.get("severity", "info"), 99), e.get("created", ""), e.get("_path", "")))

    if not entries:
        print(f"No {mode} audit files found.")
        return 0

    grouped: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        grouped[e.get("target", "(no-target)")].append(e)

    print(f"{mode.upper()} audits: {len(entries)} across {len(grouped)} target files")
    print("Processing order: error → warn → suggest → info\n")

    for severity in ("error", "warn", "suggest", "info"):
        sev_entries = [e for e in entries if e.get("severity", "info") == severity]
        if not sev_entries:
            continue
        print(f"## {severity.upper()}")
        by_target: dict[str, list[dict]] = defaultdict(list)
        for e in sev_entries:
            by_target[e.get("target", "(no-target)")].append(e)
        for target in sorted(by_target):
            bucket = by_target[target]
            print(f"{target} ({len(bucket)} {mode})")
            for e in bucket:
                aid = e.get("id", "?")
                author = e.get("author", "?")
                created = e.get("created", "?")[:10]
                line = e.get("_one_liner", "")
                print(f"   [{aid}] {severity}: {line} — {author}, {created}")
            print()

    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    root = sys.argv[1]
    mode = "open"
    for arg in sys.argv[2:]:
        if arg == "--open":
            mode = "open"
        elif arg == "--resolved":
            mode = "resolved"
        elif arg == "--all":
            mode = "all"
        else:
            print(f"Unknown flag: {arg}", file=sys.stderr)
            sys.exit(1)
    sys.exit(main(root, mode))
