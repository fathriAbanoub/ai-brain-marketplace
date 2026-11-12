#!/usr/bin/env python3
"""Health-check a project brain.

Usage:
    lint_brain.py <project-root> [--json] [--reindex] [--verify]

--verify re-checks every inline citation and records SHA-256 stamps for cited
files in .brain/verification.json (clean pages only). Stamps are the ground
truth for stale_citation detection; no other code path writes them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, date, timezone
from pathlib import Path

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
# Hybrid markdown-wikilink `[[target](path)]`: no closing ]] survives, so the
# plain wikilink regex is blind to it. Observed live in a real session.
HYBRID_WIKILINK_RE = re.compile(r"\[\[([^\]]+?)\]\(")
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
SEVERITIES = ("error", "warn", "suggest", "info")
# Inline code spans: one or more backticks, content without backticks or
# newlines, closed by the same number of backticks (any closing run accepts
# the common single/double-backtick cases; nesting is not a thing).
CODE_SPAN_RE = re.compile(r"`+[^`\n]*`+")
# Fenced code block opener: 3+ backticks or tildes after indentation (an info
# string may follow; it is masked with the fence). Indentation depth is not
# checked against a bound: deeper-indented fence-like lines are indented code
# either way, so masking them is correct too.
FENCE_OPEN_RE = re.compile(r"(?:`{3,}|~{3,})")


def strip_code_regions(text: str) -> str:
    """Mask fenced code blocks and inline code spans with same-length
    whitespace, so wikilink scanners skip code (`` `[[ghost]]` `` in docs is
    documentation, not a link) while line_for() keeps reporting the original
    line numbers: every '\\n' survives, only intra-line content is blanked.
    An unclosed fence masks to the end of the text."""
    out: list[str] = []
    fence: tuple[str, int] | None = None  # (fence char, minimum closer length)
    for line in text.split("\n"):
        stripped = line.lstrip(" \t")
        if fence is not None:
            out.append("")
            closer = stripped.rstrip()
            if set(closer) == {fence[0]} and len(closer) >= fence[1]:
                fence = None
            continue
        opener = FENCE_OPEN_RE.match(stripped)
        if opener:
            fence = (opener.group(0)[0], len(opener.group(0)))
            out.append("")
            continue
        # ponytail: inline spans are matched per line, so a backtick pair
        # spanning two lines is not masked; upgrade path: a cross-line span
        # pass if such pages are ever observed in practice.
        out.append(CODE_SPAN_RE.sub(lambda m: " " * len(m.group()), line))
    return "\n".join(out)

# Fix commands printed inside rule messages. Every message that names a
# mechanical fix names the SAME command for every instance of that rule
# (KD-05: an agent that fixes one instance by hand-editing generated files
# created new duplicates — the fix must be script-shaped, not per-file).
REINDEX_HINT = "regenerate with `project-brain-lint <root> --reindex`; never hand-edit index.md"
VERIFY_HINT = "then run `project-brain-lint <root> --verify`"
INIT_HINT = 'run `project-brain-init <root> "<Project Name>"`'

# --- WP4: citations, staleness, provenance (KD-01, KD-02, KD-07, KD-14) ---
# Inline citation syntax (documented in skills/brain/references/wiki-schema.md):
#     {{src path/to/file.ts:10-20 "anchorText"}}
CITATION_RE = re.compile(r'\{\{src\s+([^:\s]+):(\d+)(?:-(\d+))?\s+"([^"]*)"\}\}')
CITATION_ANCHOR_WINDOW_LINES = 5  # anchor must appear within this many lines after the cited range (mission constant)
# ponytail: heuristic warn for bare `file.ext:NNN` refs (closed pattern); it
# cannot catch prose claims with no line ref at all. Upgrade path: extend the
# pattern, never special-case files.
UNANCHORED_REF_RE = re.compile(r"(?<![\w/.:@-])([A-Za-z0-9_][\w.+@/~-]*\.[A-Za-z0-9]{1,8}):(\d{1,5})\b")
RATIONALE_COMMIT_RE = re.compile(r"^commit:([0-9a-f]{7,40})$")
RATIONALE_SCALARS = ("user-confirmed", "inferred", "unknown")
# ponytail: closed phrase list for forbidden all-clear claims; every pattern
# lives here and nowhere else. Upgrade path: extend this tuple.
ALL_CLEAR_PHRASES = ("no contradictions", "no conflicts", "no inconsistencies", "no discrepancies", "no mismatches")
# ponytail: closed word list for volatile-count detection (counts/versions
# drift); misses e.g. "~1k LOC". Upgrade path: extend the alternation.
VOLATILE_COUNT_RE = re.compile(r"\b\d+\s+(?:tests?|files?|modules?|packages?|components?|pages?|commits?|nodes?|edges?|dependencies|users?|routes?)\b", re.IGNORECASE)
VERIFICATION_FILE = "verification.json"
CROSSREFS_RECEIPT = "audit/crossrefs-report.json"
# Consecutive failing gate runs (a nonzero `project-brain-lint` exit or a
# `project-brain-doctor --strict` run that is not all-passed) before the agent
# must stop and write the honest report. Used by BOTH scripts via
# record_repair_round(); the count lives on disk so it survives compaction.
MAX_REPAIR_ROUNDS = 3
REPAIR_ROUNDS_REL = Path(".brain") / "state" / "repair-rounds"
# 0.10.0: the counter is keyed PER GATE. A shared counter reset by any
# passing run let a loop alternating lint-pass / doctor-strict-fail repair
# forever without ever reaching the limit.
GATE_LINT = "lint"
GATE_DOCTOR_STRICT = "doctor-strict"
GATES = (GATE_LINT, GATE_DOCTOR_STRICT)
# A `sources:` entry that is not a plain path string — flow-style {path: …}
# objects split on commas into bogus half-entries.
SOURCES_OBJECT_MARKERS = ("{", "}", ": ")
# ponytail: closed secret-pattern list — literal signatures only, no entropy
# analysis, no context awareness (a quoted example key also trips it).
# Upgrade path: extend the tuples; do not loosen lightly.
SECRET_PATTERNS: tuple[tuple[str, "re.Pattern[str]"], ...] = (
    ("private key header", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    ("aws access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("openai-style key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
)
SECRET_NAME_VALUE_RE = re.compile(
    r"(?im)^[ \t]*([A-Za-z0-9_]*(?:SECRET|TOKEN|PASSWORD|API_KEY)[A-Za-z0-9_]*)[ \t]*=[ \t]*\S")


class VerificationCorruptError(Exception):
    """.brain/verification.json exists but is not usable — fail closed."""


def rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def body_text(text: str) -> str:
    m = FRONTMATTER_RE.match(text)
    return text[m.end():] if m else text


def norm_ws(s: str) -> str:
    """Whitespace-normalize for anchor matching: collapse runs, honor literal
    \\n / \\t escapes that single-line citation anchors must use, drop CR."""
    return " ".join(s.replace("\\n", " ").replace("\\t", " ").replace("\r", " ").split())


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def git_head(root: Path) -> str | None:
    try:
        proc = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    sha = proc.stdout.strip() if proc.returncode == 0 else ""
    return sha if re.fullmatch(r"[0-9a-f]{40}", sha) else None


def has_git(root: Path) -> bool:
    try:
        proc = subprocess.run(["git", "-C", str(root), "rev-parse", "--git-dir"],
                              capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def git_commit_exists(root: Path, sha: str) -> bool:
    try:
        proc = subprocess.run(["git", "-C", str(root), "cat-file", "-e", sha + "^{commit}"],
                              capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


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
            add(issues, "error", "missing_required_path", p, root,
                f"missing required path: {rel(p, root)} — re-run scaffold ({INIT_HINT}) to regenerate template files")


def _is_non_wiki_file(target: str, root: Path) -> bool:
    """True when a failed wikilink target names a real repo file outside the
    wiki (e.g. `[[graphify-out/GRAPH_REPORT.md]]`) — those are cited as
    code-span paths, not wikilinks."""
    t = target.strip().replace("\\", "/").removeprefix("/")
    if not t or t.startswith(".."):
        return False
    return (root / t).is_file() or (root / f"{t}.md").is_file()


def check_wikilinks(root: Path, brain: Path, issues: list[dict]) -> None:
    wiki = brain / "wiki"
    keys, pages = collect_wiki_keys(wiki)
    for p in pages:
        text = read(p)
        # Code is documentation, not links: skip fenced blocks and inline
        # code spans (positions preserved, so line numbers stay exact).
        scan = strip_code_regions(text)
        for m in WIKILINK_RE.finditer(scan):
            target = m.group(1).strip()
            if not resolve_wikilink(target, keys):
                if _is_non_wiki_file(target, root):
                    fix = (f"non-wiki files are referenced as a code-span path (`{target}`), "
                           "not as a [[wikilink]] — or create a wiki page for it")
                else:
                    fix = "create the target page or fix the link (wiki page names, no .md suffix)"
                add(
                    issues,
                    "error",
                    "broken_wikilink",
                    p,
                    root,
                    f"[[{target}]] — target not found in wiki: {fix}",
                    line_for(scan, m.start()),
                )
        # Hybrid markdown-wikilinks `[[target](path)]` (observed live) have no
        # closing `]]`, so the plain wikilink regex cannot see them — they
        # render broken everywhere and used to sail through lint unnoticed.
        for m in HYBRID_WIKILINK_RE.finditer(scan):
            target = m.group(1).strip()
            if _is_non_wiki_file(target, root):
                fix = (f"non-wiki files are referenced as a code-span path (`{target}`), "
                       "not as a [[wikilink]] — or create a wiki page for it")
            else:
                fix = "create the target page or fix the link (wiki page names, no .md suffix)"
            add(
                issues,
                "error",
                "broken_wikilink",
                p,
                root,
                f"hybrid markdown-wikilink [[{target}](…)]] — target not found in wiki: {fix}",
                line_for(scan, m.start()),
            )


def source_path_exists(src: str, root: Path, file: Path) -> bool:
    """Resolve a `sources:` frontmatter entry.

    Documented convention (skills/brain/references/wiki-schema.md):
    - a path to raw evidence, resolved from the project root (e.g.
      `.brain/raw/notes/x.md` or a repo file),
    - or a wiki source-summary page, written as `sources/<name>.md` and
      resolved against `.brain/wiki/` (the summaries' home directory),
    - or a page-relative path from the wiki page's own directory.
    An absolute path is used as-is.
    """
    src = src.strip().strip('"\'')
    if not src:
        return True
    candidate = Path(src).expanduser()
    if candidate.is_absolute():
        return candidate.exists()
    wiki_dir = root / ".brain" / "wiki"
    candidates = [
        root / candidate,               # project-root relative (raw evidence, repo files)
        file.parent / candidate,        # page relative
        wiki_dir / candidate,           # wiki relative (source-summary pages: sources/<name>.md)
    ]
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
        # Flow-style {path: …} objects are split on commas by the frontmatter
        # reader into bogus half-entries, which then fail path resolution and
        # report a misleading "fix the path" hint (one issue per page instead).
        objects = [s for s in sources if any(m in str(s) for m in SOURCES_OBJECT_MARKERS)]
        if objects:
            add(
                issues,
                "error",
                "invalid_sources_entry",
                p,
                root,
                "sources entries must be plain root-relative path strings, not {path: …} objects; "
                "reliability belongs only in the frontmatter of wiki/sources/* pages",
                None,
            )
        for src in sources:
            if not src or str(src).strip() in ("[]", ""):
                continue
            if src in objects:
                continue
            if not source_path_exists(str(src), root, p):
                add(
                    issues,
                    "error",
                    "missing_source_path",
                    p,
                    root,
                    f"source path not found: {src} — fix the path or create the file it names (a source-summary page lives at .brain/wiki/sources/<name>.md)",
                    None,
                )


def check_index(root: Path, brain: Path, issues: list[dict]) -> None:
    """KD-05: verify index invariants that the old substring check could not see.

    - every eligible wiki page is listed exactly once (missing → warn,
      listed more than once / under multiple sections → error)
    - every index entry resolves to an existing page (dangling → error)
    """
    wiki = brain / "wiki"
    index = wiki / "index.md"
    if not index.exists():
        return
    index_text = read(index)
    # Index entries are wikilink list items; prose mentions do not count, and
    # fenced code blocks in the index are not entries either.
    index_scan = strip_code_regions(index_text)
    entry_re = re.compile(r"^\s*-\s*\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]", re.MULTILINE)
    entries = [(normalize_link(m.group(1)), line_for(index_scan, m.start()))
               for m in entry_re.finditer(index_scan)]

    pages = [p for p in (wiki.rglob("*.md") if wiki.exists() else []) if p != index]
    for p in pages:
        rel_no_ext = str(p.relative_to(wiki).with_suffix("")).lower()
        stem = p.stem.lower()
        # An entry references this page when its target equals the page's
        # relative key, its stem, or a path suffix of the key.
        hits = [ln for needle, ln in entries
                if needle in (rel_no_ext, stem) or rel_no_ext.endswith("/" + needle)]
        if len(hits) == 0:
            add(issues, "warn", "missing_index_entry", p, root,
                f"page missing from index: {rel(p, root)} (run `project-brain-lint <root> --reindex`)")
        elif len(hits) > 1:
            add(issues, "error", "duplicate_index_entry", p, root,
                f"page listed {len(hits)} times in index (lines {', '.join(str(h) for h in hits)}): {rel(p, root)} — every page must appear exactly once; {REINDEX_HINT}")

    page_keys = set()
    for p in pages:
        rel_no_ext = str(p.relative_to(wiki).with_suffix("")).lower()
        page_keys.add(rel_no_ext)
        page_keys.add(p.stem.lower())
    for needle, ln in entries:
        if not needle:
            continue
        if not any(key == needle or key.endswith("/" + needle) for key in page_keys):
            add(issues, "error", "index_entry_target_missing", index, root,
                f"index entry points at no wiki page: [[{needle}]] — {REINDEX_HINT}; if the page itself is missing, create it", ln)


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
        add(issues, "warn", "stale_session_brief", brief, root,
            f"session-brief.md has not been updated in {days} days — update .brain/state/session-brief.md (its Updated line) now")


def check_brief_task_checklist(root: Path, brain: Path, issues: list[dict]) -> None:
    """KD-06: task checklists live in tasks/next-actions.md ONLY.

    A checklist in the session brief is how the earlier run ended up with a
    brief saying items were done while next-actions.md said the same items
    were open. Deterministic rule: one task file, the brief links to it.
    """
    brief = brain / "state" / "session-brief.md"
    if not brief.exists():
        return
    for ln, line in enumerate(read(brief).splitlines(), start=1):
        if re.match(r"^\s*[-*]\s+\[[ xX]\]", line):
            add(issues, "error", "task_checklist_in_brief", brief, root,
                f"task checklist in session brief (line {ln}) — tasks belong in tasks/next-actions.md only", ln)
            return


def check_nested_graphify_output(root: Path, issues: list[dict]) -> None:
    """KD-08: detect a nested graphify-out/graphify-out/ stale cache copy.

    Cause: invoking graphify with the output directory itself as the target
    path (e.g. `graphify extract graphify-out`) makes it nest a fresh output
    tree inside the output. The skill text forbids passing graphify-out as
    the path; this detector catches it when it happens anyway.
    """
    nested = root / "graphify-out" / "graphify-out"
    if nested.exists():
        add(issues, "error", "nested_graphify_output", nested, root,
            "nested graphify-out/graphify-out/ detected (stale cache copy): delete the nested "
            "graphify-out/graphify-out/ directory and rebuild with `graphify .` from the project root — "
            "never pass graphify-out itself as the graphify path")


def check_audit(root: Path, brain: Path, issues: list[dict]) -> None:
    audit = brain / "audit"
    if not audit.exists():
        return
    for p in audit.glob("*.md"):
        if p.name == ".gitkeep":
            continue
        text = read(p)
        if "status: open" not in text:
            add(issues, "warn", "audit_shape", p, root,
                f"open audit may be malformed or missing status: {rel(p, root)} — add a `status: open` line, or move the file to .brain/audit/resolved/")


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


MIN_WIKI_PAGE_CHARS = 60


def check_short_wiki_pages(root: Path, brain: Path, issues: list[dict]) -> None:
    """Flag wiki pages too short to carry real knowledge (body, excluding frontmatter)."""
    wiki = brain / "wiki"
    if not wiki.exists():
        return
    for p in wiki.rglob("*.md"):
        if p.name == "index.md":
            continue
        text = read(p)
        m = FRONTMATTER_RE.match(text)
        body = text[m.end():] if m else text
        body_chars = len(re.sub(r"\s+", "", body))
        if body_chars < MIN_WIKI_PAGE_CHARS:
            add(issues, "warn", "short_wiki_page", p, root,
                f"page body is only {body_chars} chars (min {MIN_WIKI_PAGE_CHARS}); expand the page from real sources or delete the stub — stub pages below this are not mined to MemPalace")


def check_graph_report(root: Path, issues: list[dict]) -> None:
    report = root / "graphify-out" / "GRAPH_REPORT.md"
    if not report.exists():
        add(issues, "info", "missing_graph_report", report, root,
            "graphify-out/GRAPH_REPORT.md not found; rebuild via the /graphify skill (primary) when a relationship map is needed — CLI fallback: `graphify .`")


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
    block = strip_code_regions(block)  # code samples are not links
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
            add(issues, "warn", "missing_frontmatter", p, root,
                "no frontmatter found in wiki page — add title/type/created/updated/status/sources/tags per the plugin's wiki-schema reference")
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
                add(issues, "warn", "contradiction_superseded_active", index, root,
                    f"superseded page still listed as active in index: {rel(page, root)} — mark the entry superseded in wiki/index.md, or clear the page's superseded status")

    decisions = wiki / "decisions"
    superseded_decisions = {p for p in superseded_pages if decisions in p.parents}
    if superseded_decisions and decisions.exists():
        for page in decisions.rglob("*.md"):
            if page in superseded_decisions:
                continue
            text = read(page)
            scan = strip_code_regions(text)  # code samples are not links
            for m in WIKILINK_RE.finditer(scan):
                target = resolve_wikilink_path(m.group(1), lookup)
                if target in superseded_decisions:
                    line_no = line_for(scan, m.start())
                    line_text = text.splitlines()[line_no - 1] if line_no - 1 < len(text.splitlines()) else ""
                    if "superseded" not in line_text.lower():
                        add(issues, "suggest", "decision_links_superseded", page, root,
                            f"decision wikilink may point to superseded page: {rel(page, root)} → [[{m.group(1)}]] — mark the link line superseded (e.g. `- [[{m.group(1)}]] (superseded by [[<new page>]])`)", line_no)

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


def load_verification(brain: Path) -> dict | None:
    """Load .brain/verification.json; fail closed when corrupt (KD-02)."""
    path = brain / VERIFICATION_FILE
    if not path.exists():
        return None
    try:
        data = json.loads(read(path))
    except ValueError as exc:
        raise VerificationCorruptError(f"{VERIFICATION_FILE} is corrupt: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("pages", {}), dict):
        raise VerificationCorruptError(
            f"{VERIFICATION_FILE} is corrupt: expected an object with a 'pages' object")
    return data


def write_verification(root: Path, citation_state: dict) -> None:
    """--verify: stamp clean pages with SHA-256 hashes of their cited files.

    A page is stamped only when it cites at least one file and every citation
    passes the drift checks. Stamps are the staleness ground truth; nothing
    else may write this file (agents never hand-write verification.json).
    """
    brain = root / ".brain"
    pages = {
        page_rel: {"verified_at": now_iso(), "files": info["files"]}
        for page_rel, info in citation_state.items()
        if info["has_citations"] and not info["drift"]
    }
    data = {"version": 1, "generated_at": now_iso(), "commit": git_head(root), "pages": pages}
    path = brain / VERIFICATION_FILE
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)  # atomic: no half-written stamp set
    print(f"verification: stamped {len(pages)} page(s) -> {rel(path, root)}", file=sys.stderr)


def check_citations(root: Path, brain: Path, issues: list[dict], citation_state: dict) -> None:
    """KD-01/KD-02: validate {{src path:a-b "anchor"}} citations on every page.

    citation_drift (error): cited file missing, range outside the file, or
    anchor text not found (whitespace-normalized) within
    CITATION_ANCHOR_WINDOW_LINES lines after the range. Bare `file.ext:NNN`
    refs without an anchor warn (unanchored_line_ref).
    """
    wiki = brain / "wiki"
    if not wiki.exists():
        return
    for p in wiki.rglob("*.md"):
        if p.name == "index.md":
            continue
        text = read(p)
        body = body_text(text)
        offset = len(text) - len(body)
        info = {"has_citations": False, "drift": False, "files": {}}
        spans: list[tuple[int, int]] = []
        for m in CITATION_RE.finditer(body):
            spans.append((m.start(), m.end()))
            info["has_citations"] = True
            path_s, start_s, end_s, anchor = m.groups()
            line_no = text.count("\n", 0, offset + m.start()) + 1
            target = root / path_s
            if not target.is_file():
                add(issues, "error", "citation_drift", p, root,
                    f'cited file not found: {path_s} — cite a real project-root-relative path; find the right file and locate the real lines with `grep -n "<anchor>" <file>` (or a bounded Read) before re-citing, {VERIFY_HINT}', line_no)
                info["drift"] = True
                continue
            start = int(start_s)
            end = int(end_s) if end_s else start
            lines = read(target).splitlines()
            if start < 1 or end < start or end > len(lines):
                add(issues, "error", "citation_drift", p, root,
                    f'cited range {start}-{end} outside {path_s} ({len(lines)} lines) — locate the real lines with `grep -n "{anchor}" {path_s}` (or a bounded Read), never copy line numbers from docs or summaries, {VERIFY_HINT}', line_no)
                info["drift"] = True
                continue
            window = "\n".join(lines[start - 1:end + CITATION_ANCHOR_WINDOW_LINES])
            if norm_ws(anchor) not in norm_ws(window):
                add(issues, "error", "citation_drift", p, root,
                    f'anchor text not found within {CITATION_ANCHOR_WINDOW_LINES} lines of {path_s}:{start}-{end} — locate the real lines with `grep -n "{anchor}" {path_s}` and re-cite the range they actually appear in, {VERIFY_HINT}', line_no)
                info["drift"] = True
                continue
            info["files"][path_s] = sha256_file(target)
        for m in UNANCHORED_REF_RE.finditer(body):
            if any(s <= m.start() < e for s, e in spans):
                continue
            line_no = text.count("\n", 0, offset + m.start()) + 1
            add(issues, "warn", "unanchored_line_ref", p, root,
                f'bare file:line reference {m.group(0)!r} — use {{{{src {m.group(1)}:{m.group(2)} "anchorText"}}}} so it can be verified',
                line_no)
        citation_state[rel(p, brain)] = info


def check_stale_citations(root: Path, brain: Path, issues: list[dict],
                          citation_state: dict, verification: dict | None) -> None:
    """KD-02: a stamped page whose cited file's SHA-256 changed (or vanished) is stale."""
    if not verification:
        return
    stamps = verification.get("pages", {})
    for page_rel, info in citation_state.items():
        stamp = stamps.get(page_rel)
        if not isinstance(stamp, dict):
            continue
        page = brain / page_rel
        for cited, old_hash in (stamp.get("files") or {}).items():
            target = root / cited
            if not target.is_file():
                add(issues, "error", "stale_citation", page, root,
                    f"cited file no longer exists (was verified): {cited}")
            elif sha256_file(target) != str(old_hash):
                add(issues, "error", "stale_citation", page, root,
                    f"cited file changed since verification: {cited} — re-check the page, then run --verify")


def check_rationale_sources(root: Path, brain: Path, issues: list[dict]) -> None:
    """KD-07/KD-14: decision pages must state where their rationale comes from.

    rationale_source: commit:<sha> (must exist in git when git is available) |
    doc:<path> (must exist) | user-confirmed | inferred (body must carry an
    [inferred] tag) | unknown. Missing → warn; invalid → error.
    ponytail: commit: is skipped when the project has no git repo — cannot
    verify there; upgrade path: add an explicit unverifiable warning once
    brains routinely live outside git.
    """
    wiki = brain / "wiki"
    if not wiki.exists():
        return
    git_ok = has_git(root)
    for p in wiki.rglob("*.md"):
        if p.name == "index.md":
            continue
        text = read(p)
        fm = extract_frontmatter(text)
        if str(fm.get("type", "")).strip().lower() != "decision":
            continue
        raw = fm.get("rationale_source")
        if not raw or raw == []:
            add(issues, "warn", "missing_rationale_source", p, root,
                "decision page has no rationale_source: commit:<sha> | doc:<path> | user-confirmed | inferred | unknown")
            continue
        value = str(raw).strip()
        m = RATIONALE_COMMIT_RE.match(value)
        if m:
            if git_ok and not git_commit_exists(root, m.group(1)):
                add(issues, "error", "rationale_commit_missing", p, root,
                    f"rationale_source commit not found in repository: {value} — verify the sha (`git log --oneline`) or change rationale_source to doc:<path> or user-confirmed")
            continue
        if value.startswith("doc:"):
            doc = value[len("doc:"):].strip()
            if not doc:
                add(issues, "error", "invalid_rationale_source", p, root,
                    f"invalid rationale_source value: {value!r} (doc: needs a path)")
            elif not (root / doc).exists():
                add(issues, "error", "rationale_doc_missing", p, root,
                    f"rationale_source doc not found: {doc}")
            continue
        if value in RATIONALE_SCALARS:
            if value == "inferred" and "[inferred]" not in body_text(text):
                add(issues, "warn", "inferred_untagged", p, root,
                    "rationale_source is inferred — tag the claim [inferred] in the page body")
            continue
        add(issues, "error", "invalid_rationale_source", p, root,
            f"invalid rationale_source value: {value!r} (expected commit:<sha> | doc:<path> | user-confirmed | inferred | unknown)")


def check_all_clear_claims(root: Path, brain: Path, issues: list[dict], verification: dict | None) -> None:
    """KD-01: forbid unevidenced all-clear claims.

    A page may claim e.g. "no contradictions" only when (a) it has a current
    citation-verification stamp and (b) .brain/audit/crossrefs-report.json
    records a completed cross-reference check with zero missing targets.
    """
    wiki = brain / "wiki"
    if not wiki.exists():
        return
    receipt_ok = False
    receipt = brain / CROSSREFS_RECEIPT
    if receipt.is_file():
        try:
            rdata = json.loads(read(receipt))
        except ValueError:
            rdata = None
        receipt_ok = isinstance(rdata, dict) and rdata.get("missing") == []
    stamped = set((verification or {}).get("pages", {}))
    for p in wiki.rglob("*.md"):
        if p.name == "index.md":
            continue
        low = body_text(read(p)).lower()
        if not any(phrase in low for phrase in ALL_CLEAR_PHRASES):
            continue
        if rel(p, brain) in stamped and receipt_ok:
            continue
        add(issues, "error", "forbidden_all_clear", p, root,
            "all-clear claim without evidence: needs a current --verify stamp for this page AND "
            f"{CROSSREFS_RECEIPT} with zero missing cross-refs — run `project-brain-inventory <root> crossrefs` "
            f"and `project-brain-lint <root> --verify`, or drop the claim")


def check_brain_secrets(root: Path, brain: Path, issues: list[dict]) -> None:
    """KD-15: secrets must never live inside .brain/ (error; fails --strict)."""
    for p in sorted(brain.rglob("*")):
        if not p.is_file() or p.name == ".gitkeep":
            continue
        text = read(p)
        for label, pattern in SECRET_PATTERNS:
            m = pattern.search(text)
            if m:
                add(issues, "error", "brain_secret", p, root,
                    f"possible {label} inside .brain/ — remove it and rotate the credential",
                    text.count("\n", 0, m.start()) + 1)
        for m in SECRET_NAME_VALUE_RE.finditer(text):
            add(issues, "error", "brain_secret", p, root,
                f"possible secret assignment '{m.group(1)}=…' inside .brain/ — remove it and rotate the credential",
                text.count("\n", 0, m.start()) + 1)


def check_volatile_numbers(root: Path, brain: Path, issues: list[dict]) -> None:
    """KD-02: counts/versions drift — warn unless the line carries [unverified]."""
    wiki = brain / "wiki"
    if not wiki.exists():
        return
    for p in wiki.rglob("*.md"):
        if p.name == "index.md":
            continue
        text = read(p)
        body = body_text(text)
        fm_lines = text.count("\n", 0, len(text) - len(body))
        for ln, line in enumerate(body.splitlines(), start=1):
            if "[unverified]" in line:
                continue
            if VOLATILE_COUNT_RE.search(line):
                add(issues, "warn", "volatile_number", p, root,
                    f"volatile count needs a command+date or [unverified]: {line.strip()[:100]}", fm_lines + ln)


def read_repair_rounds(path: Path) -> dict[str, int]:
    """Parse .brain/state/repair-rounds. Current format: one `<gate>=<n>`
    line per gate. Legacy single-integer files (written before the per-gate
    fix) are tolerated: the count applies to both gates, so an over-limit
    legacy count still stops. Anything unreadable starts at zero."""
    counts = {gate: 0 for gate in GATES}
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return counts
    if not text:
        return counts
    if "=" not in text:
        try:
            legacy = max(0, int(text.splitlines()[0].strip()))
        except ValueError:
            return counts
        return {gate: legacy for gate in GATES}
    for line in text.splitlines():
        gate, _, raw = line.partition("=")
        gate = gate.strip()
        if gate in counts:
            try:
                counts[gate] = max(0, int(raw.strip() or "0"))
            except ValueError:
                pass
    return counts


def record_repair_round(root: Path, passed: bool, gate: str = GATE_LINT) -> str | None:
    """Count consecutive failing runs PER GATE; return the message to print.

    The old skill rule counted `doctor --strict` receipts, which missed the
    observed failure loop (`lint --verify` writes no receipt) and died at
    compaction with the in-memory count. This counter lives on disk at
    .brain/state/repair-rounds. Since the per-gate fix, a passing run resets
    only its own gate and each gate stops at its own MAX_REPAIR_ROUNDS — the
    old shared counter never reached the limit when a lint pass alternated
    with a doctor-strict failure. Both scripts call this one helper so the
    limit exists exactly once.

    ponytail: single-file counter, no history — it cannot answer "which runs
    failed"; the receipts under .brain/audit/runs/ still hold per-run detail
    for --strict. Upgrade path: a JSONL log beside the counter there.
    """
    brain = root / ".brain"
    if not brain.is_dir():
        return None  # no brain to repair; the loop has not started
    path = root / REPAIR_ROUNDS_REL
    counts = read_repair_rounds(path)
    rounds = 0 if passed else counts.get(gate, 0) + 1
    counts[gate] = rounds
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(f"{g}={counts[g]}\n" for g in GATES), encoding="utf-8")
    except OSError:
        pass  # best effort: an unwritable state dir restarts the count at 0
    if passed:
        return None
    if rounds > MAX_REPAIR_ROUNDS:
        return (f"repair limit exceeded ({rounds} > {MAX_REPAIR_ROUNDS}) — "
                "STOP and write the honest report")
    if rounds == MAX_REPAIR_ROUNDS:
        return f"repair round {rounds}/{MAX_REPAIR_ROUNDS} — STOP and write the honest report"
    return f"repair round {rounds}/{MAX_REPAIR_ROUNDS}"


