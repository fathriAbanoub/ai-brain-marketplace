#!/usr/bin/env python3
"""Scaffold a layered project brain.

Usage:
    scaffold_brain.py <project-root> "<Project Name>" [--force]
"""

from __future__ import annotations

import argparse
import json
import sys
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable


# Wing naming convention — MemPalace's own. mempalace.config.normalize_wing_name
# lowercases and maps '-' and ' ' to '_' for directory-derived wings, and its
# hooks derive diary wings as wing_<slug> with the same underscore rule. A
# hyphenated plugin wing therefore creates a twin wing per project (the
# data-loss trigger behind the reset-skill empty-wing bug), so this plugin
# generates underscore slugs in MemPalace's own convention.
WING_SEPARATOR = "_"
WIKI_WING_PREFIX = "wiki" + WING_SEPARATOR
# ponytail: pre-0.9.3 brains carry hyphenated wings; kept so doctor/reset can
# recognize and migrate them. Upgrade path: drop once no hyphenated wings exist.
LEGACY_WIKI_WING_PREFIX = "wiki-"
BRAIN_DIARY_PREFIX = "brain" + WING_SEPARATOR
FALLBACK_WING_NAME = "project" + WING_SEPARATOR + "brain"
# Since 0.9.4, NEW canonical wiki wings carry a UTC timestamp:
#   wiki_<project-slug>_<YYYYmmdd'T'HHMMSS'Z'>
# Tunnels and hallways can survive drawer deletion, so reusing a bare
# wiki_<slug> name lets new content inherit stale graph associations from an
# older wing. The timestamp makes the identity unique per creation. Legacy
# names stay supported and are never deleted or renamed automatically.
WING_TS_FORMAT = "%Y%m%dT%H%M%SZ"


def normalize_wing_slug(raw: str) -> str:
    """Normalize a name the same way mempalace.config.normalize_wing_name does:
    lowercase; '-' and ' ' (and any other separator) become '_', runs collapse,
    leading/trailing separators stripped."""
    normalized = raw.strip().lower()
    normalized = re.sub(r"[^a-z0-9._]+", WING_SEPARATOR, normalized)
    normalized = re.sub(rf"{re.escape(WING_SEPARATOR)}+", WING_SEPARATOR, normalized)
    return normalized.strip("._")


def sanitize_wing_name(raw: str) -> str:
    normalized = normalize_wing_slug(raw)
    return normalized or FALLBACK_WING_NAME


def diary_wing_for_agent(agent: str) -> str:
    """The wing mempalace_diary_write uses for `agent` when no wing is passed.

    Verified against MemPalace 3.11.0 mcp_server/tools_diary.py: the agent name
    is sanitized + lowercased and only ' ' is replaced with '_', so hyphens in
    the agent name survive into the wing. Underscore-based agent names (this
    plugin's convention) keep write and read symmetric with no surprises.
    """
    return "wing_" + agent.strip().lower().replace(" ", "_")


def plugin_identity() -> tuple[str, str]:
    """Return (version, plugin_root) from the plugin manifest.

    Lets init/doctor print their own version so skill text and scripts from
    different installed plugin versions are visibly distinguishable.
    """
    plugin_root = Path(__file__).resolve().parent.parent
    manifest = plugin_root / ".claude-plugin" / "plugin.json"
    version = "unknown"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        version = str(data.get("version", version))
    except (OSError, ValueError):
        pass
    return version, str(plugin_root)


def wiki_wing_name(title: str) -> str:
    """Legacy (pre-0.9.4) wiki wing name: wiki_<sanitized-title>.

    Kept for recognizing/recording legacy wings. New brains must use
    generate_wiki_wing_name() instead — a bare wiki_<slug> name can collide
    with surviving tunnels/hallways of an older wing after a reset.
    """
    return WIKI_WING_PREFIX + sanitize_wing_name(title)


