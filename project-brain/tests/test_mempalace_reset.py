"""Tests for the normal (MCP-based) reset algorithm — scripts/mempalace_reset.py.

Covers the brief's reset requirements: bulk deletion only (no single-drawer
fallback, enforced by the mock lacking delete_drawer), correct pagination,
batch sizes <= 500, partial-failure handling, the wing-disappearance
continuation fix, tunnel/hallway cleanup, preservation of unrelated data,
idempotent re-runs, and MCP-failure blocking.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))
sys.path.insert(0, str(PLUGIN_ROOT / "tests"))

import mempalace_reset as mr  # noqa: E402
from mock_mcp import (  # noqa: E402
    FlakyDeleteDrawers,
    MCPOutage,
    MockPalace,
    PartialFailurePalace,
)


# --- batching -----------------------------------------------------------------

def test_batches_respects_500_limit():
    ids = [f"d{i}" for i in range(1200)]
    chunks = list(mr.batches(ids))
    assert len(chunks) == 3
    assert [len(c) for c in chunks] == [500, 500, 200]
    assert chunks[0][0] == "d0" and chunks[-1][-1] == "d1199"


def test_batches_smaller_than_limit_is_one_batch():
    assert list(mr.batches(["a", "b"])) == [["a", "b"]]


# --- pagination ---------------------------------------------------------------

def test_collect_drawer_ids_paginates_over_multiple_pages():
    palace = MockPalace()
    for i in range(250):
        palace.add_drawer("wiki_ts_a", room="general", drawer_id=f"d{i}")
    enum = mr.collect_drawer_ids(palace, "wiki_ts_a")
    assert len(enum.ids) == 250
    assert enum.pages == 3  # 100 + 100 + 50
    assert enum.duplicates_found == 0


def test_collect_drawer_ids_multiple_rooms():
    palace = MockPalace()
    for i in range(60):
        palace.add_drawer("w", room="r1", drawer_id=f"a{i}")
    for i in range(40):
        palace.add_drawer("w", room="r2", drawer_id=f"b{i}")
    enum = mr.collect_drawer_ids(palace, "w")
    assert sorted(enum.ids) == sorted([f"a{i}" for i in range(60)] + [f"b{i}" for i in range(40)])


def test_collect_drawer_ids_dedupes_and_reports():
    palace = MockPalace()
    palace.add_drawer("w", drawer_id="dup1")
    # Simulate the same ID appearing in two rooms (listing anomaly).
    palace.wings["w"]["general"].append("dup1")
    enum = mr.collect_drawer_ids(palace, "w")
    assert enum.ids == ["dup1"]
    assert enum.duplicates_found == 1


def test_collect_drawer_ids_empty_wing_yields_empty():
    palace = MockPalace()
    enum = mr.collect_drawer_ids(palace, "ghost_wing")
    assert enum.ids == []


def test_collect_drawer_ids_stops_when_total_mismatches():
    palace = MockPalace()
    for i in range(10):
        palace.add_drawer("w", drawer_id=f"d{i}")

    class ShiftingPalace(MockPalace):
        def get_taxonomy(self):
            base = super().get_taxonomy()
            base["wings"][0]["drawer_count"] = 99  # inconsistent report
            return base

    shifting = ShiftingPalace()
    shifting.wings = palace.wings
    shifting.drawers = palace.drawers
    with pytest.raises(mr.ResetBlocked, match="changed during enumeration"):
        mr.collect_drawer_ids(shifting, "w")


def test_collect_drawer_ids_cross_checks_taxonomy_total():
    palace = MockPalace()
    for i in range(120):
        palace.add_drawer("w", drawer_id=f"d{i}")
    enum = mr.collect_drawer_ids(palace, "w")
    assert enum.reported_total == 120


# --- batch result inspection ---------------------------------------------------

def test_inspect_batch_result_parses_success_and_errors():
    result = {
        "results": [
            {"id": "d1", "success": True},
            {"id": "d2", "success": False, "error": "locked"},
        ],
        "count": 3,
        "deleted": 1,
        "errors": [{"id": "d2"}],
        "revisions_deleted": 4,
    }
    outcome = mr.inspect_batch_result(["d1", "d2", "d3"], result)
    assert outcome.ok_ids == ["d1"]
    assert outcome.failed == {"d2": "locked"}
    assert outcome.missing == ["d3"]
    assert outcome.revisions_deleted == 4


def test_inspect_batch_result_revisions_error():
    outcome = mr.inspect_batch_result(["d1"], {"results": [{"id": "d1", "success": True}], "revisions_error": "sidecar busy"})
    assert outcome.revisions_error == "sidecar busy"


# --- bulk deletion ---------------------------------------------------------------

def test_bulk_delete_uses_batch_calls_not_single_drawer():
    palace = MockPalace()
    ids = [palace.add_drawer("w") for _ in range(1200)]
    report = mr.bulk_delete(palace, ids)
    assert report.calls == 3
    assert report.batch_sizes == [500, 500, 200]
    assert len(report.deleted) == 1200
    assert palace.drawer_count("w") == 0
    # The mock has no delete_drawer attribute at all — reaching this point
    # proves no single-drawer call was made.


def test_bulk_delete_single_drawer_still_uses_bulk_tool():
    palace = MockPalace()
    only = palace.add_drawer("w")
    report = mr.bulk_delete(palace, [only])
    assert report.calls == 1 and report.deleted == [only]


def test_bulk_delete_transients_are_retried_bounded():
    palace = MockPalace()
    ids = [palace.add_drawer("w") for _ in range(10)]
    flaky = FlakyDeleteDrawers(palace, fail_first=1)
    report = mr.bulk_delete(flaky, ids)
    assert report.deleted == ids
    assert flaky.calls == 2


def test_bulk_delete_permanent_failure_stops_with_diagnostics():
    palace = MockPalace()
    ids = [palace.add_drawer("w") for _ in range(10)]

    class DeadPalace(MockPalace):
        def delete_drawers(self, drawer_ids):
            raise MCPOutage("palace unreachable")

    dead = DeadPalace()
    dead.wings = palace.wings
    dead.drawers = palace.drawers
    with pytest.raises(mr.ResetBlocked, match="bulk deletion stopped"):
        mr.bulk_delete(dead, ids)


def test_bulk_delete_partial_failure_recorded_not_hidden():
    palace = PartialFailurePalace()
    ids = [palace.add_drawer("w") for _ in range(5)]
    palace.fail_ids = {ids[0]}
    report = mr.bulk_delete(palace, ids)
    assert set(report.deleted) == set(ids) - {ids[0]}
    assert report.failed == {ids[0]: "simulated per-drawer refusal"}


# --- verification & continuation -------------------------------------------------

def test_verify_wing_absent_is_cleared_expected_state():
    palace = MockPalace()
    verification = mr.verify_wing_cleared(palace, "vanished_wing")
    assert verification.cleared is True
    assert verification.wing_absent is True


def test_verify_wing_zero_drawers_is_cleared():
    palace = MockPalace()
    palace.add_wing("w")  # exists but empty
    verification = mr.verify_wing_cleared(palace, "w")
    assert verification.cleared is True
    assert verification.remaining_drawers == 0


def test_verify_wing_with_drawers_not_cleared():
    palace = MockPalace()
    palace.add_drawer("w", drawer_id="survivor")
    verification = mr.verify_wing_cleared(palace, "w")
    assert verification.cleared is False
    assert verification.remaining_drawers == 1


def test_reset_wing_continues_after_wing_disappearance():
    """THE central regression: deleting the last drawers makes the wing vanish;
    that must be success, not an abort."""
    palace = MockPalace()
    for i in range(30):
        palace.add_drawer("wiki_ts_x", drawer_id=f"x{i}")
    result = mr.reset_wing(palace, "wiki_ts_x")
    assert result.cleared is True
    assert result.phase_reached == "verified"
    assert result.verification.wing_absent is True
    assert "wiki_ts_x" not in palace.wings  # implicit wing deletion happened


def test_reset_wing_empty_wing_is_idempotent_success():
    palace = MockPalace()
    result = mr.reset_wing(palace, "already_gone")
    assert result.cleared is True
    assert result.deletion is None or result.deletion.calls == 0


def test_reset_wing_blocks_when_drawers_survive():
    palace = PartialFailurePalace()
    ids = [palace.add_drawer("w") for _ in range(3)]
    palace.fail_ids = set(ids)
    result = mr.reset_wing(palace, "w")
    assert result.cleared is False
    assert "still reports 3 drawer(s)" in result.blocked_reason


# --- graph cleanup ---------------------------------------------------------------

def test_cleanup_graph_deletes_only_in_scope_records():
    palace = MockPalace()
    palace.add_wing("wiki_target")
    palace.add_wing("other_wing")
    palace.add_drawer("other_wing")
    palace.add_tunnel("t1", "wiki_target", "other_wing")
    palace.add_tunnel("t2", "other_wing", "unrelated")
    palace.add_hallway("h1", "wiki_target")
    palace.add_hallway("h2", "other_wing")
    report = mr.cleanup_graph(palace, ["wiki_target"])
    assert "tunnel:t1" in report.deleted
    assert "hallway:h1" in report.deleted
    assert "t2" in palace.tunnels and "h2" in palace.hallways
    assert report.remaining_in_scope == []


def test_cleanup_graph_exact_names_not_normalized():
    """Two distinct wings that normalize identically must not be conflated:
    only the exact requested name's records are deleted."""
    palace = MockPalace()
    palace.add_wing("demo_app")
    palace.add_wing("demo__app")
    palace.add_drawer("demo_app")
    palace.add_drawer("demo__app")
    palace.add_tunnel("t1", "demo_app", "elsewhere")
    palace.add_tunnel("t2", "demo__app", "elsewhere")
    report = mr.cleanup_graph(palace, ["demo_app"])
    assert "tunnel:t1" in report.deleted
    assert "t2" in palace.tunnels


