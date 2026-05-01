#!/usr/bin/env python3
"""Scaffold a layered project brain.

Usage:
    scaffold_brain.py <project-root> "<Project Name>" [--force]
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path


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


def merge_root_claude(project_root: Path, snippet: str) -> None:
    claude_md = project_root / "CLAUDE.md"
    if claude_md.exists():
        text = claude_md.read_text(encoding="utf-8")
        if "# Project Brain" in text:
            print("brain snippet already present in CLAUDE.md")
            return
        with claude_md.open("a", encoding="utf-8") as f:
            if not text.endswith("\n"):
                f.write("\n")
            f.write("\n" + snippet.strip() + "\n")
        print("appended brain snippet to CLAUDE.md")
    else:
        claude_md.write_text(snippet.strip() + "\n", encoding="utf-8")
        print("wrote: CLAUDE.md")


def scaffold(project_root: Path, title: str, force: bool = False) -> None:
    project_root = project_root.expanduser()
    if not project_root.exists():
        sys.exit(f"Error: project root does not exist: {project_root}")
    if not project_root.is_dir():
        sys.exit(f"Error: project root is not a directory: {project_root}")

    project_root = project_root.resolve()
    brain = project_root / ".brain"
    today = date.today().isoformat()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    dirs = [
        "raw/articles", "raw/papers", "raw/notes", "raw/refs", "raw/meetings", "raw/conversations", "raw/assets",
        "wiki/architecture", "wiki/concepts", "wiki/decisions", "wiki/entities", "wiki/sources", "wiki/syntheses",
        "outputs/queries", "state", "memory", "graph", "tasks", "runbooks", "log", "audit/resolved",
    ]
    for rel in dirs:
        (brain / rel).mkdir(parents=True, exist_ok=True)

    for rel in ["audit/.gitkeep", "audit/resolved/.gitkeep", "raw/assets/.gitkeep", "outputs/queries/.gitkeep"]:
        touch_marker(brain / rel, project_root)

    installed_line = "MemPalace is already installed as a plugin. graphify is already installed as a CLI tool and skill. Do not reinstall either."

    brain_schema = f"""# {title} Project Brain

> Operating schema for the project brain. Read this at the start of every serious session together with `.brain/state/session-brief.md`, `.brain/wiki/index.md`, and `graphify-out/GRAPH_REPORT.md` if present.

Created: {today}

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

The wiki is not the finish line. After wiki edits, update index, graph, memory, open questions, log, and session brief when relevant.

## Session start protocol

1. Read this file.
2. Read `.brain/state/session-brief.md`.
3. Read `.brain/wiki/index.md`.
4. Read `.brain/tasks/next-actions.md`.
5. If `graphify-out/GRAPH_REPORT.md` exists, read it before broad architecture or code navigation.
6. Call `mempalace_status` if available before making claims about previous decisions or conversations.
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
"""
    write_template(brain / "CLAUDE.md", brain_schema, project_root, brain, force)

    index = f"""# Project Brain Index - {title}

> Catalog of durable project knowledge. Every wiki page should appear here exactly once.

## Start here

- [[architecture/AI Brain Architecture]] - how the brain layers connect.
- [[architecture/System Overview]] - high-level project map.
- [[decisions/Use Layered Brain Architecture]] - why this brain uses wiki + memory + graph + vault + handoff.
- [[open-questions]] - unresolved questions, contradictions, and research gaps.

## Architecture

- [[architecture/AI Brain Architecture]] - the operating architecture for the brain itself.
- [[architecture/System Overview]] - initial project placeholder; update after graphify/code review.

## Decisions

- [[decisions/Use Layered Brain Architecture]] - accepted starting architecture for the brain.

## Concepts

- [[concepts/LLM Wiki]] - compiled markdown knowledge layer.
- [[concepts/Post-Wiki Synchronization]] - what the agent must do after wiki changes.

## Entities

- [[entities/MemPalace]] - memory layer for verbatim recall and session diary.
- [[entities/graphify]] - relationship graph layer for structure and paths.
- [[entities/Obsidian]] - vault view layer for human browsing.

## Sources

*(none yet)*

## Syntheses

*(none yet)*
"""
    write_template(brain / "wiki" / "index.md", index, project_root, brain, force)

    page_common = f"created: {today}\nupdated: {today}\nstatus: active\nsources: []\n"
    pages: dict[Path, str] = {
        brain / "wiki/architecture/AI Brain Architecture.md": f"""---
