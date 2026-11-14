"""Prose-contract tests: the reset/hard-reset skills and references must keep
teaching the bulk-delete, verification, continuation, and graph-cleanup
behavior that scripts/mempalace_reset.py implements. These complement the
algorithm tests in test_mempalace_reset.py — if the prose regresses to
per-drawer deletion, or drops the continuation rule, these tests fail.
"""

from __future__ import annotations

import re
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent
RESET_SKILL = PLUGIN_ROOT / "skills" / "reset" / "SKILL.md"
HARD_RESET_SKILL = PLUGIN_ROOT / "skills" / "hard-reset" / "SKILL.md"
BRAIN_SKILL = PLUGIN_ROOT / "skills" / "brain" / "SKILL.md"
TOOLS_DOC = PLUGIN_ROOT / "skills" / "brain" / "references" / "mempalace-tools.md"
WORKFLOW_DOC = PLUGIN_ROOT / "skills" / "brain" / "references" / "mempalace-workflow.md"
LIFECYCLE_DOC = PLUGIN_ROOT / "skills" / "brain" / "references" / "brain-lifecycle.md"


def test_reset_skill_never_instructs_single_drawer_deletion():
    text = RESET_SKILL.read_text(encoding="utf-8")
    # The only mentions of the single tool must be prohibitions.
    for line in text.splitlines():
        if "mempalace_delete_drawer" in line and "mempalace_delete_drawers" not in line:
            lowered = line.lower()
            assert any(
                w in lowered for w in ("never", "not even", "prohibited", "do not", "still not")
            ), f"reset skill line mentioning single-drawer deletion without prohibition: {line!r}"


def test_reset_skill_requires_bulk_batches_of_500():
    text = RESET_SKILL.read_text(encoding="utf-8")
    assert "mempalace_delete_drawers" in text
    assert "500" in text
    assert "batches" in text.lower()


def test_reset_skill_pagination_contract():
    text = RESET_SKILL.read_text(encoding="utf-8")
    assert "100" in text  # documented max page size
    assert "offset" in text


def test_reset_skill_wing_disappearance_is_continuation():
    text = RESET_SKILL.read_text(encoding="utf-8").lower()
    assert "expected success state" in text
    assert "continue" in text
    # The step that handles verification must explicitly say to move on.
    assert "3c" in text


def test_reset_skill_graph_cleanup_present():
    text = RESET_SKILL.read_text(encoding="utf-8")
    for tool in ("mempalace_list_tunnels", "mempalace_delete_tunnel", "mempalace_list_hallways", "mempalace_delete_hallway"):
        assert tool in text, f"reset skill must mention {tool}"
    assert "exact" in text.lower()  # exact-name scope rule


def test_reset_skill_uses_resolved_wrapper_for_dry_run_and_confirm():
    """CodeRabbit #17: when the command is NOT on PATH, the fallback section
    must use the resolved wrapper for BOTH the dry run and the confirmed run,
    and must warn that PLUGIN_ROOT does not survive across shell invocations."""
    text = RESET_SKILL.read_text(encoding="utf-8")
    fallback_start = text.index("not on PATH")
    fallback = text[fallback_start:]
    assert '"$PLUGIN_ROOT/bin/project-brain-reset" <project-root> --dry-run' in fallback
    assert '"$PLUGIN_ROOT/bin/project-brain-reset" <project-root> --confirm' in fallback
    # The re-resolution warning must be present in the fallback section.
    assert "re-resolve" in fallback or "does not survive" in fallback
    # The plain PATH form is fine for the normal case; the fallback section
    # must not document a bare confirm command (preview/confirm consistency).
    bare_confirm = re.findall(r"^project-brain-reset .*--confirm", fallback, re.MULTILINE)
    assert not bare_confirm, f"fallback section documents a bare confirm command: {bare_confirm}"


