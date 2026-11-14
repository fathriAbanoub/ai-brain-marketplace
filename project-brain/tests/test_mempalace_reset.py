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

# Seeded record counts derive from PAGE_LIMIT: PAGINATION_TEST_PAGES whole pages
# plus a remainder, so every page is exercised including a partial one, and the
# tests keep testing pagination if PAGE_LIMIT ever changes.
PAGINATION_TEST_PAGES = 2
PAGINATION_TEST_REMAINDER = 50


def test_collect_drawer_ids_paginates_over_multiple_pages():
    palace = MockPalace()
    count = PAGINATION_TEST_PAGES * mr.PAGE_LIMIT + PAGINATION_TEST_REMAINDER
    for i in range(count):
        palace.add_drawer("wiki_ts_a", room="general", drawer_id=f"d{i}")
    enum = mr.collect_drawer_ids(palace, "wiki_ts_a")
    assert len(enum.ids) == count
    assert enum.pages == PAGINATION_TEST_PAGES + 1  # whole pages + the remainder
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
    palace.add_wing("demo-app")
    palace.add_wing("demo_app")
    palace.add_drawer("demo-app")
    palace.add_drawer("demo_app")
    palace.add_tunnel("t1", "demo-app", "elsewhere")
    palace.add_tunnel("t2", "demo_app", "elsewhere")
    # The two names normalize identically (both -> demo_app) but are distinct
    # wings; only the exact confirmed target's records are cleaned.
    assert mr.normalize_wing_for_compare("demo-app") == mr.normalize_wing_for_compare("demo_app")
    report = mr.cleanup_graph(palace, ["demo_app"])
    assert "tunnel:t2" in report.deleted
    # The unconfirmed normalized twin's tunnel remains after cleanup.
    assert "t1" in palace.tunnels


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


def test_cleanup_graph_pages_through_all_hallway_pages():
    """Hallway collection and post-deletion verification must advance through
    every list_hallways page so later-page hallways are cleaned too."""
    palace = MockPalace()
    palace.add_wing("wiki_target")
    palace.add_wing("other_wing")
    palace.add_drawer("other_wing")
    count = PAGINATION_TEST_PAGES * mr.PAGE_LIMIT + PAGINATION_TEST_REMAINDER
    for i in range(count):
        palace.add_hallway(f"h{i}", "wiki_target")
    palace.add_hallway("h_other", "other_wing")
    assert len(palace.hallways) == count + 1
    report = mr.cleanup_graph(palace, ["wiki_target"])
    assert len(report.deleted) == count
    assert report.remaining_in_scope == []
    assert "h_other" in palace.hallways  # out-of-scope record preserved


class ListingOutage:
    """Delegates to a palace but fails the graph listing calls independently.

    fail_tunnels_from_call=N fails only the Nth and later tunnel listings, so
    a test can target the post-deletion verification listing specifically
    while the first (collection) listing succeeds."""

    def __init__(self, palace, fail_tunnels: bool = False, fail_hallways: bool = False,
                 fail_tunnels_from_call: int | None = None):
        self._palace = palace
        self._fail_tunnels = fail_tunnels
        self._fail_hallways = fail_hallways
        self._fail_tunnels_from_call = fail_tunnels_from_call
        self._tunnel_listing_calls = 0

    def __getattr__(self, name):
        return getattr(self._palace, name)

    def list_tunnels(self, wing=None):
        self._tunnel_listing_calls += 1
        from_call = self._fail_tunnels_from_call
        if self._fail_tunnels or (from_call is not None and self._tunnel_listing_calls >= from_call):
            raise MCPOutage("tunnels listing unavailable")
        return self._palace.list_tunnels(wing)

    def list_hallways(self, wing=None, limit=100, offset=0):
        if self._fail_hallways:
            raise MCPOutage("hallways listing unavailable")
        return self._palace.list_hallways(wing, limit, offset)