def test_cleanup_graph_surviving_records_after_wing_vanished():
    """Tunnels/hallways can survive drawer deletion — they must still be
    found and cleaned after the wing itself is gone."""
    palace = MockPalace()
    for i in range(3):
        palace.add_drawer("wiki_doomed", drawer_id=f"d{i}")
    palace.add_tunnel("t1", "wiki_doomed", "wiki_survivor")
    palace.add_hallway("h1", "wiki_doomed")
    result = mr.reset_wing(palace, "wiki_doomed")
    assert result.cleared is True
    graph = mr.cleanup_graph(palace, ["wiki_doomed"])
    assert "tunnel:t1" in graph.deleted and "hallway:h1" in graph.deleted


def test_cleanup_graph_failure_tracked_separately():
    palace = MockPalace()
    palace.add_wing("w")
    palace.add_tunnel("t1", "w", "x")

    class TunnelDeleteBroken(MockPalace):
        def delete_tunnel(self, tunnel_id):
            raise MCPOutage("graph service down")

    broken = TunnelDeleteBroken()
    broken.wings = palace.wings
    broken.drawers = palace.drawers
    broken.tunnels = palace.tunnels
    broken.hallways = palace.hallways
    report = mr.cleanup_graph(broken, ["w"])
    assert "tunnel:t1" in report.failed
    assert "t1" in broken.tunnels  # preserved, not silently claimed deleted


