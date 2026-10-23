#!/usr/bin/env python3
"""project-brain awareness hooks for OpenClaude / Claude Code-style harnesses.

Two events, registered via hooks/hooks.json in this plugin:

  session-start   Inject a SHORT brain status into context: .brain presence,
                  graphify freshness (doctor's line), pointers to
                  session-brief.md / index.md, harness label. Also fires on
                  SessionStart source=compact, i.e. after context compaction.
  post-tool-use   After Write/Edit/MultiEdit/NotebookEdit, if source files
                  changed since the graph was built, emit a throttled reminder
                  to update wiki pages, the graph (doctor decision rule), and
                  the session diary.

Hard constraints (report Part 7):
  - Read-only toward MemPalace: this script NEVER invokes the mempalace CLI
    or MCP write tools. MemPalace's own hooks already write session
    transcripts into the palace; a second writer fails with exit code 1
    ("palace ... is held by PID ...").
  - No network, standard library only (plus the plugin's own doctor.py).
  - Bounded output (MAX_CONTEXT_CHARS), throttled + deduplicated reminders.
  - Silent no-op when .brain/ does not exist or anything fails; always exits
    0 so the session is never blocked or broken.
  - No secrets in output (paths, commit hashes, and doctor reason text only).
  - Env opt-out: set PROJECT_BRAIN_HOOKS_DISABLED to any non-empty value
    other than "0".

Payload/output shapes follow OpenClaude 0.33.0 (report Part 4): stdin JSON
with session_id/transcript_path/cwd (+tool_name/tool_input for PostToolUse,
source for SessionStart); stdout JSON
{"hookSpecificOutput": {"hookEventName": ..., "additionalContext": ...}}.

The discriminator key is hookEventName — verbatim from OpenClaude 0.33.0
src/types/hooks.ts:83-90 (SessionStart variant) and :100-106 (PostToolUse
variant) of the hookSpecificOutput union validated by hookJSONOutputSchema
(src/utils/hooks.ts:576). Output using any other key fails that schema and is
yielded as a non_blocking_error instead of being injected into context
(src/utils/hooks.ts:2703-2731). JSON additionalContext is chosen over plain
stdout because plain stdout reaches the model for SessionStart only
(src/utils/messages.ts:3065-3080; PostToolUse returns []) and its Claude Code
behavior is UNVERIFIED here, while the JSON shape is proven for both events in
OpenClaude and is the documented Claude Code format.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from doctor import graphify_freshness  # noqa: E402  (reuse, do not duplicate)

# --- named constants (all tunables live here) --------------------------------
OPT_OUT_ENV = "PROJECT_BRAIN_HOOKS_DISABLED"
PROJECT_DIR_ENV = "CLAUDE_PROJECT_DIR"
PLUGIN_DATA_ENV = "CLAUDE_PLUGIN_DATA"
OPENCLAUDE_CONFIG_ENV = "OPENCLAUDE_CONFIG_DIR"
STATE_FILENAME = "project-brain-hooks-state.json"
STATE_DIR_FALLBACK = Path("~/.cache/project-brain").expanduser()
POST_TOOL_USE_MIN_INTERVAL_SECS = 300  # never remind more often than this
SAME_REASON_REPEAT_SECS = 1800  # same staleness reason: remind at most 1/30min
MAX_CONTEXT_CHARS = 700  # hard bound on injected text
REASON_MAX_CHARS = 160  # doctor reason text bound inside the reminder
EVENT_SESSION_START = "session-start"
EVENT_POST_TOOL_USE = "post-tool-use"
EVENTS = (EVENT_SESSION_START, EVENT_POST_TOOL_USE)
# Event names as OpenClaude's hookSpecificOutput union discriminates them
# (src/types/hooks.ts:84,101) and as hooks.json keys them.
HOOK_EVENT_NAME_SESSION_START = "SessionStart"
HOOK_EVENT_NAME_POST_TOOL_USE = "PostToolUse"
# The only per-variant keys the schema allows besides the discriminator.
SCHEMA_KEYS_SESSION_START = frozenset({"hookEventName", "additionalContext", "initialUserMessage", "watchPaths"})
SCHEMA_KEYS_POST_TOOL_USE = frozenset({"hookEventName", "additionalContext", "updatedMCPToolOutput"})
HARNESS_OPENCLAUDE = "openclaude"
HARNESS_CLAUDE_CODE = "claude-code"
HARNESS_UNKNOWN = "unknown"


def read_payload() -> dict:
    """Read the hook JSON payload from stdin; garbage becomes {}."""
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        return data if isinstance(data, dict) else {}
    except Exception:
        # ponytail: a malformed payload silently degrades to {} so the hook
        # stays a no-op instead of erroring the session; upgrade path: log to
        # a debug file if ever needed.
        return {}


def detect_harness(payload: dict) -> str:
    """Best-effort harness label. Never guessed harder than the evidence.

    Evidence, strongest first: OPENCLAUDE_CONFIG_DIR is OpenClaude's config
    override (src/utils/envUtils.ts:76); the transcript path location;
    CLAUDE_PLUGIN_DATA is set by OpenClaude hook processes
    (src/utils/hooks.ts:1038) — Claude Code behavior UNVERIFIED, so it is the
    weakest signal and maps to "openclaude-compatible".
    """
    if os.environ.get(OPENCLAUDE_CONFIG_ENV):
        return HARNESS_OPENCLAUDE
    transcript = str(payload.get("transcript_path", ""))
    if "/.openclaude/" in transcript:
        return HARNESS_OPENCLAUDE
    if "/.claude/" in transcript:
        return HARNESS_CLAUDE_CODE
    if os.environ.get(PLUGIN_DATA_ENV):
        return "openclaude-compatible"
    return HARNESS_UNKNOWN


def resolve_root(payload: dict) -> Path:
    cwd = str(payload.get("cwd") or os.environ.get(PROJECT_DIR_ENV) or "").strip()
    root = Path(cwd) if cwd else Path.cwd()
    return root.expanduser().resolve()


def _state_path() -> Path:
    base = os.environ.get(PLUGIN_DATA_ENV)
    state_dir = Path(base).expanduser() if base else STATE_DIR_FALLBACK
    return state_dir / STATE_FILENAME


def load_state() -> dict:
    try:
        return json.loads(_state_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict) -> bool:
    try:
        path = _state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state), encoding="utf-8")
        tmp.replace(path)
        return True
    except Exception:
        return False


def emit(event: str, text: str) -> None:
    text = text.strip()[:MAX_CONTEXT_CHARS]
    if not text:
        return
    print(json.dumps({
        "hookSpecificOutput": {"hookEventName": event, "additionalContext": text},
    }))


def session_start_context(root: Path, payload: dict) -> str:
    freshness, reason = graphify_freshness(root)
    if freshness == "fresh":
        graph_line = f"graphify: fresh ({reason})"
    else:
        graph_line = f"graphify: STALE ({reason}) — follow the doctor decision rule: " \
                     "code-only changes -> `graphify update .`; docs or missing report -> `/graphify .`"
    lines = [
        "project-brain: this project has a persistent brain in .brain/.",
        "Read .brain/state/session-brief.md and .brain/wiki/index.md first; "
        "check MemPalace (mempalace_status) before claiming prior-work facts.",
        graph_line,
        f"harness: {detect_harness(payload)}",
    ]
    return "\n".join(lines)


def post_tool_use_context(root: Path) -> str:
    # Cheap interval throttle FIRST: this hook fires on every Write/Edit, and
    # graphify_freshness costs two git subprocesses (5 s timeouts each). While
    # throttled, return before paying that cost; freshness is computed only
    # when a reminder could actually fire.
    now = time.time()
    state = load_state()
    last_ts = float(state.get("post_tool_use_ts", 0.0))
    if (now - last_ts) < POST_TOOL_USE_MIN_INTERVAL_SECS:
        return ""
    freshness, reason = graphify_freshness(root)
    if freshness == "fresh":
        return ""
    sig = reason[:REASON_MAX_CHARS]
    same_reason_recent = (sig == str(state.get("post_tool_use_sig", ""))) and (
        (now - last_ts) < SAME_REASON_REPEAT_SECS
    )
    if same_reason_recent:
        return ""
    # ponytail: if the state file cannot be written (read-only HOME), dedupe
    # silently degrades and the reminder may repeat; bounded text keeps that
    # harmless. Upgrade path: fall back to a temp dir next to the project.
    new_state = dict(state)
    new_state["post_tool_use_ts"] = now
    new_state["post_tool_use_sig"] = sig
    save_state(new_state)
    return (
        "project-brain: source changed since the graph was built "
        f"({sig}). Before finishing this turn: update the relevant "
        ".brain/wiki pages; refresh the graph per the doctor rule "
        "(`graphify update .` for code-only, `/graphify .` for docs or a "
        "missing report); write a session diary entry (mempalace_diary_write) "
        "if session context changed."
    )


def main(argv: list[str]) -> int:
    try:
        if os.environ.get(OPT_OUT_ENV, "").strip() not in ("", "0"):
            return 0
        event = argv[1] if len(argv) > 1 else ""
        if event not in EVENTS:
            return 0
        payload = read_payload()
        root = resolve_root(payload)
        if not (root / ".brain").is_dir():
            return 0  # silent no-op without a brain
        if event == EVENT_SESSION_START:
            emit(HOOK_EVENT_NAME_SESSION_START, session_start_context(root, payload))
        else:
            emit(HOOK_EVENT_NAME_POST_TOOL_USE, post_tool_use_context(root))
    except Exception:
        # Never break or block the session on any failure.
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