def test_cleanup_graph_listing_failure_is_reported_not_success():
    """A failed post-deletion re-listing must count as cleanup failure."""
    palace = MockPalace()
    palace.add_wing("w")
    palace.add_drawer("w")
    palace.add_tunnel("t1", "w", "x")
    report = mr.cleanup_graph(ListingOutage(palace, fail_tunnels=True), ["w"])
    assert "<list_tunnels>" in report.failed
    assert "tunnel:t1" not in report.deleted


def test_run_normal_reset_listing_failures_independent():
    """A tunnels-listing failure makes the tunnel postcondition unsuccessful
    while the hallway postcondition is judged on its own listing."""
    palace = MockPalace()
    for i in range(2):
        palace.add_drawer("wiki_w", drawer_id=f"d{i}")
    palace.add_tunnel("t1", "wiki_w", "x")
    palace.add_hallway("h1", "wiki_w")
    report = mr.run_normal_reset(ListingOutage(palace, fail_tunnels=True), ["wiki_w"])
    assert report.drawer_success is True
    assert report.tunnel_success is False
    assert report.hallway_success is True
    assert report.overall_success is False

    palace2 = MockPalace()
    for i in range(2):
        palace2.add_drawer("wiki_w", drawer_id=f"d{i}")
    palace2.add_tunnel("t1", "wiki_w", "x")
    palace2.add_hallway("h1", "wiki_w")
    report2 = mr.run_normal_reset(ListingOutage(palace2, fail_hallways=True), ["wiki_w"])
    assert report2.drawer_success is True
    assert report2.tunnel_success is True
    assert report2.hallway_success is False
    assert report2.overall_success is False


def test_wing_drawer_count_exact_absence_not_twin_substituted():
    """When the exact confirmed wing is absent from list_wings, verification
    reports absence — it never counts a normalized twin's drawers."""
    palace = MockPalace()
    palace.add_wing("wiki-demo-app")
    for i in range(3):
        palace.add_drawer("wiki-demo-app", drawer_id=f"x{i}")
    assert mr.normalize_wing_for_compare("wiki_demo_app") == mr.normalize_wing_for_compare("wiki-demo-app")
    wing_absent, count, evidence = mr._wing_drawer_count(palace, "wiki_demo_app")
    assert wing_absent is True
    assert count == 0


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


# --- CodeRabbit fixes: fail-closed verification listings -----------------------

class _MissingFieldPalace(MockPalace):
    """list_wings / list_tunnels / list_hallways drop their result field, as an
    error-shaped response would (no exception raised)."""

    def list_wings(self) -> dict:
        return {"ok": False}

    def list_tunnels(self, wing=None):
        return {"count": 0}

    def list_hallways(self, wing=None, limit=100, offset=0):
        return {"total": 0}


def test_wing_drawer_count_missing_wings_field_blocked():
    """A list_wings result without its wings field (or with a non-collection
    value) must never read as an empty wing list: an unrecognized listing
    cannot confirm that a wing is absent (ResetBlocked, not cleared)."""
    palace = _MissingFieldPalace()
    palace.add_wing("w")
    palace.add_drawer("w")
    with pytest.raises(mr.ResetBlocked, match="no 'wings' field"):
        mr._wing_drawer_count(palace, "w")

    class NonCollectionWings(MockPalace):
        def list_wings(self) -> dict:
            return {"wings": "oops"}

    with pytest.raises(mr.ResetBlocked, match="non-collection wings"):
        mr._wing_drawer_count(NonCollectionWings(), "w")


def test_wing_drawer_count_explicit_empty_list_confirms_absence():
    """An explicitly returned empty wing collection is a valid listing: the
    exact-name absence check keeps working (empty result is only proof of
    absence when the field itself was returned)."""
    palace = MockPalace()  # no wings -> {"wings": []}
    wing_absent, count, evidence = mr._wing_drawer_count(palace, "wiki_gone")
    assert wing_absent is True
    assert count == 0
    assert "0 wings remain" in evidence


