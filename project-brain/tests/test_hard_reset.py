"""Tests for the hard reset command — scripts/hard_reset.py.

All destructive tests run against disposable synthetic SQLite databases built
in tmp_path. Nothing outside tmp_path is ever touched. Covers: successful
deletion, already-absent wing, ambiguous wings, unsupported backend, stale
path, rollback, integrity failure simulation, unrelated wings untouched,
tunnels/hallways tables, revision sidecars, dry-run default, plan-hash
confirmation binding, backup creation, and fail-closed discovery.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

import hard_reset as hr  # noqa: E402


# --- synthetic palace builders ---------------------------------------------------

def make_palace(path: Path, wings: dict[str, int], with_graph: bool = True) -> Path:
    """Create a synthetic MemPalace-like SQLite database.

    Layout (evidence-based shape, introspected at runtime by the tool —
    this builder only provides plausible fixtures for the tests):
      drawers(id INTEGER PRIMARY KEY, wing TEXT, room TEXT, content TEXT)
      chunks(id INTEGER PRIMARY KEY, drawer_id INTEGER, chunk TEXT)
      tunnels(id INTEGER PRIMARY KEY, source_wing TEXT, target_wing TEXT)
      hallways(id INTEGER PRIMARY KEY, wing TEXT, peer TEXT)
    """
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE drawers (id INTEGER PRIMARY KEY, wing TEXT, room TEXT, content TEXT);
        CREATE TABLE chunks (id INTEGER PRIMARY KEY, drawer_id INTEGER, chunk TEXT);
        """
    )
    if with_graph:
        conn.executescript(
            """
            CREATE TABLE tunnels (id INTEGER PRIMARY KEY, source_wing TEXT, target_wing TEXT);
            CREATE TABLE hallways (id INTEGER PRIMARY KEY, wing TEXT, peer TEXT);
            """
        )
    for wing, count in wings.items():
        for i in range(count):
            cur = conn.execute(
                "INSERT INTO drawers (wing, room, content) VALUES (?, 'general', ?)",
                (wing, f"{wing} content {i}"),
            )
            conn.execute("INSERT INTO chunks (drawer_id, chunk) VALUES (?, ?)", (cur.lastrowid, "chunk"))
    if with_graph:
        if "wiki_target" in wings:
            conn.execute("INSERT INTO tunnels (source_wing, target_wing) VALUES ('wiki_target', 'wiki_other')")
            conn.execute("INSERT INTO hallways (wing, peer) VALUES ('wiki_target', 'peer1')")
        if "wiki_other" in wings:
            conn.execute("INSERT INTO tunnels (source_wing, target_wing) VALUES ('wiki_other', 'wiki_third')")
            conn.execute("INSERT INTO hallways (wing, peer) VALUES ('wiki_other', 'peer2')")
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def palace(tmp_path: Path) -> Path:
    return make_palace(
        tmp_path / "palace.db",
        {"wiki_target": 40, "wiki_other": 7, "solo_wing": 2},
    )


def run_cmd(*argv):
    return hr.main(list(argv))


def drawer_count(db: Path, wing: str) -> int:
    conn = sqlite3.connect(db)
    n = conn.execute("SELECT COUNT(*) FROM drawers WHERE wing=?", (wing,)).fetchone()[0]
    conn.close()
    return n


# --- discovery -----------------------------------------------------------------

def test_discovery_refuses_without_db_path_or_env(palace, monkeypatch):
    monkeypatch.delenv("MEMPAL_DIR", raising=False)
    with pytest.raises(hr.HardResetRefused, match="cannot determine"):
        hr.discover_database("")


def test_discovery_uses_mempal_dir_file(monkeypatch, tmp_path):
    db = tmp_path / "palace.db"
    make_palace(db, {"w": 1})
    monkeypatch.setenv("MEMPAL_DIR", str(db))
    assert hr.discover_database("") == db.resolve()


def test_discovery_mempal_dir_single_db(monkeypatch, tmp_path):
    (tmp_path / "palace.db").write_bytes(hr.SQLITE_HEADER + b"x" * 100)
    monkeypatch.setenv("MEMPAL_DIR", str(tmp_path))
    assert hr.discover_database("").name == "palace.db"