def test_reset_skill_directory_wing_is_diagnostic_only():
    text = RESET_SKILL.read_text(encoding="utf-8")
    assert "diagnostic-only" in text
    assert "separately confirms" in text


def test_reset_skill_normalized_collision_handling():
    text = RESET_SKILL.read_text(encoding="utf-8")
    assert "candidate discovery" in text
    assert "never collapse" in text.lower() or "never collap" in text.lower()


def test_reset_skill_hard_reset_referral():
    text = RESET_SKILL.read_text(encoding="utf-8")
    assert "/project-brain:hard-reset" in text
    assert "ownership" in text.lower()  # never recommend it for ownership questions


def test_brain_skill_reset_sequence_uses_bulk():
    text = BRAIN_SKILL.read_text(encoding="utf-8")
    assert "mempalace_delete_drawers" in text
    # The old per-drawer sequence must be gone.
    assert "mempalace_list_drawers` → `mempalace_delete_drawer`" not in text


def test_brain_skill_leftover_wing_check_reads_recorded_wing():
    text = BRAIN_SKILL.read_text(encoding="utf-8")
    assert "mempalace_wing" in text
    assert "mempalace_status" in text
    # The check must run status BEFORE list_wings.
    step6 = text[text.index("Leftover-wing check"):text.index("Leftover-wing check") + 1600]
    status_pos = step6.index("mempalace_status")
    wings_pos = step6.index("mempalace_list_wings")
    assert status_pos < wings_pos


def test_workflow_doc_bulk_loop():
    text = WORKFLOW_DOC.read_text(encoding="utf-8")
    assert "mempalace_delete_drawers" in text
    assert "mempalace_delete_drawer` once" not in text
    assert "mempalace delete-wing" in text  # explicitly prohibited


def test_tools_doc_delete_drawers_contract():
    text = TOOLS_DOC.read_text(encoding="utf-8")
    assert "1 to 500" in text
    assert "revisions_deleted" in text
    assert "revisions_error" in text
    assert "PROHIBITED in the reset workflow" in text


def test_hard_reset_skill_exists_and_is_separate():
    text = HARD_RESET_SKILL.read_text(encoding="utf-8")
    assert "SEPARATE" in text or "separate" in text
    assert "dry run" in text.lower()
    assert "--plan-hash" in text
    assert "backup" in text.lower()
    assert "mempalace_reconnect" in text
    assert "never launched automatically" in text.lower() or "NOT launched automatically" in text


def test_hard_reset_skill_fail_closed_discovery():
    text = HARD_RESET_SKILL.read_text(encoding="utf-8")
    assert "fail-closed" in text.lower()
    assert "--db-path" in text
    assert "MEMPAL_DIR" in text


def test_no_doc_recommends_mempalace_delete_wing():
    """The prohibited CLI command must only ever appear as a prohibition."""
    for path in (RESET_SKILL, HARD_RESET_SKILL, BRAIN_SKILL, TOOLS_DOC, WORKFLOW_DOC):
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if "mempalace delete-wing" in line:
                lowered = line.lower()
                assert any(w in lowered for w in ("not", "never", "no valid")), (
                    f"{path.name} mentions 'mempalace delete-wing' without prohibition: {line!r}"
                )


def test_reset_docstring_no_per_drawer():
    text = (PLUGIN_ROOT / "scripts" / "reset_brain.py").read_text(encoding="utf-8")
    assert "mempalace_delete_drawers" in text
    assert "-> mempalace_delete_drawer\n" not in text


def test_wiki_schema_documents_sources_convention():
    text = (PLUGIN_ROOT / "skills" / "brain" / "references" / "wiki-schema.md").read_text(encoding="utf-8")
    assert "wiki relative" in text.lower()
    assert "sources/<name>.md" in text


def test_readme_reset_sequence_updated():
    text = (PLUGIN_ROOT / "README.md").read_text(encoding="utf-8")
    assert "mempalace_delete_drawers" in text
    assert "mempalace_delete_drawer` for" not in text