title: AI Brain Architecture
type: architecture
{page_common}tags: [architecture, brain]
---

# AI Brain Architecture

The project brain is a layered system that lets a future model recover context after a model change or context reset.

## Layers

```mermaid
flowchart TD
    Raw[.brain/raw evidence] --> Wiki[.brain/wiki compiled knowledge]
    Repo[project files] --> Graph[graphify-out relationship graph]
    Graph --> Wiki
    Memory[MemPalace memory] --> Wiki
    Wiki --> Memory
    Wiki --> Brief[session brief]
    Wiki --> Vault[Obsidian vault mirror]
    Brief --> Agent[future model]
```

## Responsibilities

- `.brain/raw/` stores source material the agent should not rewrite.
- `.brain/wiki/` stores maintained synthesis and cross-links.
- MemPalace stores previous conversations, user preferences, and diary entries.
- graphify stores relationship maps across code, docs, and sources.
- Obsidian MCP mirrors selected wiki pages to the vault when requested.
- `.brain/state/session-brief.md` stores the short handoff for a future model.

## Related

- [[concepts/LLM Wiki]]
- [[concepts/Post-Wiki Synchronization]]
- [[decisions/Use Layered Brain Architecture]]
""",
        brain / "wiki/architecture/System Overview.md": f"""---
title: System Overview
type: architecture
created: {today}
updated: {today}
status: draft
sources: []
tags: [architecture, overview]
---

# System Overview

This page is the high-level architecture map for **{title}**.

## Purpose

_To be filled after the first project scan._

## Main components

_To be filled from source inspection and graphify output._

## Related

- [[architecture/AI Brain Architecture]]
""",
        brain / "wiki/decisions/Use Layered Brain Architecture.md": f"""---
title: Use Layered Brain Architecture
type: decision
{page_common}tags: [decision, brain]
---

# Use Layered Brain Architecture

## Decision

Use a layered project brain made of raw evidence, LLM Wiki synthesis, MemPalace memory, graphify relationship graphs, Obsidian vault sync, logs/audits, and session handoff state.

## Why this option

The layered architecture separates evidence, synthesis, memory, relationships, human browsing, and handoff. Each layer does one job and cross-checks the others.

## Related

- [[architecture/AI Brain Architecture]]
- [[concepts/Post-Wiki Synchronization]]
""",
        brain / "wiki/concepts/LLM Wiki.md": f"""---
title: LLM Wiki
type: concept
{page_common}tags: [wiki, brain]
---

# LLM Wiki

An LLM Wiki is a persistent markdown knowledge base that the agent maintains as compiled project understanding.

## What it stores

- Source summaries
- Concepts
- Entity pages
- Architecture pages
- Decision records
- Durable answers and syntheses

## Related

- [[concepts/Post-Wiki Synchronization]]
- [[architecture/AI Brain Architecture]]
""",
        brain / "wiki/concepts/Post-Wiki Synchronization.md": f"""---
title: Post-Wiki Synchronization
type: concept
{page_common}tags: [workflow, brain]
---

# Post-Wiki Synchronization

Post-wiki synchronization is the work the agent must do after writing or editing wiki pages.

## Checklist

1. Update `.brain/wiki/index.md`.
2. Add wikilinks and backlinks.
3. Extract or update decision records.
4. Refresh graphify if structure changed.
5. Write MemPalace diary/preferences if session context changed.
6. Add contradictions and unresolved questions.
7. Update `.brain/state/session-brief.md`.
8. Append a log entry.
9. Run lint after large edits.

## Related

- [[concepts/LLM Wiki]]
- [[architecture/AI Brain Architecture]]
""",
        brain / "wiki/entities/MemPalace.md": f"""---
title: MemPalace
type: entity
{page_common}tags: [memory, tool]
---

# MemPalace

MemPalace is the memory layer for previous conversations, user preferences, diary entries, and verbatim recall.

## Role in the brain

- Search before making claims about past work.
- Store concise diary entries after major sessions.
- Preserve user preferences that should survive model changes.
- Feed durable project insights back into the wiki.

## Related

- [[architecture/AI Brain Architecture]]
- [[decisions/Use Layered Brain Architecture]]
""",
        brain / "wiki/entities/graphify.md": f"""---
title: graphify
type: entity
{page_common}tags: [graph, tool]
---

# graphify

graphify is the relationship graph layer for code, docs, raw sources, diagrams, papers, and other project materials.