def build_report(root: Path, citation_state: dict | None = None) -> tuple[int, dict]:
    root = root.expanduser().resolve()
    brain = root / ".brain"
    issues: list[dict] = []
    if not brain.exists():
        add(issues, "error", "missing_brain", brain, root,
            f"no .brain directory at {brain} — {INIT_HINT}")
    else:
        check_required(root, brain, issues)
        check_wikilinks(root, brain, issues)
        check_sources(root, brain, issues)
        check_index(root, brain, issues)
        check_brief_task_checklist(root, brain, issues)
        check_nested_graphify_output(root, issues)
        check_session_brief_staleness(root, brain, issues)
        check_audit(root, brain, issues)
        check_evidence_aging(root, brain, issues)
        check_short_wiki_pages(root, brain, issues)
        check_graph_report(root, issues)
        check_frontmatter_schema(root, brain, issues)
        check_contradictions(root, brain, issues)
        verification = load_verification(brain)
        state = citation_state if citation_state is not None else {}
        check_citations(root, brain, issues, state)
        check_stale_citations(root, brain, issues, state, verification)
        check_rationale_sources(root, brain, issues)
        check_all_clear_claims(root, brain, issues, verification)
        check_volatile_numbers(root, brain, issues)
        check_brain_secrets(root, brain, issues)

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


