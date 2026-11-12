"""KD-18 regression tests: plugin-root resolution must survive --plugin-dir
sessions (no PATH entry, no CLAUDE_PLUGIN_ROOT in the Bash tool environment,
${CLAUDE_PLUGIN_ROOT} not substituted in delivered skill text).

Found live in Part 2 iter-1: the model received
"Base directory for this skill: <...>/project-brain/skills/brain" from the
harness, but every SKILL.md fallback chain guessed marketplace paths only, so
PLUGIN_ROOT resolved empty and the scripts were never run — the session then
hand-wrote an uncited, partially fabricated brain instead of stopping.

Fix contract: every skill that documents the exit-127 fallback must ALSO
document (a) deriving PLUGIN_ROOT from the harness-printed skill base
directory (three levels up), ordered BEFORE the marketplace guesses, and
(b) an explicit stop rule: never hand-write .brain files as a substitute.

KD-21 (Part 3 iter-4, 2026-10-29): the taught recipe assumed exactly two
dirname levels and lived in a comment. Live, the inner model substituted
the already-resolved PLUGIN ROOT into the dirname-x2 recipe, derived a
directory without bin/, the one-shot check failed, and the session burned
~18 turns on a filesystem hunt that ended executing a foreign, unfixed
copy of the plugin. New contract: the fallback must be a runnable
candidate loop over the base-directory path at depths 0/1/2, where the
first candidate containing bin/ wins — validated, never assumed.
"""

import re
import subprocess
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = PLUGIN_ROOT / "skills"

BASE_DIR_MARKER = "Base directory for this skill"
TWO_UP_RECIPE = 'dirname "$(dirname'
STOP_RULE_MARKER = "NEVER write or modify"
FALLBACK_ENV_LINE = 'PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}"'
MARKETPLACE_GUESS = "plugins/cache/ai-brain-marketplace"
CANDIDATE_LOOP_START = "for _c in"
BASE_DIR_ASSIGN = "BASE_DIR='<path-from-that-line>'"


def skills_with_fallback() -> list[Path]:
    out = []
    for skill_md in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        if FALLBACK_ENV_LINE in skill_md.read_text(encoding="utf-8"):
            out.append(skill_md)
    return out


def test_fallback_exists_in_expected_skills():
    found = {p.parent.name for p in skills_with_fallback()}
    assert found == {
        "brain", "doctor", "lint", "audit",
        "reset", "hard-reset", "update-check",
    }


class TestBaseDirFallback:
    @pytest.mark.parametrize("skill_md", skills_with_fallback(), ids=lambda p: p.parent.name)
    def test_base_dir_fallback_documented(self, skill_md: Path):
        text = skill_md.read_text(encoding="utf-8")
        assert BASE_DIR_MARKER in text, (
            f"{skill_md}: fallback chain never mentions the harness-printed "
            f"'{BASE_DIR_MARKER}: <path>' line, which is the only reliable "
            "location in --plugin-dir sessions"
        )

    @pytest.mark.parametrize("skill_md", skills_with_fallback(), ids=lambda p: p.parent.name)
    def test_two_level_recipe_present(self, skill_md: Path):
        text = skill_md.read_text(encoding="utf-8")
        assert TWO_UP_RECIPE in text, (
            f"{skill_md}: must show the dirname-x2 recipe from the skill base "
            "directory up to the plugin root"
        )

    @pytest.mark.parametrize("skill_md", skills_with_fallback(), ids=lambda p: p.parent.name)
    def test_base_dir_before_marketplace_guesses(self, skill_md: Path):
        text = skill_md.read_text(encoding="utf-8")
        for m in re.finditer(re.escape(FALLBACK_ENV_LINE), text):
            seg = text[m.start():m.start() + 2000]
            if MARKETPLACE_GUESS in seg:
                assert BASE_DIR_MARKER in seg[:seg.find(MARKETPLACE_GUESS)], (
                    f"{skill_md}: the base-directory fallback must appear "
                    "BEFORE the marketplace cache guesses (they fail in "
                    "--plugin-dir sessions and a weak model stops reading)"
                )


class TestStopRule:
    @pytest.mark.parametrize("skill_md", skills_with_fallback(), ids=lambda p: p.parent.name)
    def test_stop_rule_present(self, skill_md: Path):
        text = skill_md.read_text(encoding="utf-8")
        assert STOP_RULE_MARKER in text, (
            f"{skill_md}: when the plugin root cannot be resolved, the skill "
            "must order an honest STOP; hand-writing .brain files as a "
            "substitute is how iter-1 fabricated its brain"
        )


