#!/usr/bin/env python3
"""Print project-brain status, availability checks, and health metrics."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import lint_brain as lb

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")

# Sub-scores at or above this are healthy; below it the doctor flags them so a
# caller cannot summarize a failing sub-score as success. Skill text quotes the
# same number — keep skills/brain/SKILL.md and references/brain-lifecycle.md
# consistent when changing this value.
HEALTH_REPAIR_THRESHOLD = 70


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def inventory_state(root: Path) -> dict | None:
    """Load .brain/inventory.json; None when absent, {"error": ...} when unusable."""
    path = root / ".brain" / "inventory.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return {"error": f"corrupt JSON: {exc}"}
    if not isinstance(data, dict) or "completion" not in data or "summary" not in data:
        return {"error": "missing completion/summary keys — rerun inventory"}
    # Validate the nested fields coverage() and strict_gates() read, so a
    # partial or hand-edited inventory reports an inventory error instead of
    # raising KeyError mid-gate.
    completion = data.get("completion")
    summary = data.get("summary")
    weighted = completion.get("weighted_coverage") if isinstance(completion, dict) else None
    if (not isinstance(completion, dict)
            or not isinstance(completion.get("complete"), bool)
            or not isinstance(weighted, (int, float)) or isinstance(weighted, bool)
            or not isinstance(completion.get("core_uncovered"), list)
            or not isinstance(summary, dict)
            or not isinstance(summary.get("covered"), int) or isinstance(summary.get("covered"), bool)
            or not isinstance(summary.get("units"), int) or isinstance(summary.get("units"), bool)):
        return {"error": ("completion/summary missing required fields (complete, weighted_coverage, "
                          "core_uncovered, covered, units) — rerun `project-brain-inventory <root> inventory`")}
    return data


def page_sourced(fm: dict, text: str) -> bool:
    """>=1 frontmatter source entry or >=1 inline citation."""
    sources = fm.get("sources")
    if isinstance(sources, list) and any(str(s).strip() for s in sources):
        return True
    if isinstance(sources, str) and sources.strip():
        return True
    return bool(lb.CITATION_RE.search(text))


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
# Unit names shown per section when the inventory is stale (added/removed each
# truncate at this many, with an ellipsis when more exist).
INVENTORY_PREVIEW_UNITS = 5
# git status -z uses NUL as the record separator (one record per modified file,
# two consecutive records for renames: new path, then old path).
STATUS_RECORD_SEP = "\0"


def _load_manifest_keys(root: Path) -> set[str]:
    """Load manifest keys from graphify-out/manifest.json, or empty set on failure.

    Reads the manifest only when called (lazy); catches OSError and ValueError
    (JSON decode errors); returns empty set for non-dict JSON.
    """
    manifest_path = root / GRAPH_MANIFEST_REL
    try:
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(manifest_data, dict):
            return set(manifest_data.keys())
        return set()
    except (OSError, ValueError):
        return set()


def _parse_status_z(output: str) -> tuple[list[str], list[str]]:
    """Parse git status --porcelain -z output into current and origin paths.

    Returns (current_paths, origin_paths). For renames/copies (R or C in either
    status column), the next record is the origin path; for all others, the path
    after "XY " is a current path. Renames/copies appear in origin_paths AND
    current_paths (the destination).
    """
    records = [r for r in output.split(STATUS_RECORD_SEP) if r]
    current_paths: list[str] = []
    origin_paths: list[str] = []
    i = 0
    while i < len(records):
        rec = records[i]
        if len(rec) < 2:
            i += 1
            continue
        # R or C in either index (rec[0]) or worktree (rec[1]) column
        if rec[0] in "RC" or rec[1] in "RC":
            # Rename/copy: rec[3:] is the new path, next record is the origin
            current_paths.append(rec[3:] if len(rec) > 3 else "")
            if i + 1 < len(records):
                origin_paths.append(records[i + 1])
                i += 2  # Skip the origin record
            else:
                i += 1
        else:
            # Normal entry: "XY path"
            current_paths.append(rec[3:] if len(rec) > 3 else "")
            i += 1
    return current_paths, origin_paths


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

    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=5
        ).stdout.strip()
        # Dirty check: include untracked source files (they are indexed by the
        # graph), but exclude .brain/ and graphify-out/ which never affect it.
        # Use -z for NUL-separated records to handle paths with spaces/non-ASCII.
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "-z", "--", *_DIRTY_EXCLUDES],
            cwd=root, capture_output=True, text=True, timeout=5
        ).stdout
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        return "stale", f"git unavailable: {exc}"
    if not head:
        return "stale", "not a git repository"
    if not head.startswith(recorded):
        return "stale", f"graph built at {recorded}, HEAD is {head[:len(recorded)]}"
    if dirty:
        # Parse NUL-separated records. Git emits "XY path\0" for each modification,
        # plus "XY new_path\0old_path\0" for renames/copies (R or C in either index
        # or worktree status column). Collect current paths and origin paths separately.
        current_paths, origin_paths = _parse_status_z(dirty)

        visible_paths = current_paths[:MAX_DIRTY_LINES]
        omitted_count = len(current_paths) - len(visible_paths)

        # ponytail: compares mtime for existing files; for deletions (including
        # rename origins) consults manifest lazily (only when first deleted path
        # found). Upgrade path: Graphify's own change detection.
        report_mtime = report.stat().st_mtime
        any_newer_than_report = False
        manifest_keys: set[str] | None = None  # Lazy load

        # Check current paths (new files, edits, rename/copy destinations)
        for path_str in current_paths:
            if not path_str:
                continue
            path = root / path_str
            if path.exists():
                if path.stat().st_mtime > report_mtime:
                    any_newer_than_report = True
                    break
            else:
                # Deleted file: check manifest (load on first deletion only)
                if manifest_keys is None:
                    manifest_keys = _load_manifest_keys(root)
                if manifest_keys:
                    path_posix = path.relative_to(root).as_posix()
                    path_abs = str(path.resolve())
                    if path_posix in manifest_keys or path_abs in manifest_keys:
                        any_newer_than_report = True
                        break

        # Check origin paths (renames and copies): if the origin no longer exists
        # and was in the manifest, the graph is stale; if it still exists (copy),
        # compare by mtime.
        if not any_newer_than_report:
            for path_str in origin_paths:
                if not path_str:
                    continue
                path = root / path_str
                if path.exists():
                    if path.stat().st_mtime > report_mtime:
                        any_newer_than_report = True
                        break
                else:
                    # Origin no longer exists (rename): check manifest
                    if manifest_keys is None:
                        manifest_keys = _load_manifest_keys(root)
                    if manifest_keys:
                        path_posix = path.relative_to(root).as_posix()
                        path_abs = str(path.resolve())
                        if path_posix in manifest_keys or path_abs in manifest_keys:
                            any_newer_than_report = True
                            break

        if not any_newer_than_report:
            # All dirty files predate the report - graph was rebuilt after edits
            return "fresh", f"graph matches {recorded}"

        lines_str = "; ".join(visible_paths)
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
    # Weights: title/heading=2, type=1, wikilink=1, indexed=2, status=1.
    weights = [2, 1, 1, 2, 1]
    total_points = 0
    max_points = 0
    full = 0
    for p in pages:
        text = read(p)
        fm = extract_frontmatter(text)
        structural = [
            bool(fm.get("title") or re.search(r"^#\s+", text, re.M)),
            bool(fm.get("type")),
            bool(WIKILINK_RE.search(text)),
            page_in_index(p, root, idx),
            bool(fm.get("status")),
        ]
        total_points += sum(w for w, c in zip(weights, structural) if c)
        max_points += sum(weights)
        if not all(structural):
            continue
        # KD-12 / brain-health-metrics: a page is complete only when an ACTIVE
        # page also has >=1 source (frontmatter entry or inline citation);
        # draft pages are exempt from the source requirement.
        if str(fm.get("status", "")).lower() != "draft" and not page_sourced(fm, text):
            continue
        full += 1
    # The health score is the documented metric: the percentage of pages that
    # have every required field INCLUDING the source requirement. The weighted
    # number is a structure-only measure and is reported separately in the
    # note, so an active page without a source can never score as complete.
    score = round(full / len(pages) * 100)
    structural_pct = round(total_points / max_points * 100) if max_points else 0
    return score, (f"{full}/{len(pages)} pages fully formed (active pages need a source "
                   f"or citation; structure-only weighted score {structural_pct}%)")


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
    """KD-12: coverage comes from the script-derived inventory — never 100 on
    absent data. No inventory → 0 with the command that produces it."""
    inv = inventory_state(root)
    if inv is None:
        return 0, "no inventory — run `project-brain-inventory <root> inventory`"
    if inv.get("error"):
        return 0, f"inventory unreadable ({inv['error']})"
    c, s = inv["completion"], inv["summary"]
    pct = round(c["weighted_coverage"] * 100)
    return pct, (f"{s['covered']}/{s['units']} units covered, weighted {pct}% "
                 f"(core uncovered: {len(c['core_uncovered'])})")


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
    follows the canonical wiki_<slug> convention (MemPalace's own underscore
    normalization) introduced in 0.9.3. Hyphenated wiki-<slug> names from older
    versions are recognized as legacy and get a migration hint.
    """
    # ponytail: file-based only; MCP drawer count requires the agent session
    try:
        from scaffold_brain import (  # type: ignore
            LEGACY_WIKI_WING_PREFIX,
            WIKI_WING_PREFIX,
            normalize_wing_slug,
            resolve_wing_name,
        )
    except Exception as exc:
        return "warning", f"unable to load scaffold_brain: {exc}"

    wing, source = resolve_wing_name(root)
    if source == "derived":
        return "warning", f"wing={wing} (derived — .brain/CLAUDE.md missing mempalace_wing)"

    # Cross-check the other declaration source: root CLAUDE.md and
    # .brain/CLAUDE.md disagreeing on mempalace_wing is a conflict that no
    # canonical prefix can paper over — report it before any "ok".
    root_claude = root / "CLAUDE.md"
    brain_claude = root / ".brain" / "CLAUDE.md"
    other_source = ".brain/CLAUDE.md" if source == "CLAUDE.md" else "CLAUDE.md"
    other_file = brain_claude if source == "CLAUDE.md" else root_claude
    other_wing: str | None = None
    if other_file.exists():
        m2 = re.search(r"mempalace_wing:\s*(\S+)", other_file.read_text(encoding="utf-8"))
        if m2:
            other_wing = m2.group(1)
    wing_conflict = other_wing is not None and other_wing != wing

    if wing.startswith(WIKI_WING_PREFIX):
        if wing_conflict:
            return "warning", (
                f"wing conflict: {source} declares {wing!r} but {other_source} declares "
                f"{other_wing!r} — mempalace_wing must be identical in both files; "
                f"update {other_source} to match {source}"
            )
        return "ok", f"wing={wing} ({source})"
    other_declares = other_wing is not None
    if wing.startswith(LEGACY_WIKI_WING_PREFIX):
        slug_part = normalize_wing_slug(wing[len(LEGACY_WIKI_WING_PREFIX):])
        prefix_note = (
            f"uses the legacy hyphenated convention; MemPalace normalizes '-' to '_', "
            f"so directory-derived and diary wings use '{WIKI_WING_PREFIX}'-style "
            "underscore names instead"
        )
        target = f"{WIKI_WING_PREFIX}{slug_part}"
    else:
        prefix_note = f"does not start with '{WIKI_WING_PREFIX}'"
        target = f"a '{WIKI_WING_PREFIX}'-prefixed name"
    msg = (
        f"wing={wing} ({source}) {prefix_note}. "
        f"To migrate: use mempalace_update_drawer to move drawers to {target}, "
        f"then update mempalace_wing in {source}"
    )
    if other_declares:
        msg += f" and change {other_source} to match"
    msg += " — re-scaffolding alone preserves the old wing name"
    return "warning", msg