def reindex(root: Path) -> None:
    """Regenerate wiki/index.md from the real page tree (KD-05 fix path)."""
    from scaffold_brain import generate_wiki_index, INDEX_HEADER_PREFIX  # type: ignore

    index = root / ".brain" / "wiki" / "index.md"
    title = ""
    if index.exists():
        first = read(index).splitlines()[:1]
        if first and first[0].startswith(INDEX_HEADER_PREFIX + " - "):
            title = first[0][len(INDEX_HEADER_PREFIX) + 3:]
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text(generate_wiki_index(root / ".brain" / "wiki", title), encoding="utf-8")
    print(f"reindexed: {rel(index, root)}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lint a project brain.")
    parser.add_argument("project_root")
    parser.add_argument("--json", action="store_true", dest="as_json", help="print machine-readable JSON")
    parser.add_argument("--reindex", action="store_true",
                        help="regenerate wiki/index.md from the real page list before linting")
    parser.add_argument("--verify", action="store_true",
                        help="re-check citations and record SHA-256 stamps in .brain/verification.json (clean pages only)")
    return parser.parse_args(argv[1:])


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    root = Path(args.project_root).expanduser().resolve()
    if args.reindex:
        if not (root / ".brain").exists():
            print(f"no .brain directory at {root}", file=sys.stderr)
            return 2
        reindex(root)
    citation_state: dict = {}
    try:
        code, report = build_report(root, citation_state=citation_state)
    except VerificationCorruptError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    if args.verify and (root / ".brain").exists():
        write_verification(root, citation_state)
    if args.as_json:
        print(json.dumps(report, indent=2))
    else:
        print_human(report)
    note = record_repair_round(root, passed=code == 0, gate=GATE_LINT)
    if note:
        print(note, file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