def generate_wiki_wing_name(
    slug: str,
    taken: Iterable[str] = (),
    now: datetime | None = None,
) -> str:
    """Generate a unique timestamped wiki wing name for a NEW brain.

    Format: wiki_<slug>_<UTC-timestamp> (e.g. wiki_demo_app_20261026T164600Z).
    Collisions (simultaneous creation, a name already present in the palace
    or in surviving tunnels/hallways, or the directory-derived wing) are
    resolved deterministically: first by microsecond precision, then by a
    numeric suffix _2, _3, ... so the same inputs always yield the same name
    and an existing identity is never silently reused.

    `taken` must list every wing name the new identity must avoid: existing
    palace wings, stale graph-record wings, the directory-derived wing, and
    the diary wing. The caller (agent flow) obtains the first two from
    mempalace_list_wings / tunnel+hallway listings before init.
    """
    base_slug = sanitize_wing_name(slug)
    moment = now.astimezone(timezone.utc) if (now and now.tzinfo) else (
        now if now else datetime.now(timezone.utc)
    )
    candidates = [WIKI_WING_PREFIX + base_slug + WING_SEPARATOR + moment.strftime(WING_TS_FORMAT)]
    candidates.append(
        WIKI_WING_PREFIX + base_slug + WING_SEPARATOR + moment.strftime("%Y%m%dT%H%M%S%fZ")  # higher precision
    )
    suffix = 2
    while True:
        candidates.append(
            WIKI_WING_PREFIX + base_slug + WING_SEPARATOR
            + moment.strftime(WING_TS_FORMAT) + WING_SEPARATOR + str(suffix)
        )
        taken_set = {t for t in taken if t}
        for candidate in candidates:
            if candidate not in taken_set:
                return candidate
        suffix += 1
        if suffix > 1000:
            raise ValueError("cannot generate a unique wiki wing name; pass an explicit name")


def ensure_graphifyignore(project_root: Path) -> None:
    """Ensure .graphifyignore excludes the brain dirs and sensitive paths (KD-15).

    Idempotent: only appends entries that are missing (compared after
    stripping whitespace and a trailing slash so equivalent entries written
    by older scaffold runs are not duplicated); never removes or rewrites
    user entries. Adds a leading newline before new entries if the file does
    not end with one.
    """
    ignore_path = project_root / ".graphifyignore"
    # Required exclusions managed here: brain dirs + default sensitive-path
    # set. User entries beyond these are left untouched.
    required = {
        ".brain/", "graphify-out/",
        ".env", ".env.*", "*.pem", "*.key", "id_rsa*", "secrets/", "credentials*.json",
    }

    existing_text = ignore_path.read_text(encoding="utf-8") if ignore_path.exists() else ""
    # Normalise for comparison: strip whitespace + trailing slash.
    existing_normalised = {line.strip().rstrip("/") for line in existing_text.splitlines()}

    missing = [r for r in sorted(required) if r.rstrip("/") not in existing_normalised]
    if not missing:
        return

    with open(ignore_path, "a", encoding="utf-8") as f:
        if existing_text and not existing_text.endswith("\n"):
            f.write("\n")
        for line in missing:
            f.write(line + "\n")


INDEX_HEADER_PREFIX = "# Project Brain Index"
# Section order for the script-generated wiki index. Pages directly under
# wiki/ (like open-questions.md) are listed under "Start here".
INDEX_SECTION_ORDER = [
    "architecture", "decisions", "concepts", "entities", "sources", "syntheses",
]
INDEX_SECTION_TITLES = {
    "architecture": "Architecture",
    "decisions": "Decisions",
    "concepts": "Concepts",
    "entities": "Entities",
    "sources": "Sources",
    "syntheses": "Syntheses",
}


