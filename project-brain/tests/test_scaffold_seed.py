"""WP1 regression tests: scaffold seed content and structure (KD-05, 06, 08, 10, 11).

These tests encode the DESIRED behavior. On the unmodified plugin they fail
(KD-11 seeded plugin-explaining pages, KD-06 dual task lists, KD-10 eager
empty lifecycle dirs, KD-02-bait volatile numbers in seeds).
"""

from pathlib import Path


FORBIDDEN_SEED_PAGES = [
    "wiki/architecture/AI Brain Architecture.md",
    "wiki/decisions/Use Layered Brain Architecture.md",
    "wiki/concepts/LLM Wiki.md",
    "wiki/concepts/Post-Wiki Synchronization.md",
    "wiki/entities/MemPalace.md",
    "wiki/entities/graphify.md",
    "wiki/entities/Obsidian.md",
]

# Directories that must NOT be created eagerly by scaffold (KD-10): the
# lifecycle step that fills them creates them lazily.
FORBIDDEN_EAGER_DIRS = [
    "raw/articles", "raw/papers", "raw/notes", "raw/meetings",
    "raw/conversations", "raw/assets", "outputs", "memory", "graph",
    "runbooks", "audit/resolved",
]


class TestSeedContent:
    def test_no_plugin_explaining_seed_pages(self, scaffolded_project: Path):
        """KD-11: a fresh brain must not seed wiki pages about the plugin itself."""
        for rel in FORBIDDEN_SEED_PAGES:
            assert not (scaffolded_project / rel).exists(), f"seeded plugin page: {rel}"

    def test_fresh_seed_pages_present(self, scaffolded_project: Path):
        """The minimal, project-facing seed set (all draft placeholders)."""
        for rel in [
            "CLAUDE.md",
            "wiki/index.md",
            "wiki/architecture/System Overview.md",
            "wiki/open-questions.md",
            "state/session-brief.md",
            "tasks/next-actions.md",
            "log",
        ]:
            assert (scaffolded_project / rel).exists(), f"missing seed artifact: {rel}"

    def test_seed_pages_are_draft(self, scaffolded_project: Path):
        """Placeholders carry status: draft and never count as coverage."""
        overview = scaffolded_project / "wiki" / "architecture" / "System Overview.md"
        text = overview.read_text(encoding="utf-8")
        assert "status: draft" in text

    def test_session_brief_claims_no_decisions(self, scaffolded_project: Path):
        """KD-11: the brief must not claim an 'accepted' decision with no evidence."""
        brief = (scaffolded_project / "state" / "session-brief.md").read_text(encoding="utf-8")
        low = brief.lower()
        assert "accepted" not in low
        assert "decisions made recently" not in low or "none" in low

    def test_session_brief_has_no_task_checklist(self, scaffolded_project: Path):
        """KD-06: tasks live in ONE file (tasks/next-actions.md), never in the brief."""
        brief = (scaffolded_project / "state" / "session-brief.md").read_text(encoding="utf-8")
        assert "- [ ]" not in brief, "session brief contains a task checklist"
        assert "- [x]" not in brief, "session brief contains a task checklist"

    def test_no_eager_empty_lifecycle_dirs(self, scaffolded_project: Path):
        """KD-10: lifecycle dirs are created lazily by the step that fills them."""
        for rel in FORBIDDEN_EAGER_DIRS:
            assert not (scaffolded_project / rel).exists(), f"eager empty dir: {rel}"

    def test_index_lists_only_real_pages(self, scaffolded_project: Path):
        """KD-05 bait: index is script-generated from the real page list."""
        index = (scaffolded_project / "wiki" / "index.md").read_text(encoding="utf-8")
        for rel in FORBIDDEN_SEED_PAGES:
            stem = Path(rel).stem
            assert f"[[{rel[5:-3]}]]" not in index, f"index references seeded plugin page: {stem}"
            assert f"[[{stem}]]" not in index, f"index references seeded plugin page: {stem}"


class TestExistingBrainCompat:
    def test_rescaffold_keeps_old_seed_pages(self, run_script, tmp_project: Path):
        """Existing brains with old seed pages keep working: nothing is deleted."""
        proj = tmp_project / "old-brain"
        proj.mkdir(parents=True)
        old_page = proj / ".brain" / "wiki" / "entities" / "MemPalace.md"
        old_page.parent.mkdir(parents=True)
        old_page.write_text("---\ntitle: MemPalace\ntype: entity\nstatus: active\nsources: []\n---\n# MemPalace\nold page\n", encoding="utf-8")
        result = run_script("scaffold_brain.py", [str(proj), "Old Project"])
        assert result.returncode == 0
        assert old_page.exists(), "re-scaffold deleted an existing page"