class TestLayoutContract:
    def test_real_skill_dirs_are_two_levels_below_plugin_root(self):
        """The dirname-x2 recipe is only correct while skills live directly
        under the plugin root — pin that layout assumption."""
        dirs = [d for d in SKILLS_DIR.iterdir() if d.is_dir()]
        assert len(dirs) >= 7
        for d in dirs:
            assert d.parent.parent == PLUGIN_ROOT, (
                f"{d} is not two levels below the plugin root; the "
                "documented dirname-x2 recipe would resolve wrongly"
            )

    def test_bin_wrappers_exist_for_resolution_check(self):
        bin_dir = PLUGIN_ROOT / "bin"
        wrappers = list(bin_dir.glob("project-brain-*"))
        assert len(wrappers) >= 9, "bin/ must hold the project-brain-* wrappers"


def make_plugin_fixture(tmp_path: Path) -> Path:
    root = tmp_path / "plugintree"
    (root / "bin").mkdir(parents=True)
    (root / "bin" / "project-brain-doctor").write_text("#!/bin/sh\n", encoding="utf-8")
    (root / "skills" / "brain").mkdir(parents=True)
    return root


def extract_candidate_loop(text: str) -> str:
    start = text.find(CANDIDATE_LOOP_START)
    if start == -1:
        return ""
    end = text.find("\ndone", start)
    if end == -1:
        return ""
    return text[start:end + len("\ndone")]


def run_taught_loop(loop_src: str, base_dir: Path) -> str:
    script = (
        'PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}"\n'
        "BASE_DIR=" + repr(str(base_dir)) + "\n"
        + loop_src
        + '\nprintf "%s" "$PLUGIN_ROOT"\n'
    )
    proc = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


class TestBaseDirDepthRobustness:
    """KD-21: a wrong dirname-depth guess must not cascade into a hunt."""

    @pytest.mark.parametrize("skill_md", skills_with_fallback(), ids=lambda p: p.parent.name)
    def test_candidate_loop_is_runnable_code(self, skill_md: Path):
        text = skill_md.read_text(encoding="utf-8")
        assert BASE_DIR_ASSIGN in text, (
            f"{skill_md}: fallback must assign BASE_DIR from the harness line "
            "before the candidate loop"
        )
        loop_lines = [l for l in text.splitlines() if CANDIDATE_LOOP_START in l]
        assert loop_lines, f"{skill_md}: candidate loop missing entirely"
        for line in loop_lines:
            assert not line.lstrip().startswith("#"), (
                f"{skill_md}: the candidate loop must be runnable code, not a "
                "comment recipe (comment recipes get re-typed at the wrong depth)"
            )
        assert "\ndone" in text, f"{skill_md}: loop terminator missing"

    @pytest.mark.parametrize("below", [0, 1, 2])
    def test_taught_loop_resolves_plugin_root_at_any_depth(self, below, tmp_path):
        root = make_plugin_fixture(tmp_path)
        base = {0: root, 1: root / "skills", 2: root / "skills" / "brain"}[below]
        loop = extract_candidate_loop(
            (SKILLS_DIR / "brain" / "SKILL.md").read_text(encoding="utf-8")
        )
        assert loop, "brain SKILL.md: no candidate loop to test"
        assert run_taught_loop(loop, base) == str(root), (
            f"taught loop failed to resolve the plugin root from base {base}"
        )

    def test_taught_loop_leaves_root_empty_when_no_bin_anywhere(self, tmp_path):
        loop = extract_candidate_loop(
            (SKILLS_DIR / "brain" / "SKILL.md").read_text(encoding="utf-8")
        )
        assert loop, "brain SKILL.md: no candidate loop to test"
        assert run_taught_loop(loop, tmp_path) == "", (
            "loop must not invent a root when no candidate has bin/"
        )


class TestFullPathInvocationRule:
    """KD-22: bare project-brain-* commands must never be presented as a
    usable form — the harness aborts the session after roughly three
    consecutive failed Bash calls (live iter-5), so every bare 127 is a
    wasted strike."""

    def test_brain_skill_bare_command_rule(self):
        """The rule lives in ONE place (Resolve the plugin root); the Work
        loop's duplicate step 0 was deleted in the 0.10.0 fix-up round.
        Whitespace-normalized: prose reflows must not break the pin."""
        text = " ".join((SKILLS_DIR / "brain" / "SKILL.md").read_text(encoding="utf-8").split())
        assert "never type a bare" in text.lower(), (
            "brain SKILL.md must forbid bare project-brain-* invocations outright"
        )
        assert "plugin-root.txt" in text, (
            "brain SKILL.md must teach reading .brain/state/plugin-root.txt first"
        )
        assert "consecutive failed Bash calls" in text, (
            "brain SKILL.md must warn that consecutive Bash failures abort the session"
        )

    @pytest.mark.parametrize("skill_md", skills_with_fallback(), ids=lambda p: p.parent.name)
    def test_never_bare_paragraph_in_every_skill(self, skill_md: Path):
        text = skill_md.read_text(encoding="utf-8")
        assert "Never type a bare `project-brain-*` command" in text, (
            f"{skill_md}: the never-bare invocation rule is missing"
        )
