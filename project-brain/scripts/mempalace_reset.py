#!/usr/bin/env python3
"""Normal (MCP-based) MemPalace reset algorithm — single source of truth.

The /project-brain:reset skill executes MemPalace operations through MCP tools
that live in the agent session, not in a subprocess. This module encodes the
same algorithm in testable Python so the batching, pagination, verification,
continuation, and graph-cleanup behavior is pinned by unit tests instead of
by prose alone. The skill's steps mirror these functions step for step.

Contract highlights (verified against MemPalace 3.11.0, see
skills/brain/references/mempalace-tools.md):

- mempalace_list_drawers: max page size 100 (limit/offset pagination).
- mempalace_delete_drawers: 1..500 drawer IDs per call; returns per-ID
  results, count/deleted/errors, and revisions_deleted/revisions_error.
  Individual IDs may fail while the batch call itself succeeds.
- mempalace_delete_drawer (single) is PROHIBITED in the reset path. This
  module never calls it; the mock used in tests does not even implement it,
  so any accidental call raises AttributeError and fails the suite.
- Tunnels and hallways are deleted individually (delete_tunnel /
  delete_hallway). There is no bulk graph-deletion tool; do not invent one.

The MCP interface is duck-typed (McpLike below) so tests inject an in-memory
mock and a future CLI bridge can inject the real client without changes.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Iterator, Protocol

from scaffold_brain import (  # wing naming is MemPalace's convention — defined once
    WING_SEPARATOR,
    WING_TS_FORMAT,
    WIKI_WING_PREFIX,
    diary_wing_for_agent,
)

# --- documented interface limits (keep in sync with mempalace-tools.md) -------
MAX_BATCH = 500          # mempalace_delete_drawers accepts 1..500 IDs
PAGE_LIMIT = 100         # mempalace_list_drawers documented maximum page size
MAX_ENUM_PAGES = 10000   # safety bound against a misbehaving paginator
MAX_RETRIES = 2          # bounded retries for TRANSIENT failures only
RETRY_WAIT_SECONDS = 0.0  # tests patch this; real callers may sleep

DELETE_DRAWERS = "mempalace_delete_drawers"
DELETE_DRAWER = "mempalace_delete_drawer"  # referenced only for diagnostics


class ResetBlocked(Exception):
    """The destructive phase must stop; diagnostics are preserved.

    Raised when a safe, consistent target set cannot be established or when
    a phase fails in a way that makes later destructive steps unsafe. It is
    NOT raised for an expected wing disappearance — that is success.
    """


class McpLike(Protocol):
    """Minimal MemPalace MCP surface used by the reset algorithm.

    Implementations provide the documented tools. NOTE: there is
    deliberately NO delete_drawer method on this protocol — the reset path
    has no single-drawer deletion capability by construction.
    """

    def status(self) -> dict: ...
    def list_wings(self) -> dict: ...
    def get_taxonomy(self) -> dict: ...
    def list_rooms(self, wing: str) -> dict: ...
    def list_drawers(self, wing: str, room: str, limit: int, offset: int) -> dict: ...
    def delete_drawers(self, drawer_ids: list[str]) -> dict: ...
    def list_tunnels(self, wing: str | None = None) -> dict: ...
    def delete_tunnel(self, tunnel_id: str) -> dict: ...
    def list_hallways(self, wing: str | None = None, limit: int = 100, offset: int = 0) -> dict: ...
    def delete_hallway(self, hallway_id: str) -> dict: ...


# --------------------------------------------------------------------------
# Generic helpers
# --------------------------------------------------------------------------

def batches(items: list[str], size: int = MAX_BATCH) -> Iterator[list[str]]:
    """Yield consecutive chunks of at most `size` items."""
    if size < 1:
        raise ValueError("batch size must be >= 1")
    for i in range(0, len(items), size):
        yield items[i : i + size]


def dedupe(ids: Iterable[str]) -> tuple[list[str], int]:
    """Order-preserving dedupe. Returns (unique_ids, duplicate_count)."""
    seen: set[str] = set()
    unique: list[str] = []
    duplicates = 0
    for item in ids:
        if item in seen:
            duplicates += 1
            continue
        seen.add(item)
        unique.append(item)
    return unique, duplicates


def normalize_wing_for_compare(name: str) -> str:
    """MemPalace's wing comparison form (config.normalize_wing_name):
    lowercase, '-' and ' ' mapped to '_', edge separators stripped.

    NOTE: runs of separators are NOT collapsed here — that matches
    normalize_wing_name, and two distinct wings ('demo--app' vs 'demo_app')
    may normalize to different keys ('demo__app' vs 'demo_app'). Normalized
    equality is candidate DISCOVERY, never proof of identity; see
    skills/reset/SKILL.md Step 2.
    """
    return name.strip().lower().replace(" ", "_").replace("-", "_").strip("_")


def _unwrap(result: Any, key: str) -> Any:
    """MCP results may arrive as {key: ...} or wrapped in data/content."""
    if isinstance(result, dict):
        if key in result:
            return result[key]
        data = result.get("data") or result.get("content") or {}
        if isinstance(data, dict) and key in data:
            return data[key]
    return None


def _transient(exc: Exception) -> bool:
    """Classify an exception as transient (worth a bounded retry)."""
    text = f"{type(exc).__name__}: {exc}".lower()
    markers = ("timeout", "timed out", "temporarily", "unavailable", "connection", "locked")
    return any(m in text for m in markers)


def call_with_retry(fn: Callable[[], Any], what: str, retries: int = MAX_RETRIES) -> Any:
    """Call fn with bounded retries for transient failures; else ResetBlocked."""
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — MCP clients raise anything
            last = exc
            if not _transient(exc) or attempt == retries:
                break
            if RETRY_WAIT_SECONDS:
                time.sleep(RETRY_WAIT_SECONDS)
    raise ResetBlocked(f"{what} failed after {retries + 1} attempt(s): {last}")


# --------------------------------------------------------------------------
# Wing classification (pure: no MCP calls, no file reads).
#
# The reset skill's Step 2 delegates candidate discovery, name normalization,
# wing classes, collisions, and the A/B/C outcome here. The rationale for the
# classes lives in skills/brain/references/wing-ownership.md, which names
# these constants so script/doc drift is checkable.
# --------------------------------------------------------------------------

# Class labels, in first-match-wins order (keep in sync with wing-ownership.md).
CLASS_BRAIN_WIKI = "brain wiki wing"
CLASS_BRAIN_DIARY = "brain diary wing"
CLASS_ORPHAN_CANDIDATE = "orphan candidate"
CLASS_DIRECTORY_DERIVED = "directory-derived wing"
CLASS_SESSION_OR_PATH = "session or path wing"
CLASS_OTHER_DIARY = "other diary"
CLASS_OTHER = "other"

# Outcomes: A beats B beats C. A collision among brain-class rows is reported
# as a flag that forces a per-wing question; it never changes the letter.
OUTCOME_A = "A"
OUTCOME_B = "B"
OUTCOME_C = "C"
OUTCOME_MEANINGS = {
    OUTCOME_A: "a recorded wing of this brain exists in the palace — run the normal "
               "flow on the brain wiki and brain diary wings the user confirms",
    OUTCOME_B: "the recorded wiki wing is absent, but orphan candidates exist — show "
               "them as possible orphans of this brain and ask which exact wings belong",
    OUTCOME_C: "nothing brain-owned was found in the palace — still run the "
               "stale-record check and ask exactly one yes/no for the local-only reset",
}

FLAG_COLLISION = "normalized collision"

# MemPalace's own generic transcript wings (wing-ownership.md, "session wing").
GENERIC_SESSION_WINGS = ("sessions", "wing_sessions")

# Diary wings are wing_<agent> (scaffold_brain.diary_wing_for_agent); the
# scaffold keeps that prefix inline, so compose it here the same way.
DIARY_WING_PREFIX = "wing" + WING_SEPARATOR

# strftime field widths, used to build the orphan-scan pattern from the
# scaffold's WING_TS_FORMAT instead of retyping the format as a regex.
_STRFTIME_WIDTHS = {"%Y": 4, "%m": 2, "%d": 2, "%H": 2, "%M": 2, "%S": 2, "%f": 6}


def _strftime_pattern(fmt: str) -> str:
    """Compile a fixed-width strftime format into a regex over a normalized
    (lowercased) wing name, e.g. WING_TS_FORMAT -> r'\\d{8}t\\d{6}z'."""
    return "".join(
        rf"\d{{{_STRFTIME_WIDTHS[p]}}}" if p in _STRFTIME_WIDTHS else re.escape(p.lower())
        for p in re.split(r"(%.)", fmt)
    )


# Higher-precision collision form (scaffold_brain.generate_wiki_wing_name):
# WING_TS_FORMAT with microseconds before the trailing Z.
_WING_TS_MICRO_FORMAT = WING_TS_FORMAT.replace("%SZ", "%S%fZ")
_WIKI_TS_TAIL = (
    f"(?:{_strftime_pattern(_WING_TS_MICRO_FORMAT)}|{_strftime_pattern(WING_TS_FORMAT)})"
)

# Wiki-family forms (scaffold_brain.generate_wiki_wing_name plus the legacy
# bare names): wiki_<slug> | wiki_<slug>_<timestamp> | wiki_<slug>_<ts>_<n>.
# The legacy hyphenated form wiki-<slug> normalizes to wiki_<slug>, so one
# pattern over normalized names covers both bare forms.
_WIKI_FAMILY_RE = re.compile(
    rf"^{re.escape(WIKI_WING_PREFIX)}(?P<slug>.+?)"
    rf"(?:{WING_SEPARATOR}{_WIKI_TS_TAIL}(?:{WING_SEPARATOR}\d+)?)?$"
)


@dataclass
class WingRow:
    """One actual wing with its classification (see classify_wings)."""

    wing: str
    drawers: int
    normalized: str
    wing_class: str
    flags: list[str] = field(default_factory=list)


@dataclass
class WingClassification:
    """One row per actual wing, plus the A/B/C outcome and the scan slug."""

    rows: list[WingRow]
    outcome: str
    orphan_slug: str | None


def _orphan_slug_for(recorded_norm: str | None, project_dir_name: str) -> str | None:
    """The slug the orphan scan matches against: from the recorded wiki wing
    (wiki prefix and timestamp/collision tail stripped) when it parses as a
    wiki-family name, else from the normalized project directory name."""
    if recorded_norm:
        match = _WIKI_FAMILY_RE.match(recorded_norm)
        if match:
            return match.group("slug")
    normalized_dir = normalize_wing_for_compare(project_dir_name)
    return normalized_dir or None


def classify_wings(
    wings: dict[str, int],
    recorded_wiki_wing: str | None,
    recorded_diary_agent: str | None,
    project_dir_name: str,
) -> WingClassification:
    """Classify actual palace wings against the brain's recorded identity.

    Inputs: the wing map (name -> drawer count) as returned by
    mempalace_list_wings, the recorded wiki wing and diary agent from
    .brain/CLAUDE.md (either may be absent = None), and the project directory
    name. Returns one row per actual wing plus an outcome.

    Classes, first match wins, compared with normalize_wing_for_compare
    (equality means equal normalized strings, never prefix or substring):
    brain wiki wing, brain diary wing, orphan candidate, directory-derived
    wing, session or path wing, other diary, other. Several actual wings may
    normalize to the same key; each keeps its own row and all rows sharing a
    key are flagged (FLAG_COLLISION) — never collapsed.
    """
    recorded_norm = (
        normalize_wing_for_compare(recorded_wiki_wing) if recorded_wiki_wing else None
    )
    diary_norm = (
        normalize_wing_for_compare(diary_wing_for_agent(recorded_diary_agent))
        if recorded_diary_agent
        else None
    )
    dir_norm = normalize_wing_for_compare(project_dir_name)
    orphan_slug = _orphan_slug_for(recorded_norm, project_dir_name)
    # wiki_<slug> optionally followed by _<timestamp> and a numeric _<n>: a
    # wing without the wiki_ prefix can never match (the prefix is anchored).
    orphan_re = (
        re.compile(
            rf"^{re.escape(WIKI_WING_PREFIX)}{re.escape(orphan_slug)}"
            rf"(?:{WING_SEPARATOR}{_WIKI_TS_TAIL}(?:{WING_SEPARATOR}\d+)?)?$"
        )
        if orphan_slug
        else None
    )

    rows: list[WingRow] = []
    for name, drawers in wings.items():
        normalized = normalize_wing_for_compare(name)
        if recorded_norm is not None and normalized == recorded_norm:
            wing_class = CLASS_BRAIN_WIKI
        elif diary_norm is not None and normalized == diary_norm:
            wing_class = CLASS_BRAIN_DIARY
        elif orphan_re is not None and orphan_re.match(normalized):
            wing_class = CLASS_ORPHAN_CANDIDATE
        elif dir_norm and normalized == dir_norm:
            wing_class = CLASS_DIRECTORY_DERIVED
        elif name.startswith("-") or normalized in GENERIC_SESSION_WINGS:
            # Hyphen test on the RAW name: normalization strips edge separators.
            wing_class = CLASS_SESSION_OR_PATH
        elif normalized.startswith(DIARY_WING_PREFIX):
            wing_class = CLASS_OTHER_DIARY
        else:
            wing_class = CLASS_OTHER
        rows.append(WingRow(wing=name, drawers=drawers, normalized=normalized, wing_class=wing_class))

    by_key: dict[str, list[WingRow]] = {}
    for row in rows:
        by_key.setdefault(row.normalized, []).append(row)
    for group in by_key.values():
        if len(group) > 1:
            for row in group:
                row.flags.append(FLAG_COLLISION)

    classes = {row.wing_class for row in rows}
    if CLASS_BRAIN_WIKI in classes or CLASS_BRAIN_DIARY in classes:
        outcome = OUTCOME_A
    elif CLASS_ORPHAN_CANDIDATE in classes:
        outcome = OUTCOME_B
    else:
        outcome = OUTCOME_C
    return WingClassification(rows=rows, outcome=outcome, orphan_slug=orphan_slug)


# --------------------------------------------------------------------------
# Phase 1: enumerate drawer IDs with correct pagination
# --------------------------------------------------------------------------

@dataclass
class Enumeration:
    wing: str
    ids: list[str]
    duplicates_found: int = 0
    pages: int = 0
    reported_total: int | None = None
    notes: list[str] = field(default_factory=list)


def collect_drawer_ids(mcp: McpLike, wing: str, rooms: list[str] | None = None) -> Enumeration:
    """Collect every drawer ID of `wing` with page-size-100 pagination.

    - Paginates each room until a page returns fewer than the requested limit.
    - Stops with ResetBlocked if pagination exceeds the safety bound or a
      page violates the contract (more items than requested).
    - Dedupes IDs (order-preserving) and reports duplicate count.
    - Cross-checks the collected count against the taxonomy's reported total
      for the wing when the taxonomy exposes one; a mismatch stops the
      destructive phase (the listing changed under us or drifts from the
      reported state).
    """
    if rooms is None:
        rooms_result = call_with_retry(lambda: mcp.list_rooms(wing=wing), f"list_rooms({wing!r})")
        rooms_raw = _unwrap(rooms_result, "rooms") or []
        rooms = [str(r.get("name")) if isinstance(r, dict) else str(r) for r in rooms_raw]
        if not rooms:
            # Rooms listing empty: still probe the wing-level listing so an
            # unroomed wing is not misread as empty (empty result is never
            # proof of an empty wing).
            rooms = [""]

    ids: list[str] = []
    pages = 0
    for room in rooms:
        offset = 0
        while True:
            result = call_with_retry(
                lambda r=room, o=offset: mcp.list_drawers(wing=wing, room=r, limit=PAGE_LIMIT, offset=o),
                f"list_drawers(wing={wing!r}, room={room!r}, offset={offset})",
            )
            items = _unwrap(result, "drawers") or []
            total = _unwrap(result, "total")
            if not isinstance(items, list):
                raise ResetBlocked(f"list_drawers returned non-list drawers for wing {wing!r}")
            if len(items) > PAGE_LIMIT:
                raise ResetBlocked(
                    f"list_drawers page exceeded documented page size {PAGE_LIMIT} "
                    f"({len(items)} items) for wing {wing!r}"
                )
            pages += 1
            if pages > MAX_ENUM_PAGES:
                raise ResetBlocked(f"pagination for wing {wing!r} exceeded {MAX_ENUM_PAGES} pages; aborting enumeration")
            for item in items:
                drawer_id = item.get("id") if isinstance(item, dict) else item
                if drawer_id is not None:
                    ids.append(str(drawer_id))
            if len(items) < PAGE_LIMIT:
                break
            offset += PAGE_LIMIT

    unique, dup_count = dedupe(ids)
    enum = Enumeration(wing=wing, ids=unique, duplicates_found=dup_count, pages=pages)
    if dup_count:
        enum.notes.append(f"{dup_count} duplicate drawer ID(s) collapsed during enumeration")
    # Consistency check against the taxonomy total (if the taxonomy reports
    # per-wing drawer counts). The taxonomy counts records, so compare raw
    # collected IDs (duplicates included). A mismatch means the data changed
    # during enumeration or the listing is inconsistent — stop before
    # deleting anything.
    try:
        taxonomy = call_with_retry(mcp.get_taxonomy, "get_taxonomy")
        wings_raw = _unwrap(taxonomy, "wings") or []
        for w in wings_raw:
            name = w.get("wing") or w.get("name") if isinstance(w, dict) else None
            if name == wing:
                reported = w.get("drawer_count")
                if isinstance(reported, int) and reported != len(ids):
                    raise ResetBlocked(
                        f"collected {len(ids)} drawer ID(s) (unique: {len(unique)}) for wing {wing!r} "
                        f"but taxonomy reports {reported}; the palace changed during enumeration — "
                        "re-run the reset before deleting anything"
                    )
                if isinstance(reported, int):
                    enum.reported_total = reported
    except ResetBlocked:
        raise
    except Exception:
        # Taxonomy is an optional cross-check; its absence does not block a
        # deletion that the per-room pagination already validated.
        enum.notes.append("taxonomy cross-check unavailable; relied on pagination totals")
    return enum


# --------------------------------------------------------------------------
# Phase 2: bulk deletion with per-batch result inspection
# --------------------------------------------------------------------------

@dataclass
class BatchOutcome:
    ids: list[str]
    ok_ids: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)   # id -> error text
    missing: list[str] = field(default_factory=list)        # id absent from results
    revisions_deleted: int | None = None
    revisions_error: str | None = None
    raw: dict | None = None


@dataclass
class DeletionReport:
    attempted: list[str]
    deleted: list[str]
    failed: dict[str, str]
    missing: list[str]
    calls: int = 0
    batch_sizes: list[int] = field(default_factory=list)
    transient_retries: int = 0
    revisions_deleted: int = 0
    revisions_errors: list[str] = field(default_factory=list)


def inspect_batch_result(batch_ids: list[str], result: Any) -> BatchOutcome:
    """Parse one mempalace_delete_drawers response against its requested IDs.

    A successfully accepted batch is NOT proof every drawer was deleted:
    per-ID results may report errors, and IDs absent from the results list
    are recorded as missing rather than assumed deleted.
    """
    outcome = BatchOutcome(ids=list(batch_ids))
    results = _unwrap(result, "results")
    if isinstance(results, dict):
        results = [dict(id=k, **(v if isinstance(v, dict) else {"success": bool(v)})) for k, v in results.items()]
    entries: dict[str, dict] = {}
    if isinstance(results, list):
        for entry in results:
            if isinstance(entry, dict):
                key = entry.get("id") or entry.get("drawer_id") or entry.get("drawer")
                if key is not None:
                    entries[str(key)] = entry

    for drawer_id in batch_ids:
        entry = entries.get(drawer_id)
        if entry is None:
            outcome.missing.append(drawer_id)
            continue
        ok = entry.get("success", entry.get("deleted", True))
        error = entry.get("error") or entry.get("message")
        if ok is False or (ok is True and isinstance(error, str) and error):
            outcome.failed[drawer_id] = str(error or "unknown error")
        else:
            outcome.ok_ids.append(drawer_id)

    revisions = _unwrap(result, "revisions_deleted")
    if isinstance(revisions, int):
        outcome.revisions_deleted = revisions
    rev_err = _unwrap(result, "revisions_error")
    if isinstance(rev_err, str) and rev_err:
        outcome.revisions_error = rev_err
    outcome.raw = result if isinstance(result, dict) else None
    return outcome


def bulk_delete(mcp: McpLike, drawer_ids: list[str]) -> DeletionReport:
    """Delete drawer IDs through mempalace_delete_drawers in <=500-ID batches.

    - Batches respect the documented 500-ID maximum.
    - Every batch result is inspected per ID; failures and missing IDs are
      tracked instead of being papered over by the batch call's success.
    - Transient batch failures get bounded retries; a batch that still fails
      stops the deletion phase with its diagnostics (ResetBlocked).
    - This function contains the ONLY deletion mechanism of the normal reset:
      mempalace_delete_drawers. It never calls mempalace_delete_drawer.
    """
    report = DeletionReport(attempted=list(drawer_ids), deleted=[], failed={}, missing=[])
    remaining = list(drawer_ids)
    for batch in batches(remaining, MAX_BATCH):
        try:
            result = call_with_retry(lambda b=batch: mcp.delete_drawers(drawer_ids=b), "delete_drawers batch")
        except ResetBlocked as exc:
            # Attribute the failure to the IDs of this batch so the report
            # shows exactly what was not deleted.
            for drawer_id in batch:
                report.failed[drawer_id] = str(exc)
            raise ResetBlocked(
                f"bulk deletion stopped: {exc}; {len(report.deleted)} drawer(s) deleted before failure"
            ) from exc
        report.calls += 1
        report.batch_sizes.append(len(batch))
        outcome = inspect_batch_result(batch, result)
        report.deleted.extend(outcome.ok_ids)
        for failed_id, err in outcome.failed.items():
            report.failed[failed_id] = err
        report.missing.extend(outcome.missing)
        if outcome.revisions_deleted:
            report.revisions_deleted += outcome.revisions_deleted
        if outcome.revisions_error:
            report.revisions_errors.append(outcome.revisions_error)
    return report


# --------------------------------------------------------------------------
# Phase 3: verification (the wing-disappearance continuation fix)
# --------------------------------------------------------------------------

@dataclass
class WingVerification:
    wing: str
    cleared: bool
    wing_absent: bool = False
    remaining_drawers: int = 0
    evidence: str = ""
    verified_unrelated_intact: bool = False


def _wing_drawer_count(mcp: McpLike, wing: str) -> tuple[bool, int, str]:
    """Return (wing_absent, drawer_count, evidence) by fresh queries."""
    wings_result = call_with_retry(mcp.list_wings, "list_wings")
    wings_raw = _unwrap(wings_result, "wings") or []
    actual_names: list[str] = []
    for w in wings_raw:
        if isinstance(w, dict):
            actual_names.append(str(w.get("wing") or w.get("name") or ""))
        else:
            actual_names.append(str(w))
    if wing not in actual_names:
        # The recorded name may normalize differently from the actual wing.
        # Check normalized matches too — but only treat an *exact* absence as
        # absence; a normalized twin is verified via its own drawer count.
        target = normalize_wing_for_compare(wing)
        twins = [n for n in actual_names if normalize_wing_for_compare(n) == target]
        if not twins:
            return True, 0, f"wing {wing!r} absent from list_wings ({len(actual_names)} wings remain)"
        wing = twins[0]
    taxonomy = call_with_retry(mcp.get_taxonomy, "get_taxonomy")
    wings_raw = _unwrap(taxonomy, "wings") or []
    for w in wings_raw:
        if isinstance(w, dict) and (w.get("wing") or w.get("name")) == wing:
            count = w.get("drawer_count")
            if isinstance(count, int):
                return False, count, f"taxonomy reports drawer_count={count} for {wing!r}"
    # Taxonomy lacks the wing or lacks counts: count via rooms + list_drawers.
    rooms_result = call_with_retry(lambda: mcp.list_rooms(wing=wing), f"list_rooms({wing!r})")
    rooms_raw = _unwrap(rooms_result, "rooms") or []
    total = 0
    for r in rooms_raw:
        room = str(r.get("name")) if isinstance(r, dict) else str(r)
        offset = 0
        while True:
            result = call_with_retry(
                lambda rm=room, o=offset: mcp.list_drawers(wing=wing, room=rm, limit=PAGE_LIMIT, offset=o),
                f"list_drawers(wing={wing!r}, room={room!r}, offset={offset})",
            )
            items = _unwrap(result, "drawers") or []
            total += len(items)
            if len(items) < PAGE_LIMIT:
                break
            offset += PAGE_LIMIT
    return False, total, f"counted {total} remaining drawer(s) via list_drawers for {wing!r}"


def verify_wing_cleared(mcp: McpLike, wing: str, deletion: DeletionReport | None = None) -> WingVerification:
    """Post-deletion verification for one wing.

    A wing that no longer appears in list_wings is an EXPECTED success state
    (MemPalace deletes a wing implicitly with its last drawer), never a
    reason to abandon the reset. A wing that still exists must report zero
    drawers to count as cleared. Anomalies (missing IDs in batch results,
    per-ID errors) are preserved in the report instead of being hidden by
    the zero-count.
    """
    wing_absent, count, evidence = _wing_drawer_count(mcp, wing)
    verification = WingVerification(
        wing=wing,
        cleared=(wing_absent or count == 0),
        wing_absent=wing_absent,
        remaining_drawers=count,
        evidence=evidence,
    )
    if deletion is not None and (deletion.failed or deletion.missing):
        notes = []
        if deletion.failed:
            notes.append(f"{len(deletion.failed)} per-ID error(s): {dict(list(deletion.failed.items())[:5])}")
        if deletion.missing:
            notes.append(f"{len(deletion.missing)} ID(s) missing from batch results: {deletion.missing[:5]}")
        if verification.cleared:
            verification.evidence += " | anomalies noted but postcondition satisfied: " + "; ".join(notes)
        else:
            verification.evidence += " | unresolved anomalies: " + "; ".join(notes)
    return verification


# --------------------------------------------------------------------------
# Phase 4: tunnel / hallway cleanup
# --------------------------------------------------------------------------

@dataclass
class GraphRecord:
    kind: str          # "tunnel" | "hallway"
    id: str
    wings: set[str]    # exact wings the record associates
    raw: dict


@dataclass
class GraphCleanupReport:
    in_scope: list[GraphRecord] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)  # id -> error
    remaining_in_scope: list[GraphRecord] = field(default_factory=list)
    preserved: int = 0
    notes_wings_skipped: list[str] = field(default_factory=list)  # wings whose records were deliberately left


def _tunnel_wings(record: dict) -> set[str]:
    wings: set[str] = set()
    for key in ("source_wing", "target_wing", "wing_a", "wing_b", "wing"):
        value = record.get(key)
        if isinstance(value, str) and value:
            wings.add(value)
    return wings


def _hallway_wings(record: dict) -> set[str]:
    wings: set[str] = set()
    for key in ("wing", "wing_name", "source_wing", "target_wing"):
        value = record.get(key)
        if isinstance(value, str) and value:
            wings.add(value)
    return wings


def collect_graph_records(mcp: McpLike, target_wings: list[str]) -> tuple[list[GraphRecord], list[GraphRecord], GraphCleanupReport]:
    """Collect tunnels/hallways associated with the EXACT confirmed wings.

    Matching is by exact wing name in the record's endpoints/association —
    never by normalized slug. Records belonging to other wings are preserved.
    """
    targets = set(target_wings)
    tunnels: list[GraphRecord] = []
    hallways: list[GraphRecord] = []
    report = GraphCleanupReport()
    try:
        tunnels_result = call_with_retry(lambda: mcp.list_tunnels(), "list_tunnels")
    except ResetBlocked as exc:
        report.failed["<list_tunnels>"] = str(exc)
        return tunnels, hallways, report
    for record in _unwrap(tunnels_result, "tunnels") or []:
        if not isinstance(record, dict):
            continue
        wings = _tunnel_wings(record)
        tunnel_id = str(record.get("id") or record.get("tunnel_id") or "")
        graph = GraphRecord(kind="tunnel", id=tunnel_id, wings=wings, raw=record)
        if wings & targets:
            tunnels.append(graph)
            report.in_scope.append(graph)
        else:
            report.preserved += 1
    try:
        hallways_result = call_with_retry(lambda: mcp.list_hallways(), "list_hallways")
    except ResetBlocked as exc:
        report.failed["<list_hallways>"] = str(exc)
        return tunnels, hallways, report
    for record in _unwrap(hallways_result, "hallways") or []:
        if not isinstance(record, dict):
            continue
        wings = _hallway_wings(record)
        hallway_id = str(record.get("id") or record.get("hallway_id") or "")
        graph = GraphRecord(kind="hallway", id=hallway_id, wings=wings, raw=record)
        if wings & targets:
            hallways.append(graph)
            report.in_scope.append(graph)
        else:
            report.preserved += 1
    return tunnels, hallways, report


def cleanup_graph(mcp: McpLike, target_wings: list[str]) -> GraphCleanupReport:
    """Delete in-scope tunnels/hallways individually and verify removal.

    Uses mempalace_delete_tunnel / mempalace_delete_hallway — the only
    documented interface; there is no bulk variant and none is invented.
    Failures are tracked separately from drawer deletion and never reported
    as success.
    """
    tunnels, hallways, report = collect_graph_records(mcp, target_wings)
    for graph in tunnels + hallways:
        try:
            if graph.kind == "tunnel":
                call_with_retry(lambda t=graph.id: mcp.delete_tunnel(tunnel_id=t), f"delete_tunnel({graph.id})")
            else:
                call_with_retry(lambda h=graph.id: mcp.delete_hallway(hallway_id=h), f"delete_hallway({graph.id})")
            report.deleted.append(f"{graph.kind}:{graph.id}")
        except ResetBlocked as exc:
            report.failed[f"{graph.kind}:{graph.id}"] = str(exc)
    # Verify: re-list and keep only in-scope records that survived.
    _, _, post = collect_graph_records(mcp, target_wings)
    surviving_ids = {f"{g.kind}:{g.id}" for g in post.in_scope}
    report.remaining_in_scope = [g for g in post.in_scope if f"{g.kind}:{g.id}" in surviving_ids]
    report.preserved += post.preserved
    return report


# --------------------------------------------------------------------------
# Full per-wing reset (enumerate -> delete -> verify per target, continue)
# --------------------------------------------------------------------------

@dataclass
class WingResetResult:
    wing: str
    phase_reached: str            # enumerated | deleted | verified | blocked
    enumeration: Enumeration | None = None
    deletion: DeletionReport | None = None
    verification: WingVerification | None = None
    cleared: bool = False
    blocked_reason: str = ""
    notes: list[str] = field(default_factory=list)


def reset_wing(mcp: McpLike, wing: str) -> WingResetResult:
    """Run enumerate -> bulk delete -> verify for ONE confirmed target wing.

    Continuation guarantee: a wing that disappears after its drawers are
    deleted is an expected success state. This function only blocks on
    genuinely unsafe states (inconsistent enumeration, unreachable palace,
    a wing that still reports drawers after deletion).
    """
    result = WingResetResult(wing=wing, phase_reached="enumerated")
    try:
        enum = collect_drawer_ids(mcp, wing)
        result.enumeration = enum
        result.notes.extend(enum.notes)
        if not enum.ids:
            # Empty wing: nothing to delete; verify absent-or-empty.
            verification = verify_wing_cleared(mcp, wing)
            result.verification = verification
            result.cleared = verification.cleared
            result.phase_reached = "verified"
            if not verification.cleared:
                result.blocked_reason = f"wing {wing!r} still reports {verification.remaining_drawers} drawer(s) after empty enumeration"
            return result
        deletion = bulk_delete(mcp, enum.ids)
        result.deletion = deletion
        result.phase_reached = "deleted"
        verification = verify_wing_cleared(mcp, wing, deletion)
        result.verification = verification
        result.phase_reached = "verified"
        result.cleared = verification.cleared
        if not verification.cleared:
            result.blocked_reason = (
                f"wing {wing!r} still reports {verification.remaining_drawers} drawer(s) after deletion; "
                f"{len(deletion.failed)} per-ID error(s), {len(deletion.missing)} missing result(s)"
            )
    except ResetBlocked as exc:
        result.blocked_reason = str(exc)
        if result.deletion is None:
            result.phase_reached = "blocked"
    return result


@dataclass
class ResetReport:
    wings: list[WingResetResult] = field(default_factory=list)
    graph: GraphCleanupReport | None = None
    drawer_success: bool = False
    tunnel_success: bool | None = None
    hallway_success: bool | None = None
    overall_success: bool = False
    blocked: list[str] = field(default_factory=list)

    def summarize(self) -> str:
        lines = []
        for wing in self.wings:
            deleted = len(wing.deletion.deleted) if wing.deletion else 0
            lines.append(
                f"wing {wing.wing!r}: phase={wing.phase_reached} cleared={wing.cleared} "
                f"deleted={deleted} remaining={wing.verification.remaining_drawers if wing.verification else '?'}"
            )
        if self.graph is not None:
            lines.append(
                f"graph: deleted={len(self.graph.deleted)} failed={len(self.graph.failed)} "
                f"preserved={self.graph.preserved} remaining_in_scope={len(self.graph.remaining_in_scope)}"
            )
        lines.append(f"overall_success={self.overall_success}")
        return "\n".join(lines)


def run_normal_reset(mcp: McpLike, confirmed_wings: list[str]) -> ResetReport:
    """Run the complete normal (MCP) reset over all confirmed target wings.

    Ordering: per-wing enumerate/delete/verify first (each wing independent —
    one wing's failure never abandons the others), then tunnel/hallway
    cleanup, then the final classification. The four postconditions
    (drawers, tunnels, hallways, overall) are reported separately.

    Local-file deletion (.brain/, graphify-out/, CLAUDE.md block) is handled
    by scripts/reset_brain.py and is NOT part of this function.
    """
    report = ResetReport()
    for wing in confirmed_wings:
        report.wings.append(reset_wing(mcp, wing))
    # Graph cleanup runs for the wings that were actually CLEARED — deleting
    # graph records of a wing whose drawers survived would be a destructive
    # dependent operation on an inconsistent state; those records stay for a
    # retry and are reported as remaining instead of being hidden.
    cleared_wings = [w.wing for w in report.wings if w.cleared]
    try:
        report.graph = cleanup_graph(mcp, cleared_wings)
        if len(cleared_wings) < len(confirmed_wings):
            report.graph.notes_wings_skipped = [
                w.wing for w in report.wings if not w.cleared
            ]
        report.tunnel_success = not any(
            g.kind == "tunnel" for g in report.graph.remaining_in_scope
        ) and not any(k.startswith("tunnel") for k in report.graph.failed)
        report.hallway_success = not any(
            g.kind == "hallway" for g in report.graph.remaining_in_scope
        ) and not any(k.startswith("hallway") for k in report.graph.failed)
    except ResetBlocked as exc:
        report.blocked.append(f"graph cleanup blocked: {exc}")
    drawer_success = all(w.cleared for w in report.wings)
    report.drawer_success = drawer_success
    report.overall_success = (
        drawer_success
        and report.graph is not None
        and not report.graph.failed
        and not report.graph.remaining_in_scope
        and not report.blocked
    )
    for wing in report.wings:
        if not wing.cleared:
            report.blocked.append(f"wing {wing.wing!r}: {wing.blocked_reason}")
    return report
