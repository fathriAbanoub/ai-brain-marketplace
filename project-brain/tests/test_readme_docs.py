"""WP4: README parity — the docs are only trustworthy if the commands match.

- Every `project-brain-*` command named in project-brain/README.md must exist
  in bin/, and every bin/project-brain-* wrapper must be documented.
- Flag-level pins for the flags the README promises (verified against the
  scripts' argparse definitions).
- The reset-sequence pin from test_reset_contracts.py keeps passing
  (mempalace_delete_drawers documented, never the single-drawer tool).
"""

import re
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
README = PLUGIN_ROOT / "README.md"
BIN_DIR = PLUGIN_ROOT / "bin"

COMMAND_NAME_RE = re.compile(r"project-brain-([a-z][a-z-]*)")


def readme_text() -> str:
    return README.read_text(encoding="utf-8")


def readme_commands() -> set[str]:
    """Full command names (project-brain-<suffix>) mentioned in the README.
    Trailing hyphens are trimmed so backticks and table cells parse."""
    text = readme_text()
    names = set()
    for match in COMMAND_NAME_RE.finditer(text):
        suffix = match.group(1).rstrip("-")
        if suffix:
            names.add(f"project-brain-{suffix}")
    return names


def bin_commands() -> set[str]:
    return {p.name for p in BIN_DIR.iterdir() if p.name.startswith("project-brain-")}


class TestReadmeCommandParity:
    def test_every_readme_command_exists_in_bin(self):
        missing = sorted(n for n in readme_commands() if n not in bin_commands())
        assert not missing, f"README names commands that are not in bin/: {missing}"

    def test_every_bin_command_is_documented(self):
        undocumented = sorted(n for n in bin_commands() if n not in readme_commands())
        assert not undocumented, f"bin/ commands missing from README: {undocumented}"

    def test_readme_mentions_all_bin_wrappers_at_least_once(self):
        text = readme_text()
        for name in sorted(bin_commands()):
            assert name in text, f"{name} never appears in the README"


class TestReadmeFlagTruth:
    """Flags the README promises must exist in the scripts' argparse."""

    def test_lint_flags(self):
        script = (PLUGIN_ROOT / "scripts" / "lint_brain.py").read_text(encoding="utf-8")
        for flag in ("--json", "--reindex", "--verify"):
            assert flag in script and flag in readme_text()

    def test_doctor_flags(self):
        script = (PLUGIN_ROOT / "scripts" / "doctor.py").read_text(encoding="utf-8")
        for flag in ("--strict", "--json"):
            assert flag in script and flag in readme_text()

    def test_inventory_subcommands(self):
        script = (PLUGIN_ROOT / "scripts" / "brain_inventory.py").read_text(encoding="utf-8")
        for sub in ("inventory", "crossrefs", "git-digest", "graph-digest"):
            assert sub in script and sub in readme_text()

    def test_hard_reset_flags(self):
        script = (PLUGIN_ROOT / "scripts" / "hard_reset.py").read_text(encoding="utf-8")
        for flag in ("--wing", "--db-path", "--confirm", "--plan-hash", "--allow-live"):
            assert flag in script and flag in readme_text()

    def test_reset_flags(self):
        script = (PLUGIN_ROOT / "scripts" / "reset_brain.py").read_text(encoding="utf-8")
        for flag in ("--dry-run", "--confirm", "--verify-reset-transcript", "--classify-wings"):
            assert flag in script and flag in readme_text()

    def test_wiki_subcommands(self):
        script = (PLUGIN_ROOT / "scripts" / "wiki_ledger.py").read_text(encoding="utf-8")
        for sub in ("status", "snapshot", "log", "history", "diff", "restore"):
            assert f'"{sub}"' in script and sub in readme_text()

    def test_init_flags(self):
        script = (PLUGIN_ROOT / "scripts" / "scaffold_brain.py").read_text(encoding="utf-8")
        for flag in ("--force", "--wing"):
            assert flag in script and flag in readme_text()


class TestReadmeDocumentsTheRelease:
    def test_six_layers_present(self):
        text = readme_text()
        for layer in ("Evidence", "Synthesis", "Memory", "Map", "Handoff", "Vault"):
            assert layer in text

    def test_wiki_ledger_documented_with_storage_truth(self):
        text = readme_text()
        assert ".brain/state/wiki.git" in text
        assert "auto-snapshot" in text
        assert "never a `.git` inside the wiki dir" in text or "never a `.git`" in text

    def test_hook_opt_out_documented(self):
        text = readme_text()
        assert "PROJECT_BRAIN_HOOKS_DISABLED=1" in text
        assert "launch-time snapshot" in text

    def test_three_troubleshooting_modes_documented(self):
        text = readme_text()
        assert "launch-time snapshot" in text
        assert "deferred" in text.lower()
        assert "turn cap" in text

    def test_whats_new_section_present(self):
        assert "What's new in 0.10.0" in readme_text()

    def test_graphify_policy_documented(self):
        text = readme_text()
        assert "PRIMARY" in text or "Primary builder" in text
        assert "GRAPHIFY_BACKEND=none" in text
        assert "reconnect" in text.lower()

    def test_no_unmeasured_token_saving_claims(self):
        text = readme_text()
        for claim in ("saves tokens", "token-saving", "saves context"):
            assert claim not in text.lower()

    def test_top_level_readme_is_a_pointer(self):
        text = (PLUGIN_ROOT.parent / "README.md").read_text(encoding="utf-8")
        assert "project-brain/README.md" in text
        # The pointer stays short: no command tables duplicated at the top.
        assert len(text) < 2000

    def test_reset_sequence_pin_still_holds(self):
        """Deliberate pin (moved from test_reset_contracts.py::test_readme_reset_sequence_updated)."""
        text = readme_text()
        assert "mempalace_delete_drawers" in text
        assert "mempalace_delete_drawer` for" not in text