def health_data(root: Path) -> dict:
    c, c_note = completeness(root)
    f, f_note = freshness(root)
    cov, cov_note = coverage(root)
    mem, mem_note = memory_sync(root)
    return {
        "Completeness": {"score": c, "note": c_note},
        "Freshness": {"score": f, "note": f_note},
        "Coverage": {"score": cov, "note": cov_note},
        "Memory sync": {"score": mem, "note": mem_note, "estimated": True},
    }


def print_health(root: Path) -> dict:
    data = health_data(root)
    total = round(sum(item["score"] for item in data.values()) / len(data))
    print()
    print(f"Project Brain Health: {total}/100")
    for label, item in data.items():
        flag = (
            "  ⚠ BELOW REPAIR THRESHOLD — report or repair, do not summarize as success"
            if item["score"] < HEALTH_REPAIR_THRESHOLD
            else ""
        )
        est = " [estimated from logs]" if item.get("estimated") else ""
        print(f"  {label:13}{item['score']:4}/100  ({item['note']}){est}{flag}")
    print(
        f"  (scores below {HEALTH_REPAIR_THRESHOLD} require repair or an explicit explanation; "
        "see Self-correction scan in the brain skill)"
    )
    return data


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print project-brain status, availability checks, and health metrics.")
    parser.add_argument("project_root", nargs="?", default=None)
    parser.add_argument("--strict", action="store_true",
                        help="hard gate: exit nonzero unless every gate passes (lint errors 0, "
                             "inventory complete); writes one receipt per run to .brain/audit/runs/")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="print machine-readable JSON instead of human text")
    return parser.parse_args(argv[1:])