def test_discovery_refuses_ambiguous_dir(monkeypatch, tmp_path):
    (tmp_path / "a.db").write_bytes(hr.SQLITE_HEADER + b"x" * 100)
    (tmp_path / "b.db").write_bytes(hr.SQLITE_HEADER + b"x" * 100)
    monkeypatch.setenv("MEMPAL_DIR", str(tmp_path))
    with pytest.raises(hr.HardResetRefused, match="2 database candidates"):
        hr.discover_database("")


def test_discovery_refuses_stale_path(monkeypatch, tmp_path):
    monkeypatch.setenv("MEMPAL_DIR", str(tmp_path / "does-not-exist"))
    with pytest.raises(hr.HardResetRefused):
        hr.discover_database("")


# --- dry run / plan -----------------------------------------------------------------

def test_dry_run_default_touches_nothing(palace, capsys):
    rc = run_cmd("--wing", "wiki_target", "--db-path", str(palace))
    assert rc == 0
    out = capsys.readouterr().out
    assert "Dry run only" in out
    assert drawer_count(palace, "wiki_target") == 40  # untouched


def test_plan_counts_and_preservation(palace, capsys):
    rc = run_cmd("--wing", "wiki_target", "--db-path", str(palace))
    out = capsys.readouterr().out
    assert "wiki_target" in out
    assert "40" in out
    assert "preserved" in out and "wiki_other" in out and "solo_wing" in out


def test_confirm_requires_plan_hash(palace):
    rc = run_cmd("--wing", "wiki_target", "--db-path", str(palace), "--confirm")
    assert rc == 2  # refused


def test_confirm_rejects_stale_plan_hash(palace):
    rc = run_cmd(
        "--wing", "wiki_target", "--db-path", str(palace),
        "--confirm", "--plan-hash", "deadbeefdeadbeef",
    )
    assert rc == 2


# --- successful deletion -----------------------------------------------------------------

def test_successful_hard_reset(palace, capsys):
    plan = hr.build_plan(palace, ["wiki_target"])
    rc = run_cmd(
        "--wing", "wiki_target", "--db-path", str(palace),
        "--confirm", "--plan-hash", hr.plan_hash(plan),
    )
    assert rc == 0, capsys.readouterr()
    assert drawer_count(palace, "wiki_target") == 0
    # Chunks of deleted drawers removed; other wings untouched.
    conn = sqlite3.connect(palace)
    orphan_chunks = conn.execute(
        "SELECT COUNT(*) FROM chunks WHERE drawer_id NOT IN (SELECT id FROM drawers)"
    ).fetchone()[0]
    conn.close()
    assert orphan_chunks == 0
    assert drawer_count(palace, "wiki_other") == 7
    assert drawer_count(palace, "solo_wing") == 2
    # Tunnels/hallways of the deleted wing removed, others preserved.
    conn = sqlite3.connect(palace)
    remaining_t = conn.execute("SELECT source_wing FROM tunnels").fetchall()
    remaining_h = conn.execute("SELECT wing FROM hallways").fetchall()
    conn.close()
    assert ("wiki_target",) not in remaining_t
    assert ("wiki_other",) in remaining_t
    assert ("wiki_target",) not in remaining_h
    assert ("wiki_other",) in remaining_h
    out = capsys.readouterr().out
    assert "integrity_check: ok" in out
    assert "mempalace_reconnect" in out


def test_backup_created(palace):
    plan = hr.build_plan(palace, ["wiki_target"])
    rc = run_cmd(
        "--wing", "wiki_target", "--db-path", str(palace),
        "--confirm", "--plan-hash", hr.plan_hash(plan),
    )
    assert rc == 0
    backups = list(palace.parent.glob("palace.db.hard-reset-backup-*"))
    assert len(backups) == 1
    assert (backups[0] / "palace.db").exists()


def test_already_absent_wing_succeeds(palace):
    plan = hr.build_plan(palace, ["wiki_never_existed"])
    rc = run_cmd(
        "--wing", "wiki_never_existed", "--db-path", str(palace),
        "--confirm", "--plan-hash", hr.plan_hash(plan),
    )
    assert rc == 0
    assert drawer_count(palace, "wiki_target") == 40


