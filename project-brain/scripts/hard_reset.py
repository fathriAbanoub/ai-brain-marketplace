#!/usr/bin/env python3
"""Hard reset: database-level deletion of confirmed MemPalace wings.

This is the local, database-backed counterpart of the normal MCP reset. It is
a SEPARATE operation with its own authorization (/project-brain:hard-reset,
referred to in the plugin docs as the "mempalace hard reset" command) and is
only appropriate when the normal MCP route cannot complete and the user has
explicitly authorized direct database mutation.

Safety architecture (see skills/hard-reset/SKILL.md):

- FAIL-CLOSED discovery: the palace file is resolved from --db-path or
  MEMPAL_DIR; anything else refuses. No home-directory guessing.
- FAIL-CLOSED schema: the actual SQLite schema is introspected at runtime
  (sqlite_master + PRAGMA table_info / foreign_key_list). Tables are
  classified by column-shape evidence (wing-tagged tables, drawer-id child
  tables). An unclassifiable or unsupported layout refuses the destructive
  operation instead of guessing.
- DRY RUN DEFAULT: without --confirm nothing is written. The plan is printed
  and hashed; --confirm must pass --plan-hash <hash> matching the exact plan
  it confirms. A changed plan invalidates the confirmation.
- BACKUP: the database (and any WAL/SHM sidecars and revision JSONL files)
  is copied to a timestamped backup directory before any mutation.
- TRANSACTION: all deletions run in one BEGIN IMMEDIATE transaction with a
  rollback on any error, followed by PRAGMA integrity_check.
- ISOLATION: only rows whose wing column equals the exact confirmed wing
  names are touched. Unrelated wings are verified untouched after the run.
- REVISION SIDECARS: JSONL revision logs next to the database are rewritten
  via temp file + atomic replace after backup (never in-place text edits).

Tested exclusively against disposable synthetic databases — see
tests/test_hard_reset.py. This tool refuses to operate when MemPalace is
running (WAL/SHM present) unless --allow-live is passed, because deleting
under a live server can corrupt or be overwritten by in-memory state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

DB_EXTENSIONS = (".db", ".sqlite", ".sqlite3")
# Any of these column names makes a table wing-tagged. Tunnels carry
# source_wing/target_wing endpoints; hallways carry wing; drawers carry wing.
WING_COLUMN_NAMES = ("wing", "wing_name", "source_wing", "target_wing", "wing_a", "wing_b")
# Default ChromaDB persistent-store tables. ChromaDB keeps document metadata as
# rows in embedding_metadata (not as wing columns) and vectors in HNSW segment
# files, so deleting SQLite rows directly would leave the vector index stale:
# such palaces are refused unless removal can happen safely through the Chroma
# API, which this offline SQLite-only tool cannot establish.
CHROMA_TABLE_NAMES = ("embeddings", "embedding_metadata", "segments", "collections")
SIDECAR_SUFFIXES = (".revisions.jsonl", ".jsonl")
SQLITE_HEADER = b"SQLite format 3\x00"

PLAN_VERSION = 1


class HardResetRefused(Exception):
    """The destructive operation cannot proceed safely; show the reason."""


# ---------------------------------------------------------------------------
# Discovery (fail-closed)
# ---------------------------------------------------------------------------

def discover_database(explicit_path: str) -> Path:
    """Resolve the palace database file. Refuses rather than guesses."""
    if explicit_path:
        path = Path(explicit_path).expanduser().resolve()
        if not path.exists():
            raise HardResetRefused(f"--db-path does not exist: {path}")
        if path.is_dir():
            raise HardResetRefused(
                f"--db-path is a directory, not a database file: {path}; "
                "pass the palace database file itself"
            )
        return path
    mempal_dir = os.environ.get("MEMPAL_DIR", "").strip()
    if not mempal_dir:
        raise HardResetRefused(
            "cannot determine the palace database location: no --db-path given "
            "and MEMPAL_DIR is not set. Locate the database via the installed "
            "MemPalace CLI/config (e.g. `mempalace status` output) or pass "
            "--db-path explicitly. Refusing to guess."
        )
    candidate = Path(mempal_dir).expanduser().resolve()
    if candidate.is_file():
        return candidate
    if candidate.is_dir():
        db_files = sorted(
            p for p in candidate.iterdir()
            if p.is_file() and p.suffix.lower() in DB_EXTENSIONS
        )
        if len(db_files) == 1:
            return db_files[0]
        if not db_files:
            raise HardResetRefused(
                f"MEMPAL_DIR ({candidate}) contains no database file "
                f"with extensions {DB_EXTENSIONS}; refusing to guess"
            )
        raise HardResetRefused(
            f"MEMPAL_DIR ({candidate}) contains {len(db_files)} database "
            f"candidates ({', '.join(p.name for p in db_files[:5])}); pass "
            "--db-path explicitly to choose"
        )
    raise HardResetRefused(f"MEMPAL_DIR points at a non-existent path: {candidate}")


# ---------------------------------------------------------------------------
# Schema introspection (fail-closed)
# ---------------------------------------------------------------------------

@dataclass
class TablePlan:
    name: str
    role: str                    # wing-tagged | drawer-child | wing-registry
    wing_columns: list[str] = field(default_factory=list)  # all wing-bearing columns
    child_column: str = ""       # drawer_id-like FK column for children
    row_count: int = 0           # rows affected for the confirmed wings


@dataclass
class SidecarPlan:
    path: Path
    total_lines: int = 0
    affected_lines: int = 0


@dataclass
class ResetPlan:
    db_path: Path
    backend: str
    wings: list[str]
    tables: list[TablePlan] = field(default_factory=list)
    sidecars: list[SidecarPlan] = field(default_factory=list)
    backup_dir: Path | None = None
    unrelated_wing_counts: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def affected_rows(self) -> int:
        return sum(t.row_count for t in self.tables)


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def open_readonly(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def verify_backend(db_path: Path) -> None:
    with open(db_path, "rb") as fh:
        header = fh.read(16)
    if header != SQLITE_HEADER:
        raise HardResetRefused(
            f"{db_path} is not an SQLite database (header {header!r}); this "
            "tool supports local SQLite palaces only and refuses remote or "
            "unknown backends"
        )


def classify_schema(conn: sqlite3.Connection, db_path: Path) -> list[TablePlan]:
    """Classify every user table by column-shape evidence.

    - wing-tagged: has a `wing`/`wing_name` column -> rows of the confirmed
      wings are deleted directly.
    - drawer-child: no wing column but a `drawer_id`/`drawer` column -> rows
      referencing the wing's drawers are deleted via subquery.
    - Anything else is left untouched and noted.
    Refuses when no wing-tagged table exists (unsupported layout).
    """
    tables = [
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'"
        )
    ]
    if not tables:
        raise HardResetRefused(f"no user tables found in {db_path}; unsupported layout")
    tables_lower = {t.lower() for t in tables}
    if "embeddings" in tables_lower and "embedding_metadata" in tables_lower:
        raise HardResetRefused(
            f"{db_path} has the default ChromaDB persistent-store layout "
            f"({', '.join(t for t in CHROMA_TABLE_NAMES if t in tables_lower)}); "
            "its records can only be removed safely through the Chroma API — "
            "deleting embedding_metadata or other rows directly in SQLite would "
            "leave vectors in the HNSW segment files. This tool supports "
            "wing-tagged SQLite palaces only, so the default backend is "
            "unsupported; use the normal MCP-based reset for ChromaDB palaces"
        )
    plans: list[TablePlan] = []
    wing_tagged = 0
    for table in tables:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({_quote_ident(table)})")]
        cols_lower = {c.lower(): c for c in cols}
        wing_cols = [cols_lower[c] for c in WING_COLUMN_NAMES if c in cols_lower]
        if wing_cols:
            wing_tagged += 1
            plans.append(TablePlan(name=table, role="wing-tagged", wing_columns=wing_cols))
            continue
        child_col = next(
            (cols_lower[c] for c in ("drawer_id", "drawer", "drawer_ids") if c in cols_lower),
            "",
        )
        if child_col:
            # A child table needs a wing-tagged parent with an id column.
            plans.append(TablePlan(name=table, role="drawer-child", child_column=child_col))
    if wing_tagged == 0:
        raise HardResetRefused(
            f"no wing-tagged table (column 'wing'/'wing_name') found in "
            f"{db_path}; the actual schema differs from what this helper "
            "supports — refusing the destructive operation until "
            "compatibility is established"
        )
    # drawer-children only make sense with a wing-tagged drawer table that
    # has an id column; verify that parent exists, else drop the children
    # from the plan (they would be orphans but deleting them is optional and
    # must not guess).
    parent = next((p for p in plans if p.role == "wing-tagged" and p.name.lower() in ("drawers", "drawer")), None)
    if parent is None:
        for p in plans:
            if p.role == "drawer-child":
                p.role = "unclassified"
        notes_parent_missing = True
    else:
        notes_parent_missing = False
    if notes_parent_missing:
        for p in plans:
            if p.role == "drawer-child":
                p.role = "unreferenced-child"
    return plans


def count_affected(conn: sqlite3.Connection, plans: list[TablePlan], wings: list[str]) -> None:
    parent = next((p for p in plans if p.role == "wing-tagged" and p.name.lower() in ("drawers", "drawer")), None)
    placeholders = ",".join("?" for _ in wings)
    for plan in plans:
        if plan.role == "wing-tagged":
            predicate = " OR ".join(
                f"{_quote_ident(col)} IN ({placeholders})" for col in plan.wing_columns
            )
            cur = conn.execute(
                f"SELECT COUNT(*) FROM {_quote_ident(plan.name)} WHERE {predicate}",
                wings * len(plan.wing_columns),
            )
            plan.row_count = int(cur.fetchone()[0])
        elif plan.role == "drawer-child" and parent is not None:
            cur = conn.execute(
                f"SELECT COUNT(*) FROM {_quote_ident(plan.name)} WHERE "
                f"{_quote_ident(plan.child_column)} IN (SELECT id FROM "
                f"{_quote_ident(parent.name)} WHERE "
                f"{_quote_ident(parent.wing_columns[0])} IN ({placeholders}))",
                wings,
            )
            plan.row_count = int(cur.fetchone()[0])


def count_unrelated(conn: sqlite3.Connection, plans: list[TablePlan], wings: list[str]) -> dict[str, int]:
    """Per-wing drawer counts for every non-target wing (isolation evidence)."""
    parent = next((p for p in plans if p.role == "wing-tagged" and p.name.lower() in ("drawers", "drawer")), None)
    counts: dict[str, int] = {}
    if parent is None:
        return counts
    placeholders = ",".join("?" for _ in wings)
    for row in conn.execute(
        f"SELECT {_quote_ident(parent.wing_columns[0])} AS wing, COUNT(*) AS n FROM "
        f"{_quote_ident(parent.name)} WHERE {_quote_ident(parent.wing_columns[0])} NOT IN ({placeholders}) "
        f"GROUP BY {_quote_ident(parent.wing_columns[0])}",
        wings,
    ):
        counts[str(row["wing"])] = int(row["n"])
    return counts


def plan_sidecars(db_path: Path, wings: list[str]) -> list[SidecarPlan]:
    """JSONL revision logs next to the DB: count lines mentioning the wings.

    Only files whose JSON lines actually carry a wing field are planned;
    unparseable or wing-less files are warned about, never blind-edited.
    """
    sidecars: list[SidecarPlan] = []
    for item in sorted(db_path.parent.iterdir()):
        if not item.is_file() or not item.name.endswith(SIDECAR_SUFFIXES):
            continue
        if item.name.startswith(db_path.name):
            pass  # db-adjacent sidecar like palace.db.revisions.jsonl
        elif not item.name.endswith(".jsonl"):
            continue
        total = 0
        affected = 0
        wing_keys = ("wing", "wing_name")
        try:
            with item.open("r", encoding="utf-8") as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    total += 1
                    try:
                        record = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(record, dict) and any(
                        record.get(k) in wings for k in wing_keys
                    ):
                        affected += 1
        except OSError as exc:
            sidecars.append(SidecarPlan(path=item, total_lines=-1, affected_lines=0))
            continue
        if total:
            sidecars.append(SidecarPlan(path=item, total_lines=total, affected_lines=affected))
    return sidecars


def detect_live_server(db_path: Path) -> list[str]:
    """WAL/SHM sidecars indicate the server may be running."""
    live = [
        item.name for item in db_path.parent.iterdir()
        if item.is_file() and item.name in (f"{db_path.name}-wal", f"{db_path.name}-shm")
    ]
    return live


def wing_registry_table(conn: sqlite3.Connection) -> tuple[str, str]:
    """(table, key column) of a dedicated wings table, if the schema has one.

    The key column is whatever the table actually uses ('wing', 'wing_name',
    or 'name') so the registry DELETE never assumes a wing column that a
    name- or wing_name-keyed table does not have."""
    for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ):
        name = r[0]
        if name.lower() not in ("wings", "wing"):
            continue
        cols = {row[1].lower() for row in conn.execute(f"PRAGMA table_info({_quote_ident(name)})")}
        for candidate in ("wing", "wing_name", "name"):
            if candidate in cols:
                return name, candidate
    return "", ""


# ---------------------------------------------------------------------------
# Plan / backup / execute / verify
# ---------------------------------------------------------------------------

def build_plan(db_path: Path, wings: list[str], backup_root: Path | None = None) -> ResetPlan:
    # Ambiguity guard: two requested wings that normalize identically are
    # distinct records — refuse and require the user to pick exact names.
    seen: dict[str, str] = {}
    for wing in wings:
        key = wing.strip().lower().replace(" ", "_").replace("-", "_").strip("_")
        if key in seen and seen[key] != wing:
            raise HardResetRefused(
                f"ambiguous targets: {seen[key]!r} and {wing!r} normalize to the "
                "same comparison value but are distinct records; pass the exact "
                "wing name(s) you want deleted"
            )
        seen[key] = wing
    verify_backend(db_path)
    conn = open_readonly(db_path)
    try:
        plans = classify_schema(conn, db_path)
        count_affected(conn, plans, wings)
        unrelated = count_unrelated(conn, plans, wings)
        plan = ResetPlan(
            db_path=db_path,
            backend="sqlite (local file, header verified)",
            wings=list(wings),
            tables=plans,
            unrelated_wing_counts=unrelated,
        )
        registry, _registry_key = wing_registry_table(conn)
        if registry:
            plan.notes.append(
                f"wing registry table {registry!r} detected; its row for the "
                "confirmed wings is deleted last (children first)"
            )
        live = detect_live_server(db_path)
        if live:
            plan.warnings.append(
                "WAL/SHM files present (" + ", ".join(live) + ") — MemPalace may be "
                "running; stop it before a hard reset or pass --allow-live"
            )
    finally:
        conn.close()
    plan.sidecars = plan_sidecars(db_path, wings)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    plan.backup_dir = (backup_root or db_path.parent) / f"{db_path.name}.hard-reset-backup-{stamp}"
    return plan


def plan_hash(plan: ResetPlan) -> str:
    payload = {
        "version": PLAN_VERSION,
        "db": str(plan.db_path),
        "wings": plan.wings,
        "tables": [(t.name, t.role, t.row_count) for t in plan.tables if t.row_count],
        "sidecars": [(str(s.path), s.affected_lines) for s in plan.sidecars if s.affected_lines],
        "affected_rows": plan.affected_rows(),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def print_plan(plan: ResetPlan) -> None:
    print("Hard reset plan (dry run)")
    print(f"  backend:      {plan.backend}")
    print(f"  database:     {plan.db_path}")
    print(f"  target wings: {', '.join(plan.wings)}")
    print("  affected records by category:")
    for table in plan.tables:
        if table.row_count or table.role == "wing-tagged":
            detail = f"wing columns: {', '.join(table.wing_columns)}" if table.role == "wing-tagged" else f"child of drawers via {table.child_column}"
            print(f"    - {table.name} [{table.role}]: {table.row_count} row(s) ({detail})")
    for sidecar in plan.sidecars:
        if sidecar.total_lines < 0:
            print(f"    - {sidecar.path.name}: UNREADABLE (will be backed up, not rewritten)")
        else:
            print(f"    - {sidecar.path.name}: {sidecar.affected_lines}/{sidecar.total_lines} revision line(s)")
    if not plan.sidecars:
        print("    - revision sidecars: none found")
    print(f"  backup dir:   {plan.backup_dir}")
    for wing, count in sorted(plan.unrelated_wing_counts.items()):
        print(f"  preserved:    wing {wing!r}: {count} drawer(s) untouched")
    for note in plan.notes:
        print(f"  note:         {note}")
    for warning in plan.warnings:
        print(f"  WARNING:      {warning}")
    print(f"  total affected rows: {plan.affected_rows()}")
    print(f"  plan hash:    {plan_hash(plan)}")


def make_backup(plan: ResetPlan) -> Path:
    backup_dir = plan.backup_dir
    assert backup_dir is not None
    backup_dir.mkdir(parents=True, exist_ok=False)
    shutil.copy2(plan.db_path, backup_dir / plan.db_path.name)
    for suffix in ("-wal", "-shm"):
        sidecar = plan.db_path.with_name(plan.db_path.name + suffix)
        if sidecar.exists():
            shutil.copy2(sidecar, backup_dir / sidecar.name)
    for sidecar in plan.sidecars:
        if sidecar.path.exists():
            shutil.copy2(sidecar.path, backup_dir / sidecar.path.name)
    return backup_dir


def execute_deletions(conn: sqlite3.Connection, plan: ResetPlan,
                      registry: str, registry_key: str) -> list[str]:
    """Run all deletions inside one transaction; caller commits or rolls back."""
    executed: list[str] = []
    wings = plan.wings
    placeholders = ",".join("?" for _ in wings)
    parent = next((p for p in plan.tables if p.role == "wing-tagged" and p.name.lower() in ("drawers", "drawer")), None)
    # Children first, then wing-tagged rows, then the registry row.
    for table_plan in plan.tables:
        if table_plan.role != "drawer-child" or table_plan.row_count == 0:
            continue
        cur = conn.execute(
            f"DELETE FROM {_quote_ident(table_plan.name)} WHERE "
            f"{_quote_ident(table_plan.child_column)} IN (SELECT id FROM "
            f"{_quote_ident(parent.name)} WHERE {_quote_ident(parent.wing_columns[0])} "
            f"IN ({placeholders}))",
            wings,
        )
        executed.append(f"DELETE {table_plan.name}: {cur.rowcount} row(s)")
    for table_plan in plan.tables:
        if table_plan.role != "wing-tagged" or table_plan.row_count == 0:
            continue
        predicate = " OR ".join(
            f"{_quote_ident(col)} IN ({placeholders})" for col in table_plan.wing_columns
        )
        cur = conn.execute(
            f"DELETE FROM {_quote_ident(table_plan.name)} WHERE {predicate}",
            wings * len(table_plan.wing_columns),
        )
        executed.append(f"DELETE {table_plan.name}: {cur.rowcount} row(s)")
    if registry and registry_key:
        cur = conn.execute(
            f"DELETE FROM {_quote_ident(registry)} "
            f"WHERE {_quote_ident(registry_key)} IN ({placeholders})",
            wings,
        )
        if cur.rowcount:
            executed.append(f"DELETE {registry}: {cur.rowcount} row(s)")
    return executed


def rewrite_sidecars(plan: ResetPlan) -> list[str]:
    """Rewrite JSONL sidecars without the confirmed wings' lines (atomic)."""
    done: list[str] = []
    wings = set(plan.wings)
    wing_keys = ("wing", "wing_name")
    for sidecar in plan.sidecars:
        if sidecar.total_lines < 0 or sidecar.affected_lines == 0:
            continue
        kept: list[str] = []
        with sidecar.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                drop = False
                if line.strip():
                    try:
                        record = json.loads(line)
                    except ValueError:
                        record = None
                    if isinstance(record, dict) and any(record.get(k) in wings for k in wing_keys):
                        drop = True
                if not drop:
                    kept.append(line)
        tmp = sidecar.path.with_suffix(sidecar.path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            fh.writelines(kept)
        tmp.replace(sidecar.path)
        done.append(f"rewrote {sidecar.path.name}: removed {sidecar.affected_lines} line(s)")
    return done


def verify_result(plan: ResetPlan, backup_dir: Path) -> tuple[bool, list[str]]:
    """Independent post-mutation verification through fresh reads."""
    problems: list[str] = []
    conn = sqlite3.connect(f"file:{plan.db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            problems.append(f"integrity_check: {integrity}")
        for table_plan in plan.tables:
            if table_plan.role != "wing-tagged":
                continue
            placeholders = ",".join("?" for _ in plan.wings)
            predicate = " OR ".join(
                f"{_quote_ident(col)} IN ({placeholders})" for col in table_plan.wing_columns
            )
            cur = conn.execute(
                f"SELECT COUNT(*) FROM {_quote_ident(table_plan.name)} WHERE {predicate}",
                plan.wings * len(table_plan.wing_columns),
            )
            remaining = int(cur.fetchone()[0])
            if remaining:
                problems.append(f"{table_plan.name}: {remaining} row(s) remain for target wings")
        # Unrelated wings must be untouched.
        parent = next((p for p in plan.tables if p.role == "wing-tagged" and p.name.lower() in ("drawers", "drawer")), None)
        if parent is not None:
            after = count_unrelated(conn, plan.tables, plan.wings)
            if after != plan.unrelated_wing_counts:
                problems.append(
                    f"unrelated wing counts changed: before={plan.unrelated_wing_counts} after={after}"
                )
    finally:
        conn.close()
    if not (backup_dir / plan.db_path.name).exists():
        problems.append("backup file missing after operation")
    return (not problems), problems


def confirm_guard(args: argparse.Namespace, plan: ResetPlan) -> None:
    if not args.confirm:
        return
    if not args.plan_hash:
        raise HardResetRefused(
            "--confirm requires --plan-hash <hash> from the dry-run plan it "
            "confirms; the confirmation must be tied to the exact displayed plan"
        )
    current = plan_hash(plan)
    if args.plan_hash != current:
        raise HardResetRefused(
            f"plan hash mismatch: confirming {args.plan_hash!r} but the current "
            f"plan is {current!r}; the plan changed materially — review the new "
            "dry run and confirm again"
        )


def run(args: argparse.Namespace) -> int:
    try:
        db_path = discover_database(args.db_path)
        plan = build_plan(db_path, args.wing)
        confirm_guard(args, plan)
        print_plan(plan)
        if not args.confirm:
            print("\nDry run only. Nothing was modified.")
            print("To execute: rerun with --confirm --plan-hash <hash above>.")
            return 0
        live = detect_live_server(db_path)
        if live and not args.allow_live:
            raise HardResetRefused(
                "refusing to modify a possibly-live palace (" + ", ".join(live) +
                "); stop MemPalace first or pass --allow-live"
            )
        backup_dir = make_backup(plan)
        print(f"Backup created: {backup_dir}")
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute("BEGIN IMMEDIATE")
            registry, registry_key = wing_registry_table(conn)
            executed = execute_deletions(conn, plan, registry, registry_key)
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise sqlite3.DatabaseError(f"integrity_check failed inside transaction: {integrity}")
            conn.commit()
        except Exception as exc:
            conn.rollback()
            print(f"✗ Deletion failed and was rolled back: {exc}", file=sys.stderr)
            print(f"  Backup preserved at: {backup_dir}", file=sys.stderr)
            return 1
        finally:
            conn.close()
        # Sidecars are plain files, not part of the SQLite transaction: rewrite
        # them only after the commit succeeded, so a rollback leaves the
        # sidecar files unchanged and the "rolled back" message stays true.
        try:
            executed.extend(rewrite_sidecars(plan))
        except Exception as exc:
            print(f"✗ Database committed, but sidecar rewrite failed: {exc}", file=sys.stderr)
            print(f"  Backup preserved at: {backup_dir}", file=sys.stderr)
            return 1
        for line in executed:
            print(f"✓ {line}")
        ok, problems = verify_result(plan, backup_dir)
        if not ok:
            print("✗ Post-deletion verification FAILED — the hard reset must not be reported as success:", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
            print(f"  Backup and recovery path: {backup_dir}", file=sys.stderr)
            return 1
        print("✓ integrity_check: ok; target wings removed; unrelated wings unchanged")
        print("Reconnect MemPalace so its in-memory index matches the database:")
        print("  call the mempalace_reconnect MCP tool (or restart the MemPalace server).")
        print("Hard reset complete.")
        return 0
    except HardResetRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="project-brain-hard-reset",
        description=(
            "Database-level deletion of confirmed MemPalace wings (hard reset). "
            "Separate from the normal MCP reset; dry run by default; creates a "
            "backup and verifies the result. Only for local SQLite palaces."
        ),
    )
    parser.add_argument("--wing", action="append", required=True, help="Exact wing name to delete (repeatable)")
    parser.add_argument("--db-path", default="", help="Palace database file (otherwise resolved from MEMPAL_DIR; refuses to guess)")
    parser.add_argument("--confirm", action="store_true", help="Execute deletion (requires --plan-hash from the dry run)")
    parser.add_argument("--plan-hash", default="", help="Hash of the exact dry-run plan being confirmed")
    parser.add_argument("--allow-live", action="store_true", help="Proceed even when WAL/SHM files suggest MemPalace is running (not recommended)")
    parser.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
