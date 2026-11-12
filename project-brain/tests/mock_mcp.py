"""In-memory MemPalace MCP mock for reset-algorithm tests.

Implements ONLY the documented tool surface used by the normal reset
(scripts/mempalace_reset.McpLike). Deliberately NO delete_drawer method:
if any reset code path attempted single-drawer deletion it would raise
AttributeError and fail the suite (Part V §5 safeguard).

Failure injection hooks let tests simulate MCP outages, transient timeouts,
partial batch failures, and mid-flight data changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field


PAGE_LIMIT = 100  # mirror scripts.mempalace_reset.PAGE_LIMIT contract


class MCPOutage(Exception):
    """Simulated MCP/tool failure."""


class TransientTimeout(Exception):
    """Simulated transient failure worth a bounded retry."""


@dataclass
class Tunnel:
    id: str
    source_wing: str
    target_wing: str
    label: str = ""


@dataclass
class Hallway:
    id: str
    wing: str
    peer: str = ""


@dataclass
class MockPalace:
    """Wings are dicts: wing -> room -> list[drawer_id]; drawers: id -> wing."""

    wings: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    drawers: dict[str, str] = field(default_factory=dict)  # drawer_id -> wing
    tunnels: dict[str, Tunnel] = field(default_factory=dict)
    hallways: dict[str, Hallway] = field(default_factory=dict)
    _next_drawer: int = 1

    # --- construction helpers -------------------------------------------------
    def add_wing(self, wing: str, rooms: list[str] | None = None) -> None:
        self.wings.setdefault(wing, {})
        for room in rooms or []:
            self.wings[wing].setdefault(room, [])

    def add_drawer(self, wing: str, room: str = "general", drawer_id: str | None = None) -> str:
        self.add_wing(wing)
        self.wings[wing].setdefault(room, [])
        if drawer_id is None:
            drawer_id = f"d{self._next_drawer}"
            self._next_drawer += 1
        self.wings[wing][room].append(drawer_id)
        self.drawers[drawer_id] = wing
        return drawer_id

    def add_tunnel(self, tunnel_id: str, source_wing: str, target_wing: str, label: str = "") -> Tunnel:
        tunnel = Tunnel(id=tunnel_id, source_wing=source_wing, target_wing=target_wing, label=label)
        self.tunnels[tunnel_id] = tunnel
        return tunnel

    def add_hallway(self, hallway_id: str, wing: str, peer: str = "") -> Hallway:
        hallway = Hallway(id=hallway_id, wing=wing, peer=peer)
        self.hallways[hallway_id] = hallway
        return hallway

    def drawer_count(self, wing: str) -> int:
        return sum(len(ids) for ids in self.wings.get(wing, {}).values())

    # --- MCP tool surface (McpLike) -------------------------------------------
    def status(self) -> dict:
        return {"ok": True, "wings": len(self.wings)}

    def list_wings(self) -> dict:
        # A wing exists only while it has drawers (MemPalace implicit wings).
        return {"wings": [{"wing": w, "drawer_count": self.drawer_count(w)} for w in self.wings if self.drawer_count(w) > 0]}

    def get_taxonomy(self) -> dict:
        return {
            "wings": [
                {"wing": w, "rooms": {r: len(ids) for r, ids in rooms.items()}, "drawer_count": self.drawer_count(w)}
                for w, rooms in self.wings.items()
                if self.drawer_count(w) > 0
            ]
        }

    def list_rooms(self, wing: str | None = None) -> dict:
        rooms = self.wings.get(wing or "", {})
        return {"wing": wing, "rooms": [{"name": r, "count": len(ids)} for r, ids in rooms.items()]}

    def list_drawers(self, wing: str, room: str = "", limit: int = PAGE_LIMIT, offset: int = 0) -> dict:
        ids = list(self.wings.get(wing, {}).get(room, []))
        page = ids[offset : offset + limit]
        return {"wing": wing, "room": room, "drawers": [{"id": i} for i in page], "total": len(ids)}

    def delete_drawers(self, drawer_ids: list[str]) -> dict:
        results = []
        deleted = 0
        for drawer_id in drawer_ids:
            if drawer_id in self.drawers:
                wing = self.drawers.pop(drawer_id)
                rooms = self.wings.get(wing, {})
                for ids in rooms.values():
                    if drawer_id in ids:
                        ids.remove(drawer_id)
                results.append({"id": drawer_id, "success": True})
                deleted += 1
            else:
                results.append({"id": drawer_id, "success": False, "error": "drawer not found"})
        # Drop wings whose last drawer is gone (implicit wing deletion).
        for wing in list(self.wings):
            if self.drawer_count(wing) == 0:
                del self.wings[wing]
        return {
            "results": results,
            "count": len(drawer_ids),
            "deleted": deleted,
            "errors": [r for r in results if not r["success"]],
            "revisions_deleted": 0,
        }

    def list_tunnels(self, wing: str | None = None) -> dict:
        tunnels = [t for t in self.tunnels.values() if wing is None or wing in (t.source_wing, t.target_wing)]
        return {"tunnels": [t.__dict__ for t in tunnels]}

    def delete_tunnel(self, tunnel_id: str) -> dict:
        if tunnel_id in self.tunnels:
            del self.tunnels[tunnel_id]
            return {"tunnel_id": tunnel_id, "deleted": True}
        return {"tunnel_id": tunnel_id, "deleted": False, "error": "tunnel not found"}

    def list_hallways(self, wing: str | None = None, limit: int = 100, offset: int = 0) -> dict:
        hallways = [h for h in self.hallways.values() if wing is None or h.wing == wing]
        return {"hallways": [h.__dict__ for h in hallways]}

    def delete_hallway(self, hallway_id: str) -> dict:
        if hallway_id in self.hallways:
            del self.hallways[hallway_id]
            return {"hallway_id": hallway_id, "deleted": True}
        return {"hallway_id": hallway_id, "deleted": False, "error": "hallway not found"}


class FlakyDeleteDrawers:
    """Wraps a palace; fails the first N delete_drawers calls with a
    transient-style error, then delegates."""

    def __init__(self, palace: MockPalace, fail_first: int = 1):
        self._palace = palace
        self._fail_first = fail_first
        self.calls = 0

    def __getattr__(self, name):  # delegate everything else
        return getattr(self._palace, name)

    def delete_drawers(self, drawer_ids: list[str]) -> dict:
        self.calls += 1
        if self.calls <= self._fail_first:
            raise TransientTimeout("mcp call timed out")
        return self._palace.delete_drawers(drawer_ids)


class PartialFailurePalace(MockPalace):
    """delete_drawers reports per-ID errors for IDs in its failure set and
    leaves those drawers in place (simulates server-side per-drawer refusal
    inside an otherwise-successful batch call)."""

    fail_ids: set[str] = field(default_factory=set)

    def delete_drawers(self, drawer_ids: list[str]) -> dict:
        deletable = [i for i in drawer_ids if i not in self.fail_ids]
        refused = [i for i in drawer_ids if i in self.fail_ids]
        result = super().delete_drawers(deletable)
        for drawer_id in refused:
            result["results"].append({"id": drawer_id, "success": False, "error": "simulated per-drawer refusal"})
        result["count"] = len(drawer_ids)
        result["errors"] = [r for r in result["results"] if not r["success"]]
        return result