def test_ambiguous_wings_refused(palace):
    with pytest.raises(hr.HardResetRefused, match="ambiguous"):
        hr.build_plan(palace, ["demo_app", "demo-app"])


# --- unsupported layouts / backends ------------------------------------------------

def test_unsupported_backend_refused(tmp_path):
    fake = tmp_path / "palace.db"
    fake.write_bytes(b"NOT A DATABASE AT ALL........")
    with pytest.raises(hr.HardResetRefused, match="not an SQLite database"):
        hr.build_plan(fake, ["w"])


def test_unsupported_schema_refused(tmp_path):
    db = tmp_path / "palace.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE things (a TEXT, b TEXT)")
    conn.commit()
    conn.close()
    with pytest.raises(hr.HardResetRefused, match="no wing-tagged table"):
        hr.build_plan(db, ["w"])


def test_chromadb_layout_refused(tmp_path):
    """Default ChromaDB palaces are refused fail-closed: metadata rows must
    never be deleted directly in SQLite (vectors live in HNSW segment files)."""
    db = tmp_path / "palace.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE collections (id TEXT PRIMARY KEY, name TEXT);
        CREATE TABLE embeddings (id TEXT PRIMARY KEY, segment_id TEXT);
        CREATE TABLE embedding_metadata (id TEXT, key TEXT, value TEXT);
        CREATE TABLE segments (id TEXT PRIMARY KEY, type TEXT);
        """
    )
    conn.execute("INSERT INTO embedding_metadata VALUES ('e1', 'wing', 'wiki_target')")
    conn.commit()
    conn.close()
    with pytest.raises(hr.HardResetRefused, match="ChromaDB"):
        hr.build_plan(db, ["wiki_target"])
    # Nothing was deleted.
    conn = sqlite3.connect(db)
    n = conn.execute("SELECT COUNT(*) FROM embedding_metadata").fetchone()[0]
    conn.close()
    assert n == 1


def test_name_keyed_registry_table_reset(tmp_path):
    """A wings registry keyed by 'name' resets without a missing-column error."""
    db = make_palace(tmp_path / "palace.db", {"wiki_target": 3, "wiki_other": 2})
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE wings (name TEXT PRIMARY KEY)")
    conn.execute("INSERT INTO wings (name) VALUES ('wiki_target'), ('wiki_other')")
    conn.commit()
    conn.close()
    plan = hr.build_plan(db, ["wiki_target"])
    rc = run_cmd(
        "--wing", "wiki_target", "--db-path", str(db),
        "--confirm", "--plan-hash", hr.plan_hash(plan),
    )
    assert rc == 0
    conn = sqlite3.connect(db)
    names = [r[0] for r in conn.execute("SELECT name FROM wings").fetchall()]
    conn.close()
    assert names == ["wiki_other"]


def test_non_sqlite_explicit_path_refused(tmp_path):
    notadb = tmp_path / "whatever.bin"
    notadb.write_bytes(b"\x00\x01\x02\x03")
    with pytest.raises(hr.HardResetRefused):
        hr.build_plan(notadb, ["w"])


# --- rollback / integrity -------------------------------------------------------

def test_rollback_on_failure(palace, monkeypatch, capsys):
    plan = hr.build_plan(palace, ["wiki_target"])

    def chunks_count(db: Path, wing: str) -> int:
        conn = sqlite3.connect(db)
        n = conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE drawer_id IN "
            "(SELECT id FROM drawers WHERE wing=?)", (wing,)
        ).fetchone()[0]
        conn.close()
        return n

    assert chunks_count(palace, "wiki_target") == 40
    # Do REAL partial work first: delete the target wing's chunks, then fail.
    def failing_execute(conn, plan_, registry, registry_key):
        conn.execute(
            "DELETE FROM chunks WHERE drawer_id IN "
            "(SELECT id FROM drawers WHERE wing=?)", ("wiki_target",)
        )
        raise sqlite3.DatabaseError("simulated mid-transaction failure")

    monkeypatch.setattr(hr, "execute_deletions", failing_execute)
    rc = run_cmd(
        "--wing", "wiki_target", "--db-path", str(palace),
        "--confirm", "--plan-hash", hr.plan_hash(plan),
    )
    assert rc == 1
    # Rollback: the deleted chunks are restored and everything is as before.
    assert chunks_count(palace, "wiki_target") == 40
    assert drawer_count(palace, "wiki_target") == 40
    out = capsys.readouterr()
    assert "rolled back" in out.err
    assert "Backup preserved" in out.err


def test_integrity_failure_inside_transaction_rolls_back(palace, monkeypatch):
    plan = hr.build_plan(palace, ["wiki_target"])
    # Keep the real execute_deletions: the transaction performs actual
    # deletions; only the integrity check result is faked to fail.
    # Corrupt integrity_check result by faking the connection check.
    real_connect = sqlite3.connect

    class FakeConn:
        def __init__(self, real):
            object.__setattr__(self, "_real", real)

        def execute(self, sql, *a, **k):
            if "integrity_check" in sql:
                class R:
                    def fetchone(self):
                        return ["corrupted page"]

                return R()
            return self._real.execute(sql, *a, **k)

        def __getattr__(self, name):
            return getattr(self._real, name)

        def __setattr__(self, name, value):
            setattr(self._real, name, value)

    def fake_connect(*a, **k):
        return FakeConn(real_connect(*a, **k))

    monkeypatch.setattr(hr.sqlite3, "connect", fake_connect)
    rc = run_cmd(
        "--wing", "wiki_target", "--db-path", str(palace),
        "--confirm", "--plan-hash", hr.plan_hash(plan),
    )
    assert rc == 1
    assert drawer_count(palace, "wiki_target") == 40  # rolled back


def test_live_server_guard(palace, monkeypatch):
    plan = hr.build_plan(palace, ["wiki_target"])
    (palace.parent / (palace.name + "-wal")).write_bytes(b"")
    (palace.parent / (palace.name + "-shm")).write_bytes(b"")
    rc = run_cmd(
        "--wing", "wiki_target", "--db-path", str(palace),
        "--confirm", "--plan-hash", hr.plan_hash(plan),
    )
    assert rc == 2  # refused without --allow-live
    assert drawer_count(palace, "wiki_target") == 40


# --- revision sidecars ----------------------------------------------------------

def test_revision_sidecar_filtered_atomically(palace):
    sidecar = palace.parent / "palace.db.revisions.jsonl"
    lines = [
        json.dumps({"drawer_id": 1, "wing": "wiki_target", "op": "write"}),
        json.dumps({"drawer_id": 2, "wing": "wiki_other", "op": "write"}),
        json.dumps({"drawer_id": 3, "wing": "wiki_target", "op": "delete"}),
    ]
    sidecar.write_text("\n".join(lines) + "\n", encoding="utf-8")
    plan = hr.build_plan(palace, ["wiki_target"])
    assert plan.sidecars and plan.sidecars[0].affected_lines == 2
    rc = run_cmd(
        "--wing", "wiki_target", "--db-path", str(palace),
        "--confirm", "--plan-hash", hr.plan_hash(plan),
    )
    assert rc == 0
    kept = [json.loads(l) for l in sidecar.read_text().splitlines() if l.strip()]
    assert len(kept) == 1 and kept[0]["wing"] == "wiki_other"
    # Backup contains the original sidecar.
    backups = list(palace.parent.glob("palace.db.hard-reset-backup-*"))
    assert (backups[0] / "palace.db.revisions.jsonl").exists()


def test_multi_wing_hard_reset(palace):
    plan = hr.build_plan(palace, ["wiki_target", "wiki_other"])
    rc = run_cmd(
        "--wing", "wiki_target", "--wing", "wiki_other",
        "--db-path", str(palace),
        "--confirm", "--plan-hash", hr.plan_hash(plan),
    )
    assert rc == 0
    assert drawer_count(palace, "wiki_target") == 0
    assert drawer_count(palace, "wiki_other") == 0
    assert drawer_count(palace, "solo_wing") == 2


# --- CodeRabbit fix: name-keyed registry rows are part of the plan --------------

def test_name_keyed_registry_in_plan_hash_and_verify(tmp_path):
    """A registry keyed by 'name' is absent from plan.tables but its rows for
    the confirmed wings are deleted: they must be counted in affected rows and
    the plan hash, and verified after deletion."""
    db = make_palace(tmp_path / "palace.db", {"wiki_target": 3, "wiki_other": 2})
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE wings (name TEXT PRIMARY KEY)")
    conn.execute("INSERT INTO wings (name) VALUES ('wiki_target'), ('wiki_other')")
    conn.commit()
    conn.close()
    # The baseline plan targets BOTH wings and is built BEFORE the registry
    # row is inserted: plan_hash covers plan.wings, so only a same-wings
    # comparison isolates the registry change under test.
    wings = ["wiki_target", "wiki_target2"]
    plan = hr.build_plan(db, wings)
    assert plan.registry_table == "wings"
    assert plan.registry_key == "name"
    assert plan.registry_row_count == 1
    assert plan.affected_rows() == sum(t.row_count for t in plan.tables) + 1
    # The registry is part of the confirmed hash: adding a row for ANOTHER
    # target wing changes the hash, so stale confirmations are refused.
    hash_before = hr.plan_hash(plan)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO wings (name) VALUES ('wiki_target2')")
    conn.commit()
    conn.close()
    plan2 = hr.build_plan(db, wings)
    assert hr.plan_hash(plan2) != hash_before
    # Post-deletion verification: the registry rows are gone.
    backup = hr.make_backup(plan)
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("BEGIN IMMEDIATE")
        registry, registry_key = hr.wing_registry_table(conn)
        hr.execute_deletions(conn, plan, registry, registry_key)
        conn.commit()
    finally:
        conn.close()
    ok, problems = hr.verify_result(plan, backup)
    assert ok, problems


def test_name_keyed_registry_survivor_fails_verification(tmp_path):
    """If the registry row somehow survives (a partial deletion), verify_result
    must report it — the reset may not be declared successful."""
    db = make_palace(tmp_path / "palace.db", {"wiki_target": 2, "wiki_other": 1})
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE wings (name TEXT PRIMARY KEY)")
    conn.execute("INSERT INTO wings (name) VALUES ('wiki_target'), ('wiki_other')")
    conn.commit()
    conn.close()
    plan = hr.build_plan(db, ["wiki_target"])
    backup = hr.make_backup(plan)
    # Simulate a deletion run that skipped the registry delete.
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("BEGIN IMMEDIATE")
        for table_plan in plan.tables:
            if table_plan.role != "wing-tagged" or table_plan.row_count == 0:
                continue
            predicate = " OR ".join(
                f'"{col}" IN ({",".join("?" for _ in plan.wings)})' for col in table_plan.wing_columns
            )
            conn.execute(f'DELETE FROM "{table_plan.name}" WHERE {predicate}',
                         plan.wings * len(table_plan.wing_columns))
        conn.commit()
    finally:
        conn.close()
    ok, problems = hr.verify_result(plan, backup)
    assert not ok
    assert any("registry row(s) remain" in p for p in problems)


def test_wing_tagged_registry_is_not_double_counted(tmp_path):
    """A wings registry that carries a wing column is already wing-tagged in
    plan.tables: its rows are counted once (no registry_row_count duplication)."""
    db = make_palace(tmp_path / "palace.db", {"wiki_target": 2, "wiki_other": 1})
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE wings (name TEXT PRIMARY KEY, wing TEXT)")
    conn.execute("INSERT INTO wings (name, wing) VALUES ('w-registry', 'wiki_target')")
    conn.commit()
    conn.close()
    plan = hr.build_plan(db, ["wiki_target"])
    assert plan.registry_row_count == 0
    assert plan.registry_table == ""  # not re-registered as a name-keyed registry
    planned = [t for t in plan.tables if t.name == "wings"]
    assert len(planned) == 1 and planned[0].role == "wing-tagged"
    expected = sum(t.row_count for t in plan.tables)
    assert plan.affected_rows() == expected