## Role in the brain

- Build `graphify-out/GRAPH_REPORT.md`, `graph.json`, and graph visualization outputs.
- Identify god nodes, communities, paths, surprising links, and suggested questions.
- Feed stable structural findings into wiki architecture and concept pages.

## Related

- [[architecture/AI Brain Architecture]]
- [[concepts/Post-Wiki Synchronization]]
""",
        brain / "wiki/entities/Obsidian.md": f"""---
title: Obsidian
type: entity
{page_common}tags: [vault, tool]
---

# Obsidian

Obsidian is the optional human-browsing layer for the project brain. The agent mirrors selected `.brain/wiki/` pages to the vault only when the user asks.

## Role in the brain

- Browse wiki pages with native wikilinks.
- Use graph view for the user's mental model.
- Annotate curated knowledge outside raw scaffolding.

## Related

- [[architecture/AI Brain Architecture]]
- [[concepts/LLM Wiki]]
""",
        brain / "wiki/open-questions.md": f"""---
title: Open Questions
type: overview
{page_common}tags: [questions]
---

# Open Questions

## Project understanding

- What are the first 3-5 sources to ingest?
- What are the most important user preferences to preserve?
- What is the project purpose in one sentence?

## Architecture

- What are the core subsystems?
- Which graphify communities should become wiki architecture pages?

## Related

- [[architecture/System Overview]]
""",
    }
    for path, content in pages.items():
        write_template(path, content, project_root, brain, force)

    session_brief = f"""# Session Brief

Updated: {now}

## Project purpose

{title}

## Current state

Project brain scaffold created. The brain architecture is ready, but detailed project understanding has not been compiled yet.

## Active workstream

Initialize brain state, scan the project, and ingest first sources.

## Decisions made recently

- Created layered project brain structure under `.brain/`.
- Accepted [[decisions/Use Layered Brain Architecture]].

## Known risks / contradictions

- No project-specific sources have been ingested yet.
- The system overview is still a placeholder.

## What to read next

1. `.brain/CLAUDE.md`
2. `.brain/wiki/index.md`
3. `.brain/wiki/architecture/AI Brain Architecture.md`
4. `.brain/tasks/next-actions.md`
5. `graphify-out/GRAPH_REPORT.md` if present

## Next actions

- [ ] Run `project-brain-doctor .`.
- [ ] Run `/graphify .` when ready to map relationships.
- [ ] Ingest first raw sources into `.brain/raw/`.
"""
    write_template(brain / "state" / "session-brief.md", session_brief, project_root, brain, force)

    next_actions = f"""# Next Actions

Updated: {now}

## Setup

- [ ] Run `project-brain-doctor .`.
- [ ] Confirm MemPalace MCP is active with `mempalace_status`.
- [ ] Build graphify output when ready.
- [ ] Decide whether to mirror wiki pages to Obsidian.

## First brain build

- [ ] Identify first raw sources to ingest.
- [ ] Update `.brain/wiki/architecture/System Overview.md` from graphify/project scan.
- [ ] Add first decision records.
- [ ] Update `.brain/state/session-brief.md` after first real scan.
"""
    write_template(brain / "tasks" / "next-actions.md", next_actions, project_root, brain, force)

    graphifyignore = """.git/
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
secrets/
.brain/log/
.brain/audit/
.brain/state/
.brain/outputs/
graphify-out/
"""
    write_template(project_root / ".graphifyignore", graphifyignore, project_root, brain, force)

    snippet = f"""# Project Brain

This project has a persistent AI brain in `.brain/`.

At the start of serious work:

1. Read `.brain/CLAUDE.md`.
2. Read `.brain/state/session-brief.md`.
3. Read `.brain/wiki/index.md`.
4. Read `graphify-out/GRAPH_REPORT.md` if present before architecture or relationship questions.
5. Call `mempalace_status` if available before making claims about prior work.
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

    print("\nProject brain ready.")
    print(f"  Root:  {project_root}")
    print(f"  Brain: {brain}")
    print("  Next:  project-brain-doctor <project-root>")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scaffold a layered project brain.")
    parser.add_argument("project_root", help="Existing project root directory")
    parser.add_argument("title", help="Project title")
    parser.add_argument("--force", action="store_true", help="Refresh template files without overwriting protected user-data areas")
    return parser.parse_args(argv[1:])


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    scaffold(Path(args.project_root), args.title, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