def strict_status(gates: dict) -> str:
    if any(g["status"] == "could-not-run" for g in gates.values()):
        return "partial"
    if any(g["status"] == "failed" for g in gates.values()):
        return "completed-with-findings"
    return "passed-for-scope"


def inventory_fresh(root: Path, inv: dict) -> tuple[bool, str]:
    """True when the saved inventory still certifies the current project.

    completion.complete was computed for the unit set AND the wiki content at
    inventory time. Two things can make the saved value stale:
    - a core unit added or removed afterwards (unit-path set changes), or
    - wiki page content edited with no path change (e.g. a page's only
      citation removed): the saved completion must not certify coverage it
      was not computed from, so the inventory binds itself to a wiki content
      digest and any content change forces a rerun."""
    import brain_inventory as bi  # local: spawns git subprocesses only when needed

    saved = inv.get("units")
    if not isinstance(saved, list) or not all(
            isinstance(u, dict) and "path" in u for u in saved):
        return False, ("inventory.json has no usable units list — "
                       "rerun `project-brain-inventory <root> inventory`")
    try:
        policy, _policy_path = bi.load_policy()
        current_units, _source, _commit = bi.list_units(root, policy)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        return False, f"cannot verify inventory freshness against current units: {exc}"
    saved_paths = {str(u["path"]) for u in saved}
    current_paths = {str(u["path"]) for u in current_units}
    if saved_paths != current_paths:
        added = sorted(current_paths - saved_paths)
        removed = sorted(saved_paths - current_paths)
        detail = (f"stale inventory: {len(added)} unit(s) added, {len(removed)} removed "
                  "since the last inventory run — rerun "
                  "`project-brain-inventory <root> inventory` and re-check coverage")
        if added:
            detail += ("; added: " + ", ".join(added[:INVENTORY_PREVIEW_UNITS])
                       + ("…" if len(added) > INVENTORY_PREVIEW_UNITS else ""))
        if removed:
            detail += ("; removed: " + ", ".join(removed[:INVENTORY_PREVIEW_UNITS])
                       + ("…" if len(removed) > INVENTORY_PREVIEW_UNITS else ""))
        return False, detail
    saved_wiki_sha = inv.get("wiki_content_sha256")
    if not isinstance(saved_wiki_sha, str) or not saved_wiki_sha:
        return False, ("inventory predates wiki-content binding — the saved completion "
                       "cannot be tied to the current wiki pages; rerun "
                       "`project-brain-inventory <root> inventory` and re-check coverage")
    try:
        current_wiki_sha = bi.wiki_content_sha256(root / ".brain")
    except OSError as exc:
        return False, f"cannot verify inventory freshness against current wiki content: {exc}"
    if saved_wiki_sha != current_wiki_sha:
        return False, ("wiki content changed since the inventory run (same unit paths, "
                       "edited pages) — the saved completion no longer certifies the "
                       "current coverage; rerun "
                       "`project-brain-inventory <root> inventory` and re-check coverage")
    return True, ""