# --- full workflow -----------------------------------------------------------------

def test_run_normal_reset_end_to_end_multi_wing():
    """Wiki wing + diary wing + unrelated wing + tunnels + hallways."""
    palace = MockPalace()
    for i in range(1200):  # >2 batches
        palace.add_drawer("wiki_proj_20261026T000000Z", drawer_id=f"w{i}")
    for i in range(3):
        palace.add_drawer("wing_brain_proj", drawer_id=f"b{i}")
    for i in range(7):
        palace.add_drawer("unrelated_wing", drawer_id=f"u{i}")
    palace.add_tunnel("t1", "wiki_proj_20261026T000000Z", "unrelated_wing")
    palace.add_tunnel("t2", "unrelated_wing", "elsewhere")
    palace.add_hallway("h1", "wiki_proj_20261026T000000Z")
    palace.add_hallway("h2", "wing_brain_proj")

    report = mr.run_normal_reset(palace, ["wiki_proj_20261026T000000Z", "wing_brain_proj"])
    assert report.drawer_success is True
    assert report.tunnel_success is True
    assert report.hallway_success is True
    assert report.overall_success is True
    assert palace.drawer_count("unrelated_wing") == 7
    assert "t2" in palace.tunnels
    # deletion calls scale with batches (3 for 1200), not per drawer:
    assert all(w.deletion is None or w.deletion.calls <= 3 for w in report.wings)
    wiki_result = next(w for w in report.wings if w.wing == "wiki_proj_20261026T000000Z")
    assert wiki_result.deletion.batch_sizes == [500, 500, 200]