def generate_wiki_index(wiki: Path, title: str = "") -> str:
    """Generate wiki/index.md content from the REAL page list on disk.

    Single source of truth for the index: scaffold writes it, and
    `project-brain-lint <root> --reindex` regenerates it the same way, so the
    index can never disagree with the page tree at generation time. lint
    verifies the invariants (every eligible page exactly once, no entry
    pointing at a missing page).
    """
    pages = [p for p in sorted(wiki.rglob("*.md")) if p.name != "index.md"]
    sections: dict[str, list[Path]] = {}
    for p in pages:
        rel = p.relative_to(wiki)
        section = rel.parts[0] if len(rel.parts) > 1 else ""
        sections.setdefault(section, []).append(p)
    header = INDEX_HEADER_PREFIX + (f" - {title}" if title else "")
    lines = [
        header,
        "",
        "> Catalog of durable project knowledge. Every wiki page appears here exactly once. "
        "Script-generated: regenerate with `project-brain-lint <project-root> --reindex` after adding pages.",
        "",
    ]
    top = sections.get("", [])
    if top:
        lines.append("## Start here")
        lines.append("")
        for p in top:
            lines.append(f"- [[{p.relative_to(wiki).with_suffix('')}]]")
        lines.append("")
    for key in INDEX_SECTION_ORDER:
        entries = sections.get(key)
        if not entries:
            continue
        lines.append(f"## {INDEX_SECTION_TITLES[key]}")
        lines.append("")
        for p in entries:
            lines.append(f"- [[{p.relative_to(wiki).with_suffix('')}]]")
        lines.append("")
    # Unknown future sections are still listed so no page silently vanishes.
    for key in sorted(k for k in sections if k and k not in INDEX_SECTION_ORDER):
        lines.append(f"## {key}")
        lines.append("")
        for p in sections[key]:
            lines.append(f"- [[{p.relative_to(wiki).with_suffix('')}]]")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_generated_index(brain: Path, project_root: Path, title: str, force: bool = False) -> None:
    """Write the script-generated index.md (only when missing, or on --force)."""
    index_path = brain / "wiki" / "index.md"
    if index_path.exists() and not force:
        print(f"skipped (exists): {index_path.relative_to(project_root)}")
        return
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(generate_wiki_index(brain / "wiki", title), encoding="utf-8")
    print(f"{'updated' if index_path.exists() else 'wrote'}: {index_path.relative_to(project_root)}")


def resolve_wing_name(root: Path) -> tuple[str, str]:
    """Resolve MemPalace wing name from project root. Returns (wing, source)."""
    claude_md = root / "CLAUDE.md"
    if claude_md.exists():
        text = claude_md.read_text(encoding="utf-8")
        m = re.search(r"mempalace_wing:\s*(\S+)", text)
        if m:
            return m.group(1), "CLAUDE.md"
    brain_claude = root / ".brain" / "CLAUDE.md"
    if brain_claude.exists():
        text = brain_claude.read_text(encoding="utf-8")
        m = re.search(r"mempalace_wing:\s*(\S+)", text)
        if m:
            return m.group(1), ".brain/CLAUDE.md"
    wing = sanitize_wing_name(root.name)
    return wing, "derived"


class MempalaceUnavailable(Exception):
    """Raised when MemPalace MCP is unavailable."""
    pass


class MempalaceBridge:
    """Simple bridge to MemPalace MCP client."""

    def __init__(self) -> None:
        raise MempalaceUnavailable("MempalaceBridge requires MCP client - use doctor MCP mode")


def collect_mempalace_drawers(client, wing: str) -> tuple[list[str], list[str]]:
    """Collect rooms and drawers from MemPalace wing."""
    raise MempalaceUnavailable("collect_mempalace_drawers requires MCP client")