def strict_gates(root: Path) -> dict:
    """KD-13: the hard gate. A gate is passed/failed/could-not-run; --strict
    exits 0 only when every gate passed. Lint errors cover citation drift,
    staleness, forbidden all-clears, secrets, and index dupes in one gate."""
    gates: dict[str, dict] = {}
    try:
        code, report = lb.build_report(root)
        error_categories = sorted({i["category"] for i in report["issues"] if i["severity"] == "error"})
        gates["lint_errors"] = {
            "status": "passed" if code == 0 else "failed",
            "detail": report["summary"],
            "error_categories": error_categories,
        }
    except lb.VerificationCorruptError as exc:
        gates["lint_errors"] = {"status": "failed",
                                "detail": f"verification.json corrupt: {exc}",
                                "error_categories": ["verification_corrupt"]}
    inv = inventory_state(root)
    if inv is None:
        gates["coverage"] = {"status": "could-not-run",
                             "detail": "inventory.json missing — run `project-brain-inventory <root> inventory`"}
    elif inv.get("error"):
        gates["coverage"] = {"status": "could-not-run", "detail": inv["error"]}
    else:
        fresh, fresh_detail = inventory_fresh(root, inv)
        if not fresh:
            gates["coverage"] = {"status": "could-not-run", "detail": fresh_detail}
        else:
            gates["coverage"] = {"status": "passed" if inv["completion"]["complete"] else "failed",
                                 "detail": inv["completion"]}
    return gates