class _FullPageDrawerPalace(MockPalace):
    """list_drawers ignores offset and always returns a full page: a misbehaving
    paginator that would loop forever without the MAX_ENUM_PAGES bound.
    get_taxonomy omits drawer_count so verification falls through to the
    rooms + list_drawers counting loops."""

    def get_taxonomy(self) -> dict:
        return {"wings": [{"wing": w} for w in self.wings]}

    def list_drawers(self, wing, room="", limit=100, offset=0):
        return {"drawers": [{"id": f"d{i}"} for i in range(limit)], "total": 10**9}


def test_wing_drawer_count_pagination_bound_on_both_fallback_loops():
    """Both fallback verification pagination loops (per-room and wing-level
    probe) stop with a failure instead of hanging after deletion."""
    palace = _FullPageDrawerPalace()
    palace.add_wing("w")
    palace.add_drawer("w")
    with pytest.raises(mr.ResetBlocked, match="exceeded"):
        mr._wing_drawer_count(palace, "w")

    class NoRoomsFullPage(_FullPageDrawerPalace):
        def list_rooms(self, wing=None):
            return {"wing": wing, "rooms": []}

    probe = NoRoomsFullPage()
    probe.add_wing("w")
    probe.add_drawer("w")
    with pytest.raises(mr.ResetBlocked, match="exceeded"):
        mr._wing_drawer_count(probe, "w")


def test_verify_wing_cleared_blocked_when_wings_field_missing():
    """verify_wing_cleared propagates the blocked listing instead of marking
    the wing cleared: enumeration works (taxonomy/rooms/drawers), deletion
    runs, but the post-deletion wing listing is unrecognized, so the wing is
    NOT cleared and the reset is not reported as success."""
    palace = _MissingFieldPalace()
    palace.add_wing("w")
    palace.add_drawer("w")
    report = mr.run_normal_reset(palace, ["w"])
    wiki_result = report.wings[0]
    assert wiki_result.cleared is False
    assert "no 'wings' field" in wiki_result.blocked_reason
    assert report.drawer_success is False
    assert report.overall_success is False


def test_collect_graph_records_tunnels_missing_field_is_listing_failure():
    """A tunnel listing without its 'tunnels' field is recorded under
    '<list_tunnels>' instead of being read as an empty listing."""
    palace = _MissingFieldPalace()
    palace.add_wing("w")
    palace.add_drawer("w")
    palace.add_tunnel("t1", "w", "x")
    tunnels, hallways, report = mr.collect_graph_records(palace, ["w"])
    assert tunnels == []
    assert "<list_tunnels>" in report.failed


def test_cleanup_graph_hallways_missing_field_is_failure_not_success():
    """A hallway page without its 'hallways' field fails the listing so
    collection and the post-deletion check cannot pass on an outage."""
    palace = _MissingFieldPalace()
    palace.add_wing("w")
    palace.add_drawer("w")
    palace.add_hallway("h1", "w")
    report = mr.cleanup_graph(palace, ["w"])
    assert report.deleted == []
    assert "<list_hallways>" in report.failed
    assert "h1" in palace.hallways  # nothing was deleted
    full = mr.run_normal_reset(palace, ["w"])
    assert full.hallway_success is False
    assert full.overall_success is False


def test_explicit_empty_graph_listings_still_pass():
    """An explicitly returned empty list keeps the old success path: an empty
    palace result is a valid listing, not an outage."""
    palace = MockPalace()
    palace.add_wing("w")
    palace.add_drawer("w")
    tunnels, hallways, report = mr.collect_graph_records(palace, ["w"])
    assert tunnels == [] and hallways == []
    assert report.failed == {}
    assert report.preserved == 0


# --- nitpick: the verification listing fails, not the first listing ------------

def test_cleanup_graph_fails_post_deletion_verification_listing_only():
    """fail_tunnels_from_call=N fails only the Nth tunnel listing: deletion
    succeeds, the re-listing fails, and the report shows both facts."""
    palace = MockPalace()
    palace.add_wing("w")
    palace.add_drawer("w")
    palace.add_tunnel("t1", "w", "x")
    report = mr.cleanup_graph(ListingOutage(palace, fail_tunnels_from_call=2), ["w"])
    assert "tunnel:t1" in report.deleted
    assert "<list_tunnels>" in report.failed