def test_run_normal_reset_continues_after_first_wing_disappears():
    """The original failure pattern: first wing vanishes mid-reset; the diary
    wing must still be processed."""
    palace = MockPalace()
    for i in range(2):
        palace.add_drawer("wiki_first", drawer_id=f"a{i}")
    for i in range(2):
        palace.add_drawer("wing_diary_second", drawer_id=f"b{i}")
    report = mr.run_normal_reset(palace, ["wiki_first", "wing_diary_second"])
    assert all(w.cleared for w in report.wings)
    assert report.overall_success is True
    assert palace.drawer_count("wing_diary_second") == 0


def test_run_normal_reset_blocked_wing_does_not_block_graph_for_cleared():
    palace = PartialFailurePalace()
    for i in range(2):
        palace.add_drawer("wiki_ok", drawer_id=f"ok{i}")
    for i in range(2):
        palace.add_drawer("wiki_stuck", drawer_id=f"stuck{i}")
    palace.fail_ids = {"stuck0", "stuck1"}
    palace.add_tunnel("t_ok", "wiki_ok", "elsewhere")
    palace.add_tunnel("t_stuck", "wiki_stuck", "elsewhere")
    report = mr.run_normal_reset(palace, ["wiki_ok", "wiki_stuck"])
    assert report.drawer_success is False
    # Cleared wing's graph records were still cleaned:
    assert "t_ok" not in palace.tunnels
    # Stuck wing's records preserved for retry:
    assert "t_stuck" in palace.tunnels
    assert report.overall_success is False


def test_run_normal_reset_mcp_outage_blocks_destructive_phase():
    """A completely unreachable palace must not delete anything and must not
    be reported as success; diagnostics are preserved for the user."""
    palace = MockPalace()
    for i in range(4):
        palace.add_drawer("w", drawer_id=f"d{i}")

    class DownPalace(MockPalace):
        def list_rooms(self, wing=None):
            raise MCPOutage("MCP down")

    down = DownPalace()
    down.wings = palace.wings
    down.drawers = palace.drawers
    down.tunnels = palace.tunnels
    down.hallways = palace.hallways
    report = mr.run_normal_reset(down, ["w"])
    assert report.overall_success is False
    assert report.drawer_success is False
    assert any("MCP down" in b for b in report.blocked)
    assert palace.drawer_count("w") == 4  # nothing was deleted


# --- helper semantics ---------------------------------------------------------

def test_normalize_wing_for_compare_semantics():
    assert mr.normalize_wing_for_compare("Wiki_Demo-App") == "wiki_demo_app"
    assert mr.normalize_wing_for_compare("wing_brain-demo_app") == "wing_brain_demo_app"
    assert mr.normalize_wing_for_compare("_edge_") == "edge"
    # runs are NOT collapsed: distinct names stay distinct keys
    assert mr.normalize_wing_for_compare("demo--app") == "demo__app"
    assert mr.normalize_wing_for_compare("demo_app") == "demo_app"


def test_no_single_drawer_tool_on_protocol():
    """The McpLike protocol must not expose delete_drawer."""
    assert not hasattr(mr.McpLike, "delete_drawer")
    assert hasattr(mr.McpLike, "delete_drawers")