def is_under(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def protected_path(path: Path, brain: Path) -> bool:
    protected = [
        brain / "raw",
        brain / "wiki" / "sources",
        brain / "log",
        brain / "audit",
    ]
    return any(path == p or is_under(path, p) for p in protected)


def write_template(path: Path, content: str, root: Path, brain: Path, force: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    label = path.relative_to(root) if is_under(path, root) else path
    already_existed = path.exists()
    if already_existed and not force:
        print(f"skipped (exists): {label}")
        return
    if already_existed and force and protected_path(path, brain):
        print(f"skipped protected (exists): {label}")
        return
    path.write_text(content, encoding="utf-8")
    print(f"{'updated' if already_existed else 'wrote'}: {label}")


def touch_marker(path: Path, root: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("", encoding="utf-8")
        print(f"wrote: {path.relative_to(root)}")


def append_log(brain: Path, op: str, title: str, bullets: list[str]) -> None:
    today = date.today()
    compact = today.strftime("%Y%m%d")
    iso = today.isoformat()
    now = datetime.now().strftime("%H:%M")
    log_path = brain / "log" / f"{compact}.md"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if not log_path.exists():
        log_path.write_text(f"# {iso}\n\n", encoding="utf-8")
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"## [{now}] {op} | {title}\n")
        for bullet in bullets:
            f.write(f"- {bullet}\n")
        f.write("\n")


def init_wiki_ledger(project_root: Path) -> None:
    """Create the wiki ledger (.brain/state/wiki.git) with a best-effort
    baseline snapshot. git missing -> warn and continue: the ledger is a
    safety net, never a requirement. The user's .gitignore is never edited;
    a one-line note prints when the outer repo could track the ledger."""
    try:
        import wiki_ledger
    except ImportError:  # pragma: no cover — ledger ships in the same dir
        return
    try:
        ledger = wiki_ledger.WikiLedger(project_root)
        ledger.init_ledger()
        committed, short, _detail = ledger.snapshot(
            wiki_ledger.BASELINE_SNAPSHOT_MESSAGE)
        detail = f"baseline snapshot {short}" if committed else "clean"
        print(f"  Ledger: {wiki_ledger.LEDGER_GIT_DIR_REL} ({detail})")
    except wiki_ledger.GitMissing:
        print("  Ledger: not created — git is missing (install git to enable "
              "wiki page history)")
    except wiki_ledger.LedgerError as exc:
        print(f"  Ledger: not created ({exc})")
    note = wiki_ledger.note_if_outer_repo_could_track_ledger(project_root)
    if note:
        print(f"  {note}")


def merge_root_claude(project_root: Path, snippet: str) -> None:
    claude_md = project_root / "CLAUDE.md"
    marked = f"<!-- project-brain:begin -->\n{snippet.strip()}\n<!-- project-brain:end -->\n"
    if claude_md.exists():
        text = claude_md.read_text(encoding="utf-8")
        if "<!-- project-brain:begin -->" in text:
            print("brain snippet already present in CLAUDE.md")
            return
        with claude_md.open("a", encoding="utf-8") as f:
            if not text.endswith("\n"):
                f.write("\n")
            f.write("\n" + marked)
        print("appended brain snippet to CLAUDE.md")
    else:
        claude_md.write_text(marked, encoding="utf-8")
        print("wrote: CLAUDE.md")


def scaffold(project_root: Path, title: str, force: bool = False, wing_override: str = "") -> None:
    project_root = project_root.expanduser()
    if not project_root.exists():
        sys.exit(f"Error: project root does not exist: {project_root}")
    if not project_root.is_dir():
        sys.exit(f"Error: project root is not a directory: {project_root}")

    project_root = project_root.resolve()
    brain = project_root / ".brain"
    today = date.today().isoformat()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Directory policy (KD-10): only directories that hold seeded content are
    # created here. Lifecycle directories (raw/articles, outputs/, memory/,
    # graph/, runbooks/, audit/) are created lazily by the step that fills
    # them, so an empty dir can never masquerade as a completed lifecycle step.
    dirs = [
        "wiki/architecture", "wiki/concepts", "wiki/decisions", "wiki/entities", "wiki/sources", "wiki/syntheses",
        "state", "tasks", "log",
    ]
    for rel in dirs:
        (brain / rel).mkdir(parents=True, exist_ok=True)

    installed_line = "MemPalace is already installed as a plugin. graphify is already installed as a CLI tool and skill. Do not reinstall either."

    slug = sanitize_wing_name(title)
    # Directory-derived wing (what MemPalace's own mining would use for this
    # root without --wing) — the new wiki wing must never collide with it.
    derived_wing = sanitize_wing_name(project_root.name)
    diary_agent = f"{BRAIN_DIARY_PREFIX}{slug}"  # Default for new brains

    # Reuse existing wing name and diary agent if .brain/CLAUDE.md already has them (idempotent re-scaffold).
    brain_claude = brain / "CLAUDE.md"
    recorded_wing = ""
    found_diary_agent = False
    if brain_claude.exists():
        existing_text = brain_claude.read_text(encoding="utf-8")
        for line in existing_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("mempalace_wing:"):
                existing_wing = stripped.split(":", 1)[1].strip()
                if existing_wing:
                    recorded_wing = existing_wing
            elif stripped.startswith("mempalace_diary_agent:"):
                existing_agent = stripped.split(":", 1)[1].strip()
                if existing_agent:
                    diary_agent = existing_agent
                    found_diary_agent = True
        # Fallback: recover from old diary sentence ONLY if no frontmatter agent
        if not found_diary_agent:
            diary_sentence_match = re.search(r"`mempalace_diary_write`\s+with\s+agent\s+`([^`]+)`", existing_text)
            if diary_sentence_match:
                diary_agent = diary_sentence_match.group(1)

    if recorded_wing:
        # Re-initialization preserves the recorded identity: never regenerate
        # the wing name for an existing brain.
        wing_name = recorded_wing
    elif wing_override:
        # Agent flow: the name was generated, then verified against the actual
        # palace (list_wings + tunnels/hallways) before being passed here.
        wing_name = sanitize_wing_name(wing_override)
    else:
        # New brain: timestamped unique name. The directory-derived wing and
        # the diary wing are reserved here; the agent flow additionally
        # verifies the generated name against live palace data (list_wings +
        # tunnels/hallways) and re-runs with --wing on the rare collision.
        wing_name = generate_wiki_wing_name(
            slug,
            taken={derived_wing, diary_wing_for_agent(diary_agent), FALLBACK_WING_NAME},
        )
        if wing_name == derived_wing:  # pragma: no cover — guaranteed by taken=
            wing_name = generate_wiki_wing_name(slug, taken={derived_wing, wing_name})

    # Fallback: ensure wing_name is never empty
    if not wing_name:
        import hashlib
        wing_name = WIKI_WING_PREFIX + hashlib.sha1(str(project_root).encode()).hexdigest()[:8]

    brain_schema = f"""---
mempalace_wing: {wing_name}
mempalace_diary_agent: {diary_agent}
---

# {title} Project Brain

> Operating schema for the project brain. Read this at the start of every serious session together with `.brain/state/session-brief.md`, `.brain/wiki/index.md`, and `graphify-out/GRAPH_REPORT.md` if present.

Created: {today}

## MemPalace namespace

Wiki pages are mined into MemPalace wing `{wing_name}`. Wiki knowledge is
searched in that wing: pass `wing: "{wing_name}"` to `mempalace_search` —
a search without `wing` scans the whole palace, other projects' wings
included. The session diary is separate: `mempalace_diary_write` with agent
`{diary_agent}` stores under MemPalace's diary default `{diary_wing_for_agent(diary_agent)}`,
and it is read back with `mempalace_diary_read` (agent `{diary_agent}`).
Never mine or diary into other projects' wings. Brains scaffolded by older
plugin versions may keep diary entries in the wiki wing — see "Existing
brains: older diary entries" in the plugin's
`skills/brain/references/mempalace-workflow.md`.

## Environment

{installed_line}

## Purpose

This brain exists so future models can understand the project after context resets or model changes.

## Layered architecture

1. `.brain/raw/` stores immutable curated evidence.
2. `.brain/wiki/` stores compiled LLM Wiki knowledge.
3. MemPalace stores verbatim memory, user preferences, and session diary.
4. `graphify-out/` stores relationship graph outputs.
5. `.brain/state/session-brief.md` stores the handoff a future model reads first.
6. Obsidian MCP can mirror selected wiki pages to the user's vault when requested.

The wiki is not the finish line. After wiki edits, regenerate the index with `project-brain-lint <project-root> --reindex`, then refresh graph, memory, open questions, log, and session brief when relevant.

## Session start protocol

1. Read this file.
2. Read `.brain/state/session-brief.md`.
3. Read `.brain/wiki/index.md`.
4. Read `.brain/tasks/next-actions.md`.
5. If `graphify-out/GRAPH_REPORT.md` exists, read it before broad architecture or code navigation.
6. Check MemPalace before making claims about previous decisions or conversations (follow the recall rule in the brain skill). The tools count as present when they appear in the session's tool list OR by name in the deferred-tools list; if deferred, load the schemas first with ONE ToolSearch call (query `select:<full tool name 1>,<full tool name 2>` — comma-separated exact full names — and `max_results` at least the number of names; success = the names appear in the returned `<functions>` block), then call `mempalace_status`. If they are genuinely absent, say which layer is down and continue; never probe with shell/node/pip and never write a check that always succeeds.
7. If Obsidian MCP tools are available, mention that vault sync is possible but do not sync unless requested.
8. If the brain is missing evidence, say what is missing instead of guessing.

## Lifecycle

1. Orient from brain state, wiki index, graph, and memory.
2. Ingest evidence into `.brain/raw/` or pointer files.
3. Compile durable synthesis into `.brain/wiki/`.
4. Refresh graphify when structure changed.
5. Write MemPalace diary/preferences when session context changed.
6. Sync to Obsidian only when the user asks.
7. Audit/lint the brain.
8. Update session brief and next actions.
9. Append a log entry.

## Naming conventions

- Architecture pages: `.brain/wiki/architecture/<Title Case>.md`
- Concept pages: `.brain/wiki/concepts/<Title Case>.md`
- Decision records: `.brain/wiki/decisions/<Decision Title>.md`
- Entity pages: `.brain/wiki/entities/<Proper Name>.md`
- Source summaries: `.brain/wiki/sources/<kebab-slug>.md`
- Synthesis pages: `.brain/wiki/syntheses/<Question or Thesis>.md`
- Query outputs: `.brain/outputs/queries/YYYY-MM-DD-<slug>.md`

## Evidence hierarchy

1. Raw sources and repository files.
2. Decision pages with source links.
3. Wiki synthesis.
4. graphify extracted relationships.
5. graphify inferred relationships.
6. MemPalace recollections.
7. Current chat claims.

## Wiki ledger

Page history: `.brain/state/wiki.git` (auto-snapshots on wiki edits, so the working tree is clean after each edit). See what changed with `project-brain-wiki <root> status` (two sections: `uncommitted:` pages first, then `recently snapshotted:` pages). Verify an edit with `project-brain-wiki <root> diff <page>` (shows the page's most recent change); undo a bad edit with `project-brain-wiki <root> restore <page>` (targets the version before the page's latest change; add `--rev <rev>` for an older one; dry run by default). Rules: the plugin skill → `references/wiki-ledger.md`.
"""
    write_template(brain / "CLAUDE.md", brain_schema, project_root, brain, force)

    # Seed content policy (KD-11): a fresh brain contains ONLY project-facing
    # placeholders. Plugin operating instructions live in .brain/CLAUDE.md,
    # never as wiki pages. The System Overview is a draft placeholder; open
    # questions is the live working list. No decision pages are seeded: a
    # decision record requires project evidence.
    page_common_draft = f"created: {today}\nupdated: {today}\nstatus: draft\nsources: []\n"
    pages: dict[Path, str] = {
        brain / "wiki/architecture/System Overview.md": f"""---
title: System Overview
type: architecture
{page_common_draft}tags: [architecture, overview]
---

# System Overview

This page is the high-level architecture map for **{title}**.

## Purpose

_To be filled from the project's own sources (README, entry points, module layout). This placeholder does not count as coverage._

## Main components

_To be filled from source inspection; every claim needs a citation._

## Related

- [[open-questions]]
""",
        brain / "wiki/open-questions.md": f"""---
title: Open Questions
type: overview
created: {today}
updated: {today}
status: active
sources: []
tags: [questions]
---

# Open Questions

## Project understanding

- What is the project purpose in one sentence (from its own README)?
- What are the core subsystems?

## Related

- [[architecture/System Overview]]
""",
    }

    for path, content in pages.items():
        write_template(path, content, project_root, brain, force)

    # index.md is generated from the real page tree on disk (KD-05): it can
    # list only pages that exist and cannot list any page twice.
    write_generated_index(brain, project_root, title, force=force)

    # KD-06: tasks live in ONE file (.brain/tasks/next-actions.md). The
    # session brief never carries a task checklist, so the two files cannot
    # contradict each other on done-state. KD-11: the brief claims no
    # decisions until evidence-backed decision pages exist.
    session_brief = f"""# Session Brief

Updated: {now}

## Project purpose

{title}

## Current state

Project brain scaffold created. No project understanding has been compiled yet.

## Active workstream

Initialize brain state, scan the project, and ingest first sources.

## Decisions made recently

None recorded yet. A decision is only recorded on an evidence-backed decision page (see `.brain/CLAUDE.md`).

## Known risks / contradictions

- No project-specific sources have been ingested yet.
- The system overview is still a placeholder.

## What to read next

1. `.brain/CLAUDE.md`
2. `.brain/wiki/index.md`
3. `.brain/tasks/next-actions.md` (the ONLY task list)
4. `graphify-out/GRAPH_REPORT.md` if present
"""
    write_template(brain / "state" / "session-brief.md", session_brief, project_root, brain, force)

    # KD-22: persist the plugin root at init so later shells read it instead
    # of re-deriving it (script-side persistence; the skill reads this file).
    (brain / "state" / "plugin-root.txt").write_text(
        str(Path(__file__).resolve().parent.parent) + "\n", encoding="utf-8"
    )

    next_actions = f"""# Next Actions

Updated: {now}

This is the project's ONLY task list (KD-06). The session brief links here and never carries its own checklist.

## First brain build

- [ ] Run `project-brain-inventory <project-root>` and read the unit table.
- [ ] Build the graphify output with the graphify CLI (`graphify .`) from the project root — never pass `graphify-out` itself as the path.
- [ ] Ingest sources for core-tier units first; cite every claim.
- [ ] Fill `.brain/wiki/architecture/System Overview.md` from real sources.
- [ ] Run `project-brain-lint <project-root> --reindex` after adding pages.
"""
    write_template(brain / "tasks" / "next-actions.md", next_actions, project_root, brain, force)

    # Default .graphifyignore for new projects — write once, then ensure_graphifyignore
    # keeps .brain/ and graphify-out/ present on re-runs (idempotent).
    graphifyignore_template = """.git/
.venv/
venv/
node_modules/
dist/
build/
coverage/
__pycache__/
*.pyc
*.log
.env
.env.*
*.pem
*.key
id_rsa*
secrets/
credentials*.json
.brain/log/
.brain/audit/
.brain/state/
.brain/outputs/
.brain/
graphify-out/
"""
    write_template(project_root / ".graphifyignore", graphifyignore_template, project_root, brain, force)
    # Idempotent guard: ensure .brain/ and graphify-out/ are present even on
    # projects scaffolded before this version (does nothing if already present).
    ensure_graphifyignore(project_root)

    snippet = f"""# Project Brain

This project has a persistent AI brain in `.brain/`.

At the start of serious work:

1. Read `.brain/CLAUDE.md`.
2. Read `.brain/state/session-brief.md`.
3. Read `.brain/wiki/index.md`.
4. Read `graphify-out/GRAPH_REPORT.md` if present before architecture or relationship questions.
5. Check MemPalace before making claims about prior work (follow the recall rule in the brain skill): a tool counts as available when it is in the tool list OR the deferred-tools list — for deferred tools, load the schemas first with ONE ToolSearch call (query `select:<full tool name 1>,<full tool name 2>` — comma-separated exact full names — and `max_results` at least the number of names; success = the names appear in the returned `<functions>` block), then call `mempalace_status`. Never probe availability with shell/node/pip.
6. Sync to Obsidian only when explicitly requested.

MemPalace is already installed as a plugin. graphify is already installed as a CLI tool and skill. Do not reinstall either.
"""
    write_template(project_root / "CLAUDE.project-brain.snippet.md", snippet, project_root, brain, force)
    merge_root_claude(project_root, snippet)

    append_log(brain, "init", title, [
        "Scaffolded or refreshed project brain structure.",
        "Preserved protected raw, source-summary, log, and audit data.",
        installed_line,
    ])

    init_wiki_ledger(project_root)

    print("\nProject brain ready.")
    version, plugin_root_resolved = plugin_identity()
    print(f"  Plugin: project-brain {version} (plugin root: {plugin_root_resolved})")
    print(f"  Root:   {project_root}")
    print(f"  Brain:  {brain}")
    print(f"  Wing:   {wing_name}")
    print("  Next:   project-brain-doctor <project-root>")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scaffold a layered project brain.")
    parser.add_argument("project_root", help="Existing project root directory")
    parser.add_argument("title", help="Project title")
    parser.add_argument("--force", action="store_true", help="Refresh template files without overwriting protected user-data areas")
    parser.add_argument(
        "--wing",
        dest="wing_override",
        default="",
        help="Explicit wiki wing name (used by the init flow after the generated name has been verified against the palace)",
    )
    return parser.parse_args(argv[1:])


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    scaffold(Path(args.project_root), args.title, force=args.force, wing_override=args.wing_override)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