def write_receipt(root: Path, brain: Path, gates: dict, health: dict) -> Path:
    """KD-13: one receipt per --strict run at .brain/audit/runs/<UTC-ts>/run.json."""
    inv = inventory_state(root)
    from scaffold_brain import plugin_identity  # type: ignore
    version, _plugin_root = plugin_identity()
    receipt = {
        "timestamp": now_iso(),
        "strict": True,
        "status": strict_status(gates),
        "target_commit": lb.git_head(root),
        "plugin": {"name": "project-brain", "version": version},
        "inventory_policy": inv.get("policy") if isinstance(inv, dict) else None,
        "unit_counts": inv.get("summary") if isinstance(inv, dict) else None,
        "health": health,
        "lint": gates.get("lint_errors", {}).get("detail"),
        "gates": gates,
    }
    run_dir = brain / "audit" / "runs" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "run.json"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def run_json_mode(root: Path, brain: Path, strict: bool) -> int:
    payload = {
        "project_root": str(root),
        "brain_exists": brain.exists(),
        "health": health_data(root) if brain.exists() else None,
        "inventory": inventory_state(root),
    }
    if strict:
        if not brain.exists():
            payload["gates"] = {
                "lint_errors": {"status": "could-not-run", "detail": "no .brain directory"},
                "coverage": {"status": "could-not-run", "detail": "no .brain directory"},
            }
        else:
            payload["gates"] = strict_gates(root)
            write_receipt(root, brain, payload["gates"], payload["health"] or {})
            note = lb.record_repair_round(root, strict_status(payload["gates"]) == "passed-for-scope",
                                          gate=lb.GATE_DOCTOR_STRICT)
            if note:
                print(note, file=sys.stderr)
        payload["status"] = strict_status(payload["gates"])
    print(json.dumps(payload, indent=2))
    if strict:
        return 0 if payload["status"] == "passed-for-scope" else 1
    return 0


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    root = Path(args.project_root).expanduser().resolve() if args.project_root else Path.cwd()
    brain = root / ".brain"
    if args.as_json:
        return run_json_mode(root, brain, args.strict)
    plugins = read_enabled_plugins()

    from scaffold_brain import plugin_identity  # type: ignore

    version, plugin_root_resolved = plugin_identity()
    print(f"Project Brain plugin {version} (plugin root: {plugin_root_resolved})")
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
        print("✗ graphify CLI not on PATH (only the fallback builder — primary is the /graphify skill)")
        print('  CLI install: uv tool install graphifyy')

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
        print(f"⚠ graphify stale: {freshness_note} — rebuild via the /graphify skill (primary); "
              "CLI fallback: `graphify .` (set GRAPHIFY_BACKEND=none when no API access)")

    if brain.exists():
        print_health(root)
        severity, wing_note = mempalace_wing_check(root)
        glyph = {"ok": "✓", "warning": "⚠", "info": "ℹ"}.get(severity, "-")
        print(f"{glyph} MemPalace wing: {wing_note}")
        mempal_dir = os.environ.get("MEMPAL_DIR", "")
        mempal_points_here = False
        if mempal_dir:
            try:
                mempal_points_here = Path(mempal_dir).expanduser().resolve() == root
            except OSError:
                mempal_points_here = False
        # The stop-hook note is printed when it is actually relevant (MEMPAL_DIR
        # set, or the wing check just flagged something) rather than on every run.
        if mempal_dir or severity != "ok":
            print(
                "ℹ MemPalace note: its session stop hook re-mines MEMPAL_DIR without --wing "
                "(mining the project root into the directory-derived wing), so a wing with the "
                "project's normalized directory name can reappear after a reset. This is "
                "MemPalace's own hook behavior; never point the wiki wing at that name and "
                "never mine the project root into the wiki wing."
            )
            if mempal_points_here:
                print(
                    "⚠ MEMPAL_DIR is this project root — MemPalace's stop hook will mine it "
                    "into the directory-derived wing (normalized project name) on every session stop."
                )

        # KD-04: doctor prints the coverage work list from the inventory
        inv = inventory_state(root)
        if inv and not inv.get("error"):
            uncovered = [u for u in inv.get("units", [])
                         if u.get("status") == "uncovered" and u.get("tier") in ("core", "important")]
            if uncovered:
                print()
                print("Coverage work list (uncovered core/important units):")
                for u in uncovered:
                    print(f"  [{u['tier']}] {u['path']}")

    if args.strict:
        if not brain.exists():
            print("strict: no .brain directory — gates could not run", file=sys.stderr)
            return 1
        gates = strict_gates(root)
        path = write_receipt(root, brain, gates, health_data(root))
        print()
        for name, g in gates.items():
            print(f"strict gate {name}: {g['status']}")
        print(f"strict status: {strict_status(gates)}")
        print(f"receipt: {rel(path, root)}")
        passed = all(g["status"] == "passed" for g in gates.values())
        note = lb.record_repair_round(root, passed, gate=lb.GATE_DOCTOR_STRICT)
        if note:
            print(note, file=sys.stderr)
        return 0 if passed else 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
